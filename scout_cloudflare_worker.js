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

    // Simple health check in browser
    if (request.method === "GET") {
      return new Response(JSON.stringify({
        status: "ok",
        service: "telegram-railway-wake-scout",
        time: new Date().toISOString()
      }), {
        headers: { "Content-Type": "application/json" }
      });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
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
      const isManualWakeCommand = text === "/wake" || text === "/track" || text === "/startstream" || text === "/start_stream";

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
        return new Response("Missing Configuration", { status: 500 });
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
      return new Response(JSON.stringify({ error: err.message }), { status: 500 });
    }
  }
};

/**
 * Triggers deployment/start of the Railway service instance.
 */
async function wakeRailwayService(token, serviceId, environmentId) {
  const query = `
    mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
      serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }
  `;

  const response = await fetch(RAILWAY_GRAPHQL_ENDPOINT, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      query,
      variables: {
        serviceId,
        environmentId
      }
    })
  });

  const data = await response.json();
  if (data.errors) {
    console.error("[Railway GraphQL Errors]", data.errors);
    throw new Error(data.errors.map(e => e.message).join(", "));
  }

  return data.data;
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
