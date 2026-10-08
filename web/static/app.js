/**
 * MOVE AM // MODERNIST CONTROL ROOM DASHBOARD
 * Telemetry, Audio Scribe & System Configuration with Telegram ID Authentication
 */

document.addEventListener("DOMContentLoaded", () => {
  // Telegram WebApp SDK Initialization
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    if (tg.enableClosingConfirmation) {
      tg.enableClosingConfirmation();
    }
  }

  // --- THEME MANAGEMENT (MODERNIST CONTROL ROOM DARK / LIGHT) ---
  function getPreferredTheme() {
    const saved = localStorage.getItem("tracker_theme");
    if (saved === "dark" || saved === "light") return saved;
    if (tg && (tg.colorScheme === "dark" || tg.colorScheme === "light")) {
      return tg.colorScheme;
    }
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "light";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.body.classList.toggle("dark-theme", theme === "dark");

    const headerColor = (theme === "dark") ? "#141312" : "#f3f2f2";
    if (tg) {
      try {
        if (typeof tg.setHeaderColor === "function") tg.setHeaderColor(headerColor);
        if (typeof tg.setBackgroundColor === "function") tg.setBackgroundColor(headerColor);
      } catch (err) {
        console.warn("Telegram color sync error:", err);
      }
    }

    const toggleBtn = document.getElementById("btn-theme-toggle");
    if (toggleBtn) {
      toggleBtn.textContent = theme === "dark" ? "☼" : "◐";
      toggleBtn.title = theme === "dark" ? "SWITCH TO LIGHT MODE" : "SWITCH TO DARK MODE";
      toggleBtn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    }
  }

  function toggleTheme() {
    triggerHaptic("medium");
    const current = document.documentElement.getAttribute("data-theme") || getPreferredTheme();
    const nextTheme = current === "dark" ? "light" : "dark";
    localStorage.setItem("tracker_theme", nextTheme);
    applyTheme(nextTheme);
    showToast(`THEME: ${nextTheme.toUpperCase()} MODE`);
  }

  // Initialize theme on load
  const initialTheme = getPreferredTheme();
  applyTheme(initialTheme);

  // Sync with Telegram theme changes if operator hasn't explicitly overridden it
  if (tg && typeof tg.onEvent === "function") {
    try {
      tg.onEvent("themeChanged", () => {
        if (!localStorage.getItem("tracker_theme")) {
          applyTheme(tg.colorScheme || "light");
        }
      });
    } catch (e) {
      console.warn("Theme event listener error:", e);
    }
  }

  document.getElementById("btn-theme-toggle")?.addEventListener("click", (e) => {
    e.preventDefault();
    toggleTheme();
  });

  function triggerHaptic(type = "light") {
    try {
      if (tg && tg.HapticFeedback) {
        if (type === "selection") {
          if (typeof tg.HapticFeedback.selectionChanged === "function") {
            tg.HapticFeedback.selectionChanged();
          }
        } else if (["light", "medium", "heavy", "rigid", "soft"].includes(type)) {
          if (typeof tg.HapticFeedback.impactOccurred === "function") {
            tg.HapticFeedback.impactOccurred(type);
          }
        } else if (["error", "success", "warning"].includes(type)) {
          if (typeof tg.HapticFeedback.notificationOccurred === "function") {
            tg.HapticFeedback.notificationOccurred(type);
          }
        } else {
          tg.HapticFeedback.impactOccurred("light");
        }
      }
    } catch (e) {
      console.warn("Haptic error caught:", e);
    }
  }

  function showToast(message, duration = 2500) {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message.toUpperCase();
    container.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, duration);
  }

  // --- AUTHENTICATION STATE & LOGIC ---
  let authToken = localStorage.getItem("tracker_auth_token") || "";
  let currentAuthUser = null;
  let activeOtpTarget = "";

  const authGate = document.getElementById("auth-gate");
  const authAlert = document.getElementById("auth-alert");
  const btnAuthLock = document.getElementById("btn-auth-lock");

  function showAuthGate(errorMessage = null) {
    if (authGate) authGate.classList.remove("hidden");
    if (btnAuthLock) {
      btnAuthLock.textContent = "🔒";
      btnAuthLock.title = "Authenticate Operator";
    }
    if (errorMessage) {
      showAuthAlert(errorMessage);
    }
  }

  function hideAuthGate() {
    if (authGate) authGate.classList.add("hidden");
    if (authAlert) authAlert.classList.add("hidden");
    if (btnAuthLock) {
      btnAuthLock.textContent = "🔓";
      btnAuthLock.title = currentAuthUser ? `Logged in: ${currentAuthUser.name} (Click to lock)` : "Authenticated";
    }
  }

  function showAuthAlert(msg) {
    if (!authAlert) return;
    authAlert.textContent = msg.toUpperCase();
    authAlert.classList.remove("hidden");
  }

  async function apiFetch(url, options = {}) {
    const headers = options.headers ? { ...options.headers } : {};
    if (authToken) {
      headers["Authorization"] = `Bearer ${authToken}`;
    }
    if (tg && tg.initData) {
      headers["X-Telegram-Init-Data"] = tg.initData;
    }
    options.headers = headers;

    const res = await fetch(url, options);
    if (res.status === 401 && !url.includes("/api/auth/")) {
      showAuthGate("AUTHENTICATION REQUIRED // OPERATOR SESSION EXPIRED");
    }
    return res;
  }

  // Wire Auth Gate Tabs & Forms
  const tabAuthOtp = document.getElementById("tab-auth-otp");
  const tabAuthKey = document.getElementById("tab-auth-key");
  const secAuthOtp = document.getElementById("auth-section-otp");
  const secAuthKey = document.getElementById("auth-section-key");

  tabAuthOtp?.addEventListener("click", () => {
    triggerHaptic("selection");
    tabAuthOtp.classList.add("active");
    tabAuthKey.classList.remove("active");
    secAuthOtp.classList.remove("hidden");
    secAuthKey.classList.add("hidden");
    if (authAlert) authAlert.classList.add("hidden");
  });

  tabAuthKey?.addEventListener("click", () => {
    triggerHaptic("selection");
    tabAuthKey.classList.add("active");
    tabAuthOtp.classList.remove("active");
    secAuthKey.classList.remove("hidden");
    secAuthOtp.classList.add("hidden");
    if (authAlert) authAlert.classList.add("hidden");
  });

  // Request OTP Button
  const btnRequestOtp = document.getElementById("btn-request-otp");
  const otpStepRequest = document.getElementById("otp-step-request");
  const otpStepVerify = document.getElementById("otp-step-verify");
  const otpHintTarget = document.getElementById("otp-hint-target");

  btnRequestOtp?.addEventListener("click", async () => {
    const target = document.getElementById("input-auth-identity").value.trim();
    if (!target) {
      showAuthAlert("PLEASE ENTER YOUR TELEGRAM USER ID OR @USERNAME");
      return;
    }

    triggerHaptic("medium");
    btnRequestOtp.disabled = true;
    btnRequestOtp.textContent = "SENDING CODE...";

    try {
      const res = await fetch("/api/auth/request-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        activeOtpTarget = target;
        otpStepRequest.classList.add("hidden");
        otpStepVerify.classList.remove("hidden");
        if (otpHintTarget) otpHintTarget.textContent = `Code sent to Telegram chat: ${target}`;
        if (authAlert) authAlert.classList.add("hidden");
        showToast("CODE SENT TO YOUR TELEGRAM");
        document.getElementById("input-auth-code")?.focus();
      } else {
        showAuthAlert(data.message || data.error || "FAILED TO SEND CODE");
      }
    } catch (err) {
      showAuthAlert("CONNECTION ERROR WHILE REQUESTING CODE");
    } finally {
      btnRequestOtp.disabled = false;
      btnRequestOtp.textContent = "REQUEST CODE »";
    }
  });

  // Back button in OTP form
  document.getElementById("btn-back-otp")?.addEventListener("click", () => {
    triggerHaptic("light");
    otpStepVerify.classList.add("hidden");
    otpStepRequest.classList.remove("hidden");
    if (authAlert) authAlert.classList.add("hidden");
  });

  // Submit OTP Verification
  const btnSubmitOtp = document.getElementById("btn-submit-otp");
  btnSubmitOtp?.addEventListener("click", async () => {
    const code = document.getElementById("input-auth-code").value.trim();
    if (!code || code.length < 4) {
      showAuthAlert("PLEASE ENTER THE 6-DIGIT VERIFICATION CODE");
      return;
    }

    triggerHaptic("heavy");
    btnSubmitOtp.disabled = true;
    btnSubmitOtp.textContent = "VERIFYING...";

    try {
      const res = await fetch("/api/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: activeOtpTarget, code })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        authToken = data.token;
        localStorage.setItem("tracker_auth_token", authToken);
        currentAuthUser = data.user;

        const greetingEl = document.getElementById("user-greeting");
        if (greetingEl) {
          greetingEl.textContent = `OPERATOR: ${data.user.name.toUpperCase()} // TELEMETRY ACTIVE`;
        }

        hideAuthGate();
        showToast("OPERATOR AUTHENTICATED");
        loadStreams();
        loadLiveStatus();
      } else {
        showAuthAlert(data.message || data.error || "INCORRECT VERIFICATION CODE");
      }
    } catch (err) {
      showAuthAlert("NETWORK ERROR DURING CODE VERIFICATION");
    } finally {
      btnSubmitOtp.disabled = false;
      btnSubmitOtp.textContent = "VERIFY & UNLOCK";
    }
  });

  // Submit Master Passkey
  const btnSubmitKey = document.getElementById("btn-submit-key");
  btnSubmitKey?.addEventListener("click", async () => {
    const passkey = document.getElementById("input-auth-key").value.trim();
    if (!passkey) {
      showAuthAlert("PLEASE ENTER THE DASHBOARD MASTER PASSKEY");
      return;
    }

    triggerHaptic("heavy");
    btnSubmitKey.disabled = true;
    btnSubmitKey.textContent = "AUTHENTICATING...";

    try {
      const res = await fetch("/api/auth/login-passkey", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passkey })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        authToken = data.token;
        localStorage.setItem("tracker_auth_token", authToken);
        currentAuthUser = data.user;

        const greetingEl = document.getElementById("user-greeting");
        if (greetingEl) {
          greetingEl.textContent = `OPERATOR: ${data.user.name.toUpperCase()} // TELEMETRY ACTIVE`;
        }

        hideAuthGate();
        showToast("OPERATOR PASSKEY ACCEPTED");
        loadStreams();
        loadLiveStatus();
      } else {
        showAuthAlert(data.error || "INVALID MASTER PASSKEY");
      }
    } catch (err) {
      showAuthAlert("CONNECTION ERROR DURING PASSKEY VERIFICATION");
    } finally {
      btnSubmitKey.disabled = false;
      btnSubmitKey.textContent = "UNLOCK DASHBOARD";
    }
  });

  // Header Lock / Logout Button
  btnAuthLock?.addEventListener("click", async () => {
    triggerHaptic("medium");
    if (!authGate.classList.contains("hidden")) {
      return; // Already locked
    }

    if (confirm("Lock Control Room and end current operator session?")) {
      try {
        await apiFetch("/api/auth/logout", { method: "POST" });
      } catch (e) {}

      authToken = "";
      localStorage.removeItem("tracker_auth_token");
      currentAuthUser = null;
      showToast("CONTROL ROOM LOCKED");
      showAuthGate();
    }
  });

  function mountTelegramLoginWidget(botUsername) {
    if (!botUsername) return;
    const wrapper = document.getElementById("telegram-widget-wrapper");
    const divider = document.getElementById("widget-divider");
    const container = document.getElementById("telegram-login-widget-container");
    if (!container) return;

    wrapper?.classList.remove("hidden");
    divider?.classList.remove("hidden");
    container.innerHTML = "";

    window.onTelegramAuth = async function(user) {
      triggerHaptic("heavy");
      showToast("VERIFYING TELEGRAM SIGNATURE...");
      try {
        const res = await fetch("/api/auth/telegram-widget", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ auth_data: user })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          authToken = data.token;
          localStorage.setItem("tracker_auth_token", authToken);
          currentAuthUser = data.user;
          const greetingEl = document.getElementById("user-greeting");
          if (greetingEl) {
            greetingEl.textContent = `OPERATOR: ${data.user.name.toUpperCase()} (@${data.user.username}) // TELEMETRY ACTIVE`;
          }
          hideAuthGate();
          showToast(`AUTHENTICATED: @${data.user.username}`);
          loadStreams();
          loadLiveStatus();
        } else {
          showAuthAlert(data.message || data.error || "TELEGRAM AUTHENTICATION REJECTED");
        }
      } catch (err) {
        showAuthAlert("FAILED TO CONNECT TO SERVER FOR TELEGRAM LOGIN");
      }
    };

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "0");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    script.async = true;
    container.appendChild(script);
  }

  // Master Startup Authentication Routine
  async function initializeAuthentication() {
    // 0. Load public auth config (such as bot username for the Telegram Widget)
    try {
      const cfgRes = await fetch("/api/auth/config");
      if (cfgRes.ok) {
        const cfg = await cfgRes.json();
        if (cfg.bot_username) {
          mountTelegramLoginWidget(cfg.bot_username);
        }
      }
    } catch (e) {
      console.warn("Auth config fetch notice:", e);
    }

    // 1. If running inside Telegram Mini App, use cryptographic initData signature
    if (tg && tg.initData) {
      try {
        const res = await fetch("/api/auth/telegram-webapp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ initData: tg.initData })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          authToken = data.token;
          localStorage.setItem("tracker_auth_token", authToken);
          currentAuthUser = data.user;

          const greetingEl = document.getElementById("user-greeting");
          if (greetingEl) {
            greetingEl.textContent = `OPERATOR: ${data.user.name.toUpperCase()} (ID: ${data.user.id}) // TELEMETRY ACTIVE`;
          }

          hideAuthGate();
          loadStreams();
          loadLiveStatus();
          return;
        } else if (res.status === 403) {
          showAuthGate(`⛔️ ACCESS DENIED // TELEGRAM ID ${data.telegram_id} IS NOT AN AUTHORIZED ADMINISTRATOR.`);
          return;
        }
      } catch (err) {
        console.warn("Telegram initData authentication notice:", err);
      }
    }

    // 2. If running in external browser (Chrome / Safari), check existing session
    try {
      const res = await apiFetch("/api/auth/me");
      if (res.ok) {
        const data = await res.json();
        if (data.authenticated) {
          currentAuthUser = data.user;
          const greetingEl = document.getElementById("user-greeting");
          if (greetingEl) {
            greetingEl.textContent = `OPERATOR: ${data.user.name.toUpperCase()} // TELEMETRY ACTIVE`;
          }

          hideAuthGate();
          loadStreams();
          loadLiveStatus();
          return;
        }
      }
    } catch (e) {
      console.warn("Session check notice:", e);
    }

    // Default: Show auth gate if unauthenticated
    showAuthGate();
  }

  // State
  let streamsData = [];
  let currentFilter = "all";
  let activeStreamDetail = null;

  // --- TAB NAVIGATION (NAVY ACTIVE) ---
  const tabButtons = document.querySelectorAll(".nav-tab");
  const tabPanes = document.querySelectorAll(".tab-pane");

  function switchTab(targetTab) {
    if (!targetTab) return;
    triggerHaptic("selection");

    tabButtons.forEach(b => {
      const isTarget = (b.dataset.tab === targetTab || b.getAttribute("data-tab") === targetTab);
      b.classList.toggle("active", isTarget);
    });

    tabPanes.forEach(p => {
      p.classList.toggle("active", p.id === `tab-${targetTab}`);
    });

    try {
      if (targetTab === "live") loadLiveStatus();
      if (targetTab === "settings") loadSettingsData();
    } catch (err) {
      console.error("Tab data load notice:", err);
    }
  }

  tabButtons.forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const targetTab = btn.dataset.tab || btn.getAttribute("data-tab");
      switchTab(targetTab);
    });
  });

  // --- REFRESH BUTTON ---
  document.getElementById("btn-refresh")?.addEventListener("click", () => {
    triggerHaptic("light");
    loadStreams();
    loadLiveStatus();
    showToast("SYNCING TELEMETRY...");
  });

  // --- STREAMS TAB & DATA FETCHING ---
  async function loadStreams() {
    const listEl = document.getElementById("streams-list");
    const badgeEl = document.getElementById("badge-streams");

    try {
      const res = await apiFetch("/api/streams");
      if (!res.ok) {
        if (res.status === 401) return;
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      streamsData = data.streams || [];

      if (badgeEl) badgeEl.textContent = streamsData.length;
      renderStreamsList();
    } catch (err) {
      console.error("Failed to load streams", err);
      listEl.innerHTML = `<div class="loading-block">ERROR: FAILED TO LOAD SESSIONS (${err.message.toUpperCase()})</div>`;
    }
  }

  function renderStreamsList() {
    const listEl = document.getElementById("streams-list");
    const searchTerm = document.getElementById("stream-search")?.value.toLowerCase().trim() || "";

    const filtered = streamsData.filter(s => {
      const matchSearch = (s.chat_title || "").toLowerCase().includes(searchTerm) ||
                          (s.stream_id || "").toLowerCase().includes(searchTerm);
      if (!matchSearch) return false;

      if (currentFilter === "audio") return s.has_audio;
      if (currentFilter === "transcripts") return s.has_transcript || s.has_summary;
      return true;
    });

    if (filtered.length === 0) {
      listEl.innerHTML = `<div class="loading-block">NO SESSIONS MATCHING QUERY</div>`;
      return;
    }

    listEl.innerHTML = filtered.map(s => {
      const isLive = s.is_active === 1;
      const durMin = Math.round((s.duration_sec || 0) / 60);
      const startDt = s.start_time ? new Date(s.start_time).toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
      }).toUpperCase() : 'RECENT';

      return `
        <div class="list-card" data-id="${s.stream_id}">
          <div class="card-title-row">
            <h3 class="card-title">${escapeHtml(s.chat_title || 'VOICE STREAM')}</h3>
            <span class="tag ${isLive ? 'tag-running' : 'tag-idle'}">${isLive ? 'LIVE' : '#' + (s.index_num || '0')}</span>
          </div>

          <div class="card-secondary">
            ${startDt} · ${durMin > 0 ? durMin + ' MINS DURATION' : 'IN PROGRESS'}
          </div>

          <div class="meter-row">
            <span class="meter-label">ATTENDEES</span>
            <div class="meter-track">
              <div class="meter-fill" style="width: ${Math.min(100, (s.total_participants || 0) * 2)}%;"></div>
            </div>
            <span class="meter-value">${s.total_participants || 0}</span>
          </div>

          <div class="card-footer-row">
            <div class="signal-tags">
              ${s.has_audio ? '<span class="signal-chip active-blue">AUDIO</span>' : ''}
              ${s.has_summary ? '<span class="signal-chip">MINUTES</span>' : ''}
              ${s.has_transcript ? '<span class="signal-chip">VERBATIM</span>' : ''}
              ${s.has_csv ? '<span class="signal-chip">CSV</span>' : ''}
            </div>
            <span style="font-weight:800; font-size:11px; color:var(--color-neutral-700);">INSPECT →</span>
          </div>
        </div>
      `;
    }).join("");

    listEl.querySelectorAll(".list-card").forEach(card => {
      card.addEventListener("click", () => {
        const streamId = card.getAttribute("data-id");
        openStreamDetailModal(streamId);
      });
    });
  }

  // Filter Row & Search Handlers
  document.querySelectorAll(".filter-btn:not(#tab-auth-otp):not(#tab-auth-key)").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      triggerHaptic("selection");
      document.querySelectorAll(".filter-strip:not(.auth-strip) .filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentFilter = btn.dataset.filter || btn.getAttribute("data-filter") || "all";
      renderStreamsList();
    });
  });

  const searchInput = document.getElementById("stream-search");
  const clearBtn = document.getElementById("search-clear");
  searchInput?.addEventListener("input", (e) => {
    if (clearBtn) clearBtn.classList.toggle("hidden", !e.target.value);
    renderStreamsList();
  });
  clearBtn?.addEventListener("click", () => {
    searchInput.value = "";
    clearBtn.classList.add("hidden");
    renderStreamsList();
  });

  // --- STREAM DETAIL MODAL ---
  const modal = document.getElementById("stream-modal");
  const closeModalBtn = document.getElementById("btn-close-modal");

  function openStreamDetailModal(streamId) {
    triggerHaptic("medium");
    modal.classList.remove("hidden");

    if (tg?.BackButton) {
      tg.BackButton.show();
      tg.BackButton.onClick(closeStreamDetailModal);
    }

    fetchStreamDetail(streamId);
  }

  function closeStreamDetailModal() {
    triggerHaptic("light");
    modal.classList.add("hidden");

    const audioEl = document.getElementById("stream-audio-element");
    if (audioEl) audioEl.pause();

    if (tg?.BackButton) {
      tg.BackButton.hide();
    }
  }

  closeModalBtn?.addEventListener("click", closeStreamDetailModal);

  async function fetchStreamDetail(streamId) {
    const titleEl = document.getElementById("modal-chat-title");
    const metaEl = document.getElementById("modal-meta-line");
    const bandEl = document.getElementById("modal-band");
    const bandKicker = document.getElementById("modal-band-kicker");
    const bandCode = document.getElementById("modal-band-code");

    const audioCard = document.getElementById("audio-player-card");
    const audioEl = document.getElementById("stream-audio-element");
    const downloadAudioBtn = document.getElementById("btn-download-audio");
    const downloadCsvBtn = document.getElementById("btn-download-csv");
    const summaryBox = document.getElementById("summary-text-container");
    const transcriptBox = document.getElementById("transcript-text-container");
    const participantsTableBody = document.getElementById("participants-table-body");

    titleEl.textContent = "LOADING TELEMETRY...";
    metaEl.textContent = "SYNCHRONIZING CALL RECORD...";
    summaryBox.innerHTML = '<p>LOADING MINUTES...</p>';
    transcriptBox.textContent = 'LOADING VERBATIM TRANSCRIPT...';
    participantsTableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;">LOADING...</td></tr>';
    audioCard.classList.add("hidden");

    try {
      const res = await apiFetch(`/api/streams/${streamId}`);
      const data = await res.json();
      activeStreamDetail = data;

      const s = data.stream;
      titleEl.textContent = s.chat_title ? s.chat_title.toUpperCase() : "VOICE CALL";

      const durMin = Math.round((s.duration_sec || 0) / 60);
      const startDt = s.start_time ? new Date(s.start_time).toLocaleString().toUpperCase() : '';
      metaEl.textContent = `${startDt} · ${durMin} MINS · ${data.participants_count} CALLERS`;

      // Top Semantic Color Band
      if (s.is_active === 1) {
        bandEl.className = "modal-color-band band-green";
        bandKicker.textContent = "LIVE STREAM ACTIVE";
        bandCode.textContent = "RUNNING";
      } else {
        bandEl.className = "modal-color-band band-blue";
        bandKicker.textContent = "SESSION TELEMETRY";
        bandCode.textContent = `ID #${s.index_num || '0'}`;
      }

      // Download CSV
      downloadCsvBtn.href = `/api/streams/${s.stream_id}/csv`;

      // Audio setup
      if (data.assets?.has_audio) {
        audioCard.classList.remove("hidden");
        const audioUrl = `/api/streams/${s.stream_id}/audio`;
        audioEl.src = audioUrl;
        downloadAudioBtn.href = audioUrl;
      } else {
        audioCard.classList.add("hidden");
        audioEl.src = "";
      }

      renderParticipantsTable(data.participants || []);
      fetchSummary(s.stream_id);
      fetchTranscript(s.stream_id);

    } catch (err) {
      titleEl.textContent = "ERROR LOADING RECORD";
      metaEl.textContent = err.message.toUpperCase();
    }
  }

  function renderParticipantsTable(participants) {
    const body = document.getElementById("participants-table-body");
    if (!participants || participants.length === 0) {
      body.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:16px;">NO ATTENDEE RECORDS LOGGED.</td></tr>';
      return;
    }

    body.innerHTML = participants.map((p, idx) => {
      const uname = p.username ? `@${p.username}` : '';
      const durMin = (p.total_min || 0).toFixed(1);
      const pct = (p.pct || 0).toFixed(1);
      const isGood = parseFloat(pct) >= 50.0;

      return `
        <tr>
          <td style="font-weight:800;">${idx + 1}</td>
          <td>
            <div style="font-weight:800;">${escapeHtml(p.name || 'USER')}</div>
            <div style="font-size:11px; color:var(--color-neutral-700);">${escapeHtml(uname)}</div>
          </td>
          <td>${durMin}m</td>
          <td style="text-align:right;">
            <span class="tag ${isGood ? 'tag-green' : 'tag-idle'}">${pct}%</span>
          </td>
        </tr>
      `;
    }).join("");
  }

  async function fetchSummary(streamId) {
    const box = document.getElementById("summary-text-container");
    const downloadBtn = document.getElementById("btn-download-summary");
    downloadBtn.href = `/api/streams/${streamId}/summary?download=1`;

    try {
      const res = await apiFetch(`/api/streams/${streamId}/summary`);
      if (res.ok) {
        const data = await res.json();
        const rawMarkdown = data.summary || "";
        box.innerHTML = window.marked ? window.marked.parse(rawMarkdown) : `<pre class="text-viewer-pre">${escapeHtml(rawMarkdown)}</pre>`;
      } else {
        box.innerHTML = `<p style="color:var(--color-neutral-700);">AI executive minutes not yet generated for this session.</p>`;
      }
    } catch (e) {
      box.innerHTML = `<p>Error loading minutes.</p>`;
    }
  }

  async function fetchTranscript(streamId) {
    const box = document.getElementById("transcript-text-container");
    const downloadBtn = document.getElementById("btn-download-transcript");
    downloadBtn.href = `/api/streams/${streamId}/transcript?download=1`;

    try {
      const res = await apiFetch(`/api/streams/${streamId}/transcript`);
      if (res.ok) {
        const data = await res.json();
        box.textContent = data.transcript || "No transcript text available.";
      } else {
        box.textContent = "Verbatim speech-to-text not yet generated for this session.";
      }
    } catch (e) {
      box.textContent = "Error loading transcript.";
    }
  }

  // Subtab Segmented Switcher
  document.querySelectorAll(".subtab-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      triggerHaptic("selection");
      const targetSubtab = btn.dataset.subtab || btn.getAttribute("data-subtab");

      document.querySelectorAll(".subtab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      document.querySelectorAll(".subtab-content").forEach(c => c.classList.add("hidden"));
      const activeContent = document.getElementById(`subtab-${targetSubtab}-content`);
      if (activeContent) activeContent.classList.remove("hidden");
    });
  });

  // Copy Buttons
  document.getElementById("btn-copy-summary")?.addEventListener("click", () => {
    const text = document.getElementById("summary-text-container")?.innerText || "";
    navigator.clipboard.writeText(text).then(() => showToast("COPIED EXECUTIVE MINUTES"));
  });

  document.getElementById("btn-copy-transcript")?.addEventListener("click", () => {
    const text = document.getElementById("transcript-text-container")?.textContent || "";
    navigator.clipboard.writeText(text).then(() => showToast("COPIED VERBATIM TRANSCRIPT"));
  });

  // --- LIVE MONITOR TAB & HUD STATS ---
  async function loadLiveStatus() {
    try {
      const res = await apiFetch("/api/status");
      const status = await res.json();

      // Update HUD Stat Strip (Numbers are the Hero)
      const hudTotal = document.getElementById("hud-total-streams");
      const hudGroups = document.getElementById("hud-tracked-groups");
      const hudAdmins = document.getElementById("hud-admins-count");
      const hudEngine = document.getElementById("hud-engine-name");

      if (hudTotal) hudTotal.textContent = status.total_streams ?? "-";
      if (hudGroups) hudGroups.textContent = status.tracked_groups_count ?? "-";
      if (hudAdmins) hudAdmins.textContent = status.admins_count ?? "-";
      if (hudEngine) hudEngine.textContent = (status.transcription_engine || "GEMINI").toUpperCase();

      const telemetryEngine = document.getElementById("telemetry-engine-name");
      if (telemetryEngine) telemetryEngine.textContent = `${(status.transcription_engine || "GEMINI").toUpperCase()} (ACTIVE)`;

      // Live banner
      const liveBanner = document.getElementById("live-call-banner");
      const liveBannerTitle = document.getElementById("live-banner-title");
      const liveBannerTag = document.getElementById("live-banner-tag");
      const liveBannerDesc = document.getElementById("live-banner-desc");
      const livePulseBadge = document.getElementById("badge-live-pulse");

      if (status.active_streams_count > 0 && status.active_streams?.length > 0) {
        const active = status.active_streams[0];
        liveBanner.classList.add("active");
        livePulseBadge.classList.remove("hidden");
        liveBannerTitle.textContent = `LIVE: ${active.chat_title ? active.chat_title.toUpperCase() : 'CALL ACTIVE'}`;
        liveBannerTag.className = "tag tag-running";
        liveBannerTag.textContent = "RUNNING";
        liveBannerDesc.textContent = "Telemetry engine logging live attendee joins and drop-offs.";
      } else {
        liveBanner.classList.remove("active");
        livePulseBadge.classList.add("hidden");
        liveBannerTitle.textContent = "NO ACTIVE STREAM";
        liveBannerTag.className = "tag tag-idle";
        liveBannerTag.textContent = "IDLE";
        liveBannerDesc.textContent = "Tracking daemon standing by. Listening for voice chat start events.";
      }
    } catch (e) {
      console.error("Status load failed", e);
    }
  }

  // --- SETTINGS TAB ---
  async function loadSettingsData() {
    loadSettingsEngine();
    loadTrackedGroups();
    loadAdminRecipients();
  }

  async function loadSettingsEngine() {
    try {
      const res = await apiFetch("/api/settings");
      const data = await res.json();
      const eng = (data.transcription_engine || "gemini").toLowerCase();

      document.querySelectorAll(".radio-row").forEach(row => {
        const rowEng = row.getAttribute("data-engine");
        if (rowEng === eng) {
          row.classList.add("selected");
          const radio = row.querySelector('input[type="radio"]');
          if (radio) radio.checked = true;
        } else {
          row.classList.remove("selected");
        }
      });
    } catch (e) {
      console.error("Failed to load settings", e);
    }
  }

  document.querySelectorAll(".radio-row").forEach(row => {
    row.addEventListener("click", async () => {
      triggerHaptic("medium");
      const newEng = row.getAttribute("data-engine");

      document.querySelectorAll(".radio-row").forEach(r => r.classList.remove("selected"));
      row.classList.add("selected");

      try {
        const res = await apiFetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transcription_engine: newEng })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`SWITCHED AI SCRIBE TO ${newEng.toUpperCase()}`);
          const hudEngine = document.getElementById("hud-engine-name");
          if (hudEngine) hudEngine.textContent = newEng.toUpperCase();
        } else {
          showToast(`ERROR: ${data.error || 'UPDATE FAILED'}`);
        }
      } catch (err) {
        showToast("SERVER ERROR");
      }
    });
  });

  // Tracked Groups Management
  async function loadTrackedGroups() {
    const listEl = document.getElementById("tracked-groups-list");
    try {
      const res = await apiFetch("/api/groups");
      const data = await res.json();
      const groups = data.groups || [];

      if (groups.length === 0) {
        listEl.innerHTML = '<div class="loading-block">NO MONITORED GROUPS CONFIGURED.</div>';
        return;
      }

      listEl.innerHTML = groups.map(g => {
        const title = g.chat_title || g.target || 'TARGET';
        const target = g.chat_id || g.target || '';
        return `
          <div class="data-row">
            <div>
              <div class="data-row-main">${escapeHtml(title.toUpperCase())}</div>
              <div class="data-row-sub">${escapeHtml(target)} · ${g.stream_count || 0} SESSIONS ARCHIVED</div>
            </div>
            <button class="btn-destructive-ghost" data-target="${escapeHtml(g.chat_id || g.target)}">DELETE</button>
          </div>
        `;
      }).join("");

      listEl.querySelectorAll(".btn-destructive-ghost").forEach(btn => {
        btn.addEventListener("click", () => {
          const target = btn.getAttribute("data-target");
          deleteGroup(target);
        });
      });
    } catch (e) {
      listEl.innerHTML = '<div class="loading-block">ERROR LOADING GROUPS.</div>';
    }
  }

  async function deleteGroup(target) {
    if (!confirm(`Delete monitored group '${target}'?`)) return;
    triggerHaptic("heavy");
    try {
      const res = await apiFetch(`/api/groups/${encodeURIComponent(target)}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        showToast(`REMOVED GROUP ${target.toUpperCase()}`);
        loadTrackedGroups();
        loadLiveStatus();
      }
    } catch (e) {
      showToast("DELETE FAILED");
    }
  }

  // Add Group Modal
  const addGroupModal = document.getElementById("add-group-modal");
  document.getElementById("btn-add-group")?.addEventListener("click", () => {
    triggerHaptic("light");
    addGroupModal.classList.remove("hidden");
  });
  document.getElementById("btn-cancel-add-group")?.addEventListener("click", () => addGroupModal.classList.add("hidden"));

  document.getElementById("form-add-group")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const target = document.getElementById("input-group-target").value.trim();
    const title = document.getElementById("input-group-title").value.trim();

    try {
      const res = await apiFetch("/api/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, title })
      });
      const data = await res.json();
      if (data.success) {
        showToast("TARGET GROUP SAVED");
        addGroupModal.classList.add("hidden");
        document.getElementById("input-group-target").value = "";
        document.getElementById("input-group-title").value = "";
        loadTrackedGroups();
        loadLiveStatus();
      } else {
        showToast(data.error || "FAILED TO SAVE");
      }
    } catch (err) {
      showToast("CONNECTION ERROR");
    }
  });

  // Admin Recipients Management
  async function loadAdminRecipients() {
    const listEl = document.getElementById("admin-recipients-list");
    try {
      const res = await apiFetch("/api/admins");
      const data = await res.json();
      const admins = data.admins || [];

      if (admins.length === 0) {
        listEl.innerHTML = '<div class="loading-block">NO ADMIN RECIPIENTS CONFIGURED.</div>';
        return;
      }

      listEl.innerHTML = admins.map(a => `
        <div class="data-row">
          <div>
            <div class="data-row-main">${escapeHtml((a.name || a.target).toUpperCase())}</div>
            <div class="data-row-sub">${escapeHtml(a.target)} · ADDED BY: ${escapeHtml((a.added_by || 'ADMIN').toUpperCase())}</div>
          </div>
          <button class="btn-destructive-ghost" data-target="${escapeHtml(a.target)}">DELETE</button>
        </div>
      `).join("");

      listEl.querySelectorAll(".btn-destructive-ghost").forEach(btn => {
        btn.addEventListener("click", () => {
          const target = btn.getAttribute("data-target");
          deleteAdmin(target);
        });
      });
    } catch (e) {
      listEl.innerHTML = '<div class="loading-block">ERROR LOADING ADMINS.</div>';
    }
  }

  async function deleteAdmin(target) {
    if (!confirm(`Delete admin recipient '${target}'?`)) return;
    triggerHaptic("heavy");
    try {
      const res = await apiFetch(`/api/admins/${encodeURIComponent(target)}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        showToast(`REMOVED ADMIN ${target.toUpperCase()}`);
        loadAdminRecipients();
        loadLiveStatus();
      }
    } catch (e) {
      showToast("DELETE FAILED");
    }
  }

  // Add Admin Modal
  const addAdminModal = document.getElementById("add-admin-modal");
  document.getElementById("btn-add-admin")?.addEventListener("click", () => {
    triggerHaptic("light");
    addAdminModal.classList.remove("hidden");
  });
  document.getElementById("btn-cancel-add-admin")?.addEventListener("click", () => addAdminModal.classList.add("hidden"));

  document.getElementById("form-add-admin")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const target = document.getElementById("input-admin-target").value.trim();
    const name = document.getElementById("input-admin-name").value.trim();

    try {
      const res = await apiFetch("/api/admins", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, name })
      });
      const data = await res.json();
      if (data.success) {
        showToast("ADMIN RECIPIENT ADDED");
        addAdminModal.classList.add("hidden");
        document.getElementById("input-admin-target").value = "";
        document.getElementById("input-admin-name").value = "";
        loadAdminRecipients();
        loadLiveStatus();
      } else {
        showToast(data.error || "FAILED TO ADD");
      }
    } catch (err) {
      showToast("CONNECTION ERROR");
    }
  });

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Start initialization and authentication check
  initializeAuthentication();
});
