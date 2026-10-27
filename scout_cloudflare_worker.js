/**
 * Cloudflare Worker: Telegram "Wake-on-Call" Scout for Railway
 * 
 * 100% Free Forever on Cloudflare Workers (100,000 free requests/day).
 * Scale-to-Zero: Costs $0 while waiting.
 * 
 * HOW IT WORKS:
 * 1. Listens for Telegram updates via Bot Webhook.
 * 2. When a voice chat/live stream starts (video_chat_started / voice_chat_started),
 *    OR when an admin sends /wake or /track:
 * 3. Sends a GraphQL request to Railway API to immediately boot/redeploy the Tracker VM.
 * 4. Alerts the Telegram group: "🚀 Live stream detected! Waking up tracker..."
 */

const RAILWAY_GRAPHQL_ENDPOINT = "https://backboard.railway.app/graphql/v2";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Simple health check or diagnostic wake test in browser
    if (request.method === "GET") {
      if (url.pathname === "/test-wake") {
        try {
          const res = await wakeRailwayService(
            env.RAILWAY_API_TOKEN,
            env.RAILWAY_SERVICE_ID,
            env.RAILWAY_ENVIRONMENT_ID
          );
          return new Response(JSON.stringify({ ok: true, railway: res }), {
            headers: { "Content-Type": "application/json" }
          });
        } catch (err) {
          return new Response(JSON.stringify({ ok: false, error: err.message }), {
            status: 200,
            headers: { "Content-Type": "application/json" }
          });
        }
      }

      return new Response(JSON.stringify({
        status: "ok",
        service: "telegram-railway-wake-scout",
        configured: {
          has_railway_token: Boolean(env.RAILWAY_API_TOKEN),
          has_service_id: Boolean(env.RAILWAY_SERVICE_ID),
          has_environment_id: Boolean(env.RAILWAY_ENVIRONMENT_ID),
          has_bot_token: Boolean(env.BOT_TOKEN)
        },
        time: new Date().toISOString()
      }), {
        headers: { "Content-Type": "application/json" }
      });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    if (env.WEBHOOK_SECRET) {
      const secretHeader = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
      if (secretHeader !== env.WEBHOOK_SECRET) {
        return new Response("Forbidden", { status: 403 });
      }
    }

    try {
      const update = await request.json();
      const msg = update.message || update.channel_post;

      if (!msg) {
        return new Response("OK", { status: 200 });
      }

      const chat = msg.chat || {};
      const chatId = chat.id;
      const chatTitle = chat.title || "Telegram Stream";
      const text = (msg.text || "").trim().toLowerCase();

      // Detection Conditions:
      // 1. Automatic Telegram Service Message (Livestream or Video Chat Started)
      const isAutoStreamStart = Boolean(msg.video_chat_started || msg.voice_chat_started);

      // 2. Manual Admin Commands (/wake, /track, /start_stream)
      const isManualWakeCommand = 
        text === "/wake" || 
        text.startsWith("/wake@") || 
        text.startsWith("/wake ") || 
        text === "/track" || 
        text.startsWith("/track@") || 
        text === "/startstream" || 
        text === "/start_stream";

      if (!isAutoStreamStart && !isManualWakeCommand) {
        return new Response("OK", { status: 200 });
      }

      console.log(`[Scout] Trigger detected in [${chatTitle}] (ID: ${chatId}). Trigger: ${isAutoStreamStart ? "Automatic video_chat_started" : text}`);

      // Read Railway credentials from Worker Environment Variables (or fallback)
      const railwayToken = env.RAILWAY_API_TOKEN;
      const serviceId = env.RAILWAY_SERVICE_ID;
      const environmentId = env.RAILWAY_ENVIRONMENT_ID;
      const botToken = env.BOT_TOKEN;

      if (!railwayToken || !serviceId || !environmentId) {
        console.error("[Scout Error] Missing Railway configuration environment variables.");
        if (botToken) {
          await sendTelegramMessage(botToken, chatId, "⚠️ **Wake-on-Call Scout Error:** Missing Railway API credentials in Cloudflare Worker settings.");
        }
        return new Response(JSON.stringify({ ok: false, error: "Missing Configuration" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      // 3. Check if Railway container is ALREADY online to prevent redundant wakes & messages
      const appUrl = env.DASHBOARD_URL || env.RAILWAY_APP_URL || "https://telegram-stream-tracker-production.up.railway.app";
      let isAlreadyOnline = false;
      try {
        const healthCheck = await fetch(`${appUrl}/api/health`, {
          method: "GET",
          signal: AbortSignal.timeout(2500)
        });
        if (healthCheck.ok) {
          isAlreadyOnline = true;
        }
      } catch (e) {
        isAlreadyOnline = false;
      }

      if (isAlreadyOnline) {
        console.log(`[Scout] Tracker container at ${appUrl} is already online. Skipping duplicate wake.`);
        return new Response(JSON.stringify({ success: true, status: "already_online" }), {
          headers: { "Content-Type": "application/json" }
        });
      }

      // Trigger Railway Service Deployment via GraphQL API
      const railwayResult = await wakeRailwayService(railwayToken, serviceId, environmentId);

      // Notify Telegram Chat
      if (botToken && chatId) {
        const replyText = isAutoStreamStart
          ? `🎙 **Live Stream Detected!**\n\n⚡️ Waking up the **Telegram Stream Tracker** on Railway...\nAttendance tracking & recording will attach automatically in ~20s.`
          : `🚀 **Manual Tracker Wake Requested!**\n\nStarting the tracker container on Railway...`;
        await sendTelegramMessage(botToken, chatId, replyText);
      }

      return new Response(JSON.stringify({ success: true, railway: railwayResult }), {
        headers: { "Content-Type": "application/json" }
      });

    } catch (err) {
      console.error("[Scout Fatal Error]", err);
      // Always return HTTP 200 to Telegram so the Bot Webhook queue does not stall on retries
      return new Response(JSON.stringify({ ok: false, error: err.message }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
};

/**
 * Triggers deployment/start of the Railway service instance.
 * Tests Bearer (Account/Workspace Token) and Project-Access-Token (Project Token) separately
 * across railway.com and railway.app endpoints.
 */
async function wakeRailwayService(token, serviceId, environmentId) {
  const cleanToken = (token || "").trim();
  const cleanServiceId = (serviceId || "").trim();
  const cleanEnvId = (environmentId || "").trim();

  const mutations = [
    `mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
      serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }`,
    `mutation ServiceInstanceDeploy($serviceId: String!, $environmentId: String!) {
      serviceInstanceDeploy(serviceId: $serviceId, environmentId: $environmentId)
    }`
  ];

  const endpoints = [
    "https://backboard.railway.com/graphql/v2",
    "https://backboard.railway.app/graphql/v2"
  ];

  const userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

  const authHeadersList = [
    { "Authorization": `Bearer ${cleanToken}`, "User-Agent": userAgent, "Content-Type": "application/json" },
    { "Project-Access-Token": cleanToken, "User-Agent": userAgent, "Content-Type": "application/json" }
  ];

  let lastError = null;

  for (const query of mutations) {
    for (const ep of endpoints) {
      for (const headers of authHeadersList) {
        try {
          const response = await fetch(ep, {
            method: "POST",
            headers,
            body: JSON.stringify({
              query,
              variables: {
                serviceId: cleanServiceId,
                environmentId: cleanEnvId
              }
            })
          });

          const data = await response.json();
          if (data.errors && data.errors.length > 0) {
            lastError = new Error(data.errors.map(e => e.message).join(", "));
            console.error(`[Railway GraphQL Error at ${ep}]`, data.errors);
            continue;
          }

          return data.data;
        } catch (err) {
          lastError = err;
          console.error(`[Railway Network Error at ${ep}]`, err);
        }
      }
    }
  }

  throw lastError || new Error("Failed to redeploy Railway service");
}

/**
 * Sends a notification message back to Telegram.
 */
async function sendTelegramMessage(botToken, chatId, text) {
  try {
    await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        parse_mode: "Markdown"
      })
    });
  } catch (e) {
    console.error("[Telegram Reply Error]", e);
  }
}
