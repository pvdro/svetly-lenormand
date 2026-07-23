/* Астромания — Mini App (облако + локальный режим) */
(function () {
  "use strict";

  const data = window.LENORMAND_DATA;
  if (!data || !data.deck) {
    document.body.innerHTML =
      "<div style='padding:24px;font-family:sans-serif'>Не загрузились данные колоды. Закройте и откройте снова.</div>";
    return;
  }

  const CFG = window.APP_CONFIG || {};
  const API_BASE = (CFG.API_BASE || "").replace(/\/$/, "");
  const API_TIMEOUT = CFG.API_TIMEOUT_MS || 8000;
  const I18N = window.ASTRO_I18N || { ru: {}, en: {} };
  const LS_LANG = "svetly_lang_v1";

  let uiLang = "ru";

  function detectLang() {
    try {
      const q = new URLSearchParams(location.search).get("lang");
      if (q && (q === "ru" || q === "en")) return q;
    } catch (_) {}
    try {
      const ls = localStorage.getItem(LS_LANG);
      if (ls === "ru" || ls === "en") return ls;
    } catch (_) {}
    const tgLang = window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe
      ? (window.Telegram.WebApp.initDataUnsafe.user || {}).language_code
      : null;
    if (tgLang && String(tgLang).toLowerCase().startsWith("en")) return "en";
    if (tgLang && String(tgLang).toLowerCase().startsWith("ru")) return "ru";
    return "ru";
  }

  function tr(key) {
    const pack = I18N[uiLang] || I18N.ru || {};
    return pack[key] || (I18N.ru && I18N.ru[key]) || key;
  }

  function tgUserName() {
    try {
      const u =
        (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) ||
        (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user);
      if (!u) return "";
      const n = (u.first_name || u.username || "").trim();
      if (!n || /астромания|astromania/i.test(n)) return "";
      return n;
    } catch (_) {
      return "";
    }
  }

  function applyHello() {
    const el = $("#hero-hello");
    if (!el) return;
    const name = tgUserName();
    if (!name) {
      el.textContent = "";
      el.classList.add("hidden");
      return;
    }
    el.classList.remove("hidden");
    el.textContent = tr("hello").replace("{name}", name);
  }

  function applyI18n() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const k = el.getAttribute("data-i18n");
      if (k) el.textContent = tr(k);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const k = el.getAttribute("data-i18n-placeholder");
      if (k) el.setAttribute("placeholder", tr(k));
    });
    document.querySelectorAll("[data-set-lang]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-set-lang") === uiLang);
    });
    document.documentElement.lang = uiLang;
    applyHello();
  }

  async function setLang(lang, { persist = true } = {}) {
    uiLang = lang === "en" ? "en" : "ru";
    try {
      localStorage.setItem(LS_LANG, uiLang);
    } catch (_) {}
    applyI18n();
    renderSpreads();
    if (persist && (await probeApi())) {
      try {
        await api("/api/lang", {
          method: "POST",
          body: JSON.stringify({ initData: initData(), lang: uiLang }),
        });
      } catch (_) {}
    }
  }

  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#FFF8F2");
      tg.setBackgroundColor("#FFF8F2");
      tg.MainButton.hide();
    } catch (_) {}
  }

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];

  let me = null;
  let apiOnline = null; // null unknown, true/false
  let lastSpreadId = null;
  let lastReadingId = null;
  let lastResultPayload = null;
  let pendingSpread = null;
  let localHistory = [];

  const LS_PROFILE = "svetly_profile_v2";
  const LS_HISTORY = "svetly_history_v2";
  const LS_QUESTION = "svetly_question_v1";

  const views = {
    home: $("#view-home"),
    draw: $("#view-draw"),
    result: $("#view-result"),
    profile: $("#view-profile"),
    profiles: $("#view-profiles"),
    compat: $("#view-compat"),
    history: $("#view-history"),
    transits: $("#view-transits"),
    journal: $("#view-journal"),
    premium: $("#view-premium"),
    library: $("#view-library"),
    card: $("#view-card"),
    about: $("#view-about"),
    ownerStats: $("#view-owner-stats"),
    invite: $("#view-invite"),
    thanks: $("#view-thanks"),
  };

  const TIP_PRESETS = [1, 5, 10, 25, 50, 100, 250];

  function initData() {
    if (tg && tg.initData) return tg.initData;
    // dev fallback only outside Telegram
    return "dev:10001";
  }

  function getQuestion() {
    const drawQ = $("#draw-question");
    const homeQ = $("#global-question");
    const fromDraw = drawQ && drawQ.value.trim();
    const fromHome = homeQ && homeQ.value.trim();
    const q = fromDraw || fromHome || "";
    return q.slice(0, 200);
  }

  function setQuestion(q) {
    const v = (q || "").slice(0, 200);
    const homeQ = $("#global-question");
    const drawQ = $("#draw-question");
    if (homeQ) homeQ.value = v;
    if (drawQ) drawQ.value = v;
    try {
      if (v) localStorage.setItem(LS_QUESTION, v);
      else localStorage.removeItem(LS_QUESTION);
    } catch (_) {}
  }

  function restoreQuestion() {
    try {
      const saved = localStorage.getItem(LS_QUESTION) || "";
      if (saved) setQuestion(saved);
    } catch (_) {}
  }

  function setStatus(aiText, premText) {
    const ai = $("#status-ai");
    const prem = $("#status-prem");
    if (ai) ai.textContent = aiText || "—";
    if (prem) prem.textContent = premText || "·";
  }

  function loadLocalProfile() {
    try {
      return JSON.parse(localStorage.getItem(LS_PROFILE) || "null");
    } catch (_) {
      return null;
    }
  }

  function saveLocalProfile(p) {
    localStorage.setItem(LS_PROFILE, JSON.stringify(p));
  }

  function loadLocalHistory() {
    try {
      localHistory = JSON.parse(localStorage.getItem(LS_HISTORY) || "[]");
    } catch (_) {
      localHistory = [];
    }
  }

  function pushHistory(item) {
    loadLocalHistory();
    localHistory.unshift(item);
    localHistory = localHistory.slice(0, 50);
    localStorage.setItem(LS_HISTORY, JSON.stringify(localHistory));
  }

  async function fetchWithTimeout(url, opts = {}, ms = API_TIMEOUT) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    try {
      return await fetch(url, { ...opts, signal: ctrl.signal });
    } finally {
      clearTimeout(t);
    }
  }

  async function api(path, opts = {}) {
    const url = (API_BASE || "") + path;
    const headers = {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData(),
      ...(opts.headers || {}),
    };
    const res = await fetchWithTimeout(url, { ...opts, headers });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(json.error || res.statusText || "Ошибка сервера");
      err.payload = json;
      err.status = res.status;
      throw err;
    }
    apiOnline = true;
    return json;
  }

  async function probeApi() {
    if (!API_BASE) {
      apiOnline = false;
      return false;
    }
    // 2 попытки — мобильные сети / холодный старт Railway
    for (let i = 0; i < 2; i++) {
      try {
        const res = await fetchWithTimeout(API_BASE + "/api/health", {}, i === 0 ? 4000 : 7000);
        if (res.ok) {
          apiOnline = true;
          return true;
        }
      } catch (_) {}
      if (i === 0) await new Promise((r) => setTimeout(r, 400));
    }
    apiOnline = false;
    return false;
  }

  function toast(msg) {
    try {
      if (tg && tg.showAlert) {
        tg.showAlert(String(msg).slice(0, 180));
        return;
      }
    } catch (_) {}
    // лёгкий toast без alert, если возможно
    let el = document.getElementById("toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), 2200);
  }

  function show(name) {
    Object.values(views).forEach((v) => v && v.classList.remove("active"));
    if (views[name]) views[name].classList.add("active");
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      tg && tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
    } catch (_) {}
  }

  function sample(arr, n) {
    const copy = arr.slice();
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy.slice(0, n);
  }

  function cardForDay(seedExtra) {
    const now = new Date();
    const key = `${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}-${seedExtra || ""}`;
    let h = 0;
    for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return data.deck[h % data.deck.length];
  }

  function localReadingText(spread, cards, question) {
    const parts = [];
    if (question) parts.push(`По вашему вопросу «${question}».`);
    cards.forEach((c, i) => {
      const pos = (spread.positions && spread.positions[i]) || `Карта ${i + 1}`;
      parts.push(`${pos}: ${c.name} — ${c.general}`);
    });
    if (cards[0]) parts.push(`Совет: ${cards[0].advice}`);
    parts.push("Это мягкое зеркало ситуации, не приговор.");
    return parts.join("\n\n");
  }

  function openPremium(msg) {
    if (msg) {
      try {
        tg && tg.showAlert && tg.showAlert(msg);
      } catch (_) {
        alert(msg);
      }
    }
    // оплата только через бота
    if (tg && tg.openTelegramLink) {
      tg.openTelegramLink("https://t.me/AstoManiabot?start=dostup");
    } else {
      show("premium");
      loadPlans();
    }
  }

  async function refreshMe() {
    const local = loadLocalProfile();
    try {
      if (local && local.sign) {
        const chip = $("#profile-chip");
        if (chip) chip.classList.remove("hidden");
        const s = $("#profile-chip-sign");
        const m = $("#profile-chip-meta");
        updateProfileChip(local);
        const sub = $("#asc-hero-sub");
        const cta = $("#asc-hero-cta");
        if (sub) {
          sub.textContent = uiLang === "en"
            ? `Sun · Moon · Rising — your personal day`
            : `Солнце · Луна · Восходящий — ваш личный день`;
        }
        if (cta) cta.textContent = tr("asc_cta");
      }

      setStatus("Проверяю связь…", "·");

      if (!(await probeApi())) {
        setStatus(tr("local_mode"), tr("status_local"));
        me = { premium: { active: false }, free_ai_used: 0, free_ai_limit: 3, profile: local, is_owner: false };
        toggleOwnerUi(false);
        return;
      }

      try {
        me = await api("/api/me");
        if (me.lang && (me.lang === "ru" || me.lang === "en") && me.lang !== uiLang) {
          await setLang(me.lang, { persist: false });
        }
        const prem = me.premium && me.premium.active;
        setStatus(
          prem
            ? uiLang === "en"
              ? "Reading: unlimited ⭐"
              : "Прогноз: без ограничения ⭐"
            : uiLang === "en"
              ? `Readings today: ${me.free_ai_used ?? 0}/${me.free_ai_limit ?? 3}`
              : `Прогнозов сегодня: ${me.free_ai_used ?? 0}/${me.free_ai_limit ?? 3}`,
          prem
            ? uiLang === "en"
              ? `Full access until ${String(me.premium.until).slice(0, 10)}`
              : `Полный доступ до ${String(me.premium.until).slice(0, 10)}`
            : tr("free")
        );
        toggleOwnerUi(!!me.is_owner);
        updateStreak(me.streak || 0);
        if (me.ref_code) window.__REF_CODE = me.ref_code;
        if (me.profile && me.profile.sign) {
          saveLocalProfile(me.profile);
          updateProfileChip(me.profile);
        }
      } catch (_) {
        me = { premium: { active: false }, free_ai_used: 0, free_ai_limit: 3, profile: local, is_owner: false };
        setStatus(tr("local_mode"), tr("status_need_tg"));
        toggleOwnerUi(false);
      }
    } catch (e) {
      setStatus(tr("local_mode"), "·");
      console.warn("refreshMe", e);
    }
  }

  function toggleOwnerUi(isOwner) {
    const btn = $("#btn-owner-stats");
    if (btn) btn.classList.toggle("hidden", !isOwner);
  }

  function updateProfileChip(p) {
    if (!p || !p.sign) return;
    const chip = $("#profile-chip");
    if (chip) chip.classList.remove("hidden");
    const s = $("#profile-chip-sign");
    const m = $("#profile-chip-meta");
    const b3 = $("#profile-chip-big3");
    if (s) {
      s.textContent = uiLang === "en"
        ? `${p.emoji || "✦"} Rising ${p.sign}`
        : `${p.emoji || "✦"} Восходящий: ${p.sign}`;
    }
    if (b3) {
      const sun = p.sun_sign ? `${p.sun_emoji || "☀️"} ${p.sun_sign}` : "";
      const moon = p.moon_sign ? `${p.moon_emoji || "🌙"} ${p.moon_sign}` : "";
      const asc = `${p.emoji || "⬆️"} ${p.sign}`;
      b3.textContent = [sun && `☀️ ${p.sun_sign}`, moon && `🌙 ${p.moon_sign}`, `⬆️ ${p.sign}`]
        .filter(Boolean)
        .join(" · ");
    }
    if (m) m.textContent = p.place || "";
  }

  function updateStreak(n) {
    const chip = $("#streak-chip");
    const txt = $("#streak-text");
    if (!chip || !txt) return;
    if (n && n > 0) {
      chip.classList.remove("hidden");
      txt.textContent = `🔥 ${n} ${tr("streak_label")}`;
    } else {
      chip.classList.add("hidden");
    }
  }

  function openQuick(id) {
    if (id === "day") openDay("day");
    else if (id === "t_day") startSpread("t_day");
    else if (id === "sun_day" || id === "moon_day" || id === "asc_day") openDay(id);
    else startSpread(id);
  }

  function openAstroDay(kind) {
    const p = loadLocalProfile();
    if (!p || !p.sign) {
      toast(tr("need_profile"));
      show("profile");
      return;
    }
    if (kind === "sun_day" && !p.sun_sign) {
      // старый профиль без солнца — пересчитать
      toast(tr("need_profile"));
      show("profile");
      return;
    }
    if (kind === "moon_day" && !p.moon_sign) {
      toast(tr("need_profile"));
      show("profile");
      return;
    }
    openDay(kind);
  }

  function handleDeepLink() {
    let spread = null;
    try {
      const q = new URLSearchParams(location.search);
      spread = q.get("spread") || q.get("startapp") || q.get("startApp");
    } catch (_) {}
    try {
      const sp = tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param;
      if (sp) spread = sp;
    } catch (_) {}
    if (!spread) return;
    spread = String(spread).toLowerCase();
    const map = {
      day: "day",
      t_day: "t_day",
      tarot: "t_day",
      three: "three",
      love: "love",
      yesno: "yesno",
      work: "work",
      situation: "situation",
      path: "path",
      asc: "asc_day",
      asc_day: "asc_day",
    };
    const sid = map[spread] || spread;
    setTimeout(() => {
      if (sid === "day" || sid === "asc_day") openDay(sid);
      else if ((data.spreads || []).some((s) => s.id === sid)) startSpread(sid);
    }, 400);
  }

  function renderSpreads() {
    const grid = $("#spread-grid");
    grid.innerHTML = "";
    const all = (data.spreads || []).filter((s) => !["day", "asc_day"].includes(s.id));
    const groups = [
      {
        key: "lenormand",
        title: tr("group_lenormand"),
        items: all.filter((s) => (s.system || "lenormand") !== "tarot"),
      },
      {
        key: "tarot",
        title: tr("group_tarot"),
        items: all.filter((s) => s.system === "tarot"),
      },
    ];
    groups.forEach((g) => {
      if (!g.items.length) return;
      const h = document.createElement("div");
      h.className = "spread-group-title";
      h.textContent = g.title;
      grid.appendChild(h);
      g.items.forEach((s) => {
        const prem = !!s.premium;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "spread-tile";
        const title = uiLang === "en" && s.title_en ? s.title_en : s.title;
        const blurb = uiLang === "en" && s.blurb_en ? s.blurb_en : s.blurb;
        const cardsWord = uiLang === "en" ? "cards" : "карт";
        btn.innerHTML = `
          <span class="emoji">${s.emoji}</span>
          <div class="title">${title}${prem ? ` <span class="pill-mini">${tr("full")}</span>` : ""}</div>
          <div class="meta">${s.n} ${cardsWord} · ${blurb}</div>`;
        btn.addEventListener("click", () => {
          if (s.id === "compat") {
            show("compat");
            return;
          }
          startSpread(s.id);
        });
        grid.appendChild(btn);
      });
    });
  }

  function startSpread(spreadId) {
    const s = (data.spreads || []).find((x) => x.id === spreadId);
    if (!s) {
      alert("Расклад не найден. Обновите приложение.");
      return;
    }
    pendingSpread = s;
    lastSpreadId = spreadId;
    const title = $("#draw-title");
    const blurb = $("#draw-blurb");
    if (title) title.textContent = `${s.emoji || ""} ${s.title}`.trim();
    if (blurb) blurb.textContent = s.blurb || "";
    // синхронизируем вопрос: home → draw
    const q = getQuestion();
    setQuestion(q);
    const drawQhint = $("#draw-q");
    if (drawQhint) drawQhint.textContent = q ? tr("q_hint_set") : tr("q_hint_empty");
    const sh = $("#shuffle-label");
    if (sh) sh.textContent = tr("shuffle");
    const btn = $("#btn-shuffle");
    if (btn) btn.disabled = false;
    const pile = $("#deck-pile");
    if (pile) pile.classList.remove("shuffling");
    show("draw");
    // фокус на вопрос, если пустой — удобнее ввести
    setTimeout(() => {
      const dq = $("#draw-question");
      if (dq && !dq.value.trim()) {
        try {
          dq.focus();
        } catch (_) {}
      }
    }, 200);
  }

  async function runDraw() {
    if (!pendingSpread) return;
    const btn = $("#btn-shuffle");
    if (btn) btn.disabled = true;
    const sh = $("#shuffle-label");
    if (sh) sh.textContent = tr("shuffle_doing");
    const pile = $("#deck-pile");
    if (pile) pile.classList.add("shuffling");

    // финальный вопрос с экрана тасования
    const question = getQuestion() || null;
    setQuestion(question || "");

    try {
      let r;
      if (apiOnline || (await probeApi())) {
        try {
          r = await api("/api/draw", {
            method: "POST",
            body: JSON.stringify({
              initData: initData(),
              spread_id: pendingSpread.id,
              question,
              ai: true,
            }),
          });
        } catch (e) {
          if (e.payload && e.payload.premium_required) {
            openPremium(e.message);
            return;
          }
          console.warn("draw api fail, local fallback", e);
          r = null;
        }
      }

      if (!r) {
        const deckSrc = pendingSpread.system === "tarot" ? data.tarot || data.deck : data.deck;
        const n = pendingSpread.n || pendingSpread.n_cards || 3;
        const cards = sample(deckSrc, n);
        const text = localReadingText(pendingSpread, cards, question);
        r = {
          reading_id: Date.now(),
          spread_id: pendingSpread.id,
          title: pendingSpread.title,
          emoji: pendingSpread.emoji,
          blurb: pendingSpread.blurb,
          positions: pendingSpread.positions,
          cards,
          question,
          ai_text: text,
          ai: false,
          provider: "local",
        };
        pushHistory({
          title: r.title,
          day_key: new Date().toISOString().slice(0, 10),
          cards,
          ai_text: text,
          question,
        });
      }

      // если API не вернул question — подставим свой
      if (!r.question && question) r.question = question;

      if (pile) pile.classList.remove("shuffling");
      showResult(r);
      refreshMe();
    } catch (e) {
      if (pile) pile.classList.remove("shuffling");
      alert(e.message || "Ошибка");
    } finally {
      if (btn) btn.disabled = false;
      if (sh) sh.textContent = tr("shuffle");
    }
  }

  function showResult(r) {
    lastReadingId = r.reading_id;
    lastResultPayload = r;
    const rt = $("#result-title");
    if (rt) rt.textContent = `${r.emoji || ""} ${r.title || "Расклад"}`.trim();

    const rb = $("#result-blurb");
    if (rb) {
      if (r.question) rb.innerHTML = `<strong>${tr("question_prefix")}</strong> ${escapeHtml(r.question)}`;
      else rb.textContent = r.blurb || r.day_key || "";
    }

    const list = $("#result-cards");
    if (list) {
      list.innerHTML = "";
      const positions = r.positions || [];
      (r.cards || []).forEach((card, i) => {
        const el = document.createElement("article");
        el.className = "reading-card";
        const body = card.general || card.upright || "";
        el.innerHTML = `
          <div class="pos-label">${escapeHtml(positions[i] || "Карта " + (i + 1))}</div>
          <div class="card-face">
            <div class="card-visual">
              <span class="em">${card.emoji || "✦"}</span>
              <span class="num">${card.number != null ? card.number : ""}</span>
              <span class="nm">${escapeHtml(card.name || "")}</span>
            </div>
            <div class="card-body">
              <h3>${escapeHtml(card.name || "")}</h3>
              <p class="kw">${escapeHtml(card.keywords || "")}</p>
              <p class="txt">${escapeHtml(body)}</p>
            </div>
          </div>`;
        list.appendChild(el);
      });
    }

    const aiBox = $("#ai-box");
    if (aiBox) aiBox.classList.remove("hidden");
    const aiLoad = $("#ai-loading");
    if (aiLoad) aiLoad.classList.add("hidden");
    const aiText = $("#ai-text");
    if (aiText) aiText.textContent = r.ai_text || "Прогноз появится здесь.";
    const aiMeta = $("#ai-meta");
    if (aiMeta) {
      aiMeta.textContent = r.ai
        ? tr("live_reading")
        : r.provider === "local"
          ? tr("local_reading")
          : tr("short_reading");
    }

    const jr = $("#journal-rate");
    if (jr) jr.classList.add("hidden");
    show("result");
    try {
      tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred("success");
    } catch (_) {}
  }

  function shareStoryText() {
    const r = lastResultPayload;
    if (!r) return;
    const names = (r.cards || []).map((c) => `${c.emoji || ""} ${c.name}`).join(", ");
    const q = r.question ? (uiLang === "en" ? `Question: ${r.question}\n` : `Вопрос: ${r.question}\n`) : "";
    const brand = uiLang === "en" ? "Astromania" : "Астромания";
    const text =
      uiLang === "en"
        ? `${brand} ✨\n${r.title || "Reading"}\n${q}${names}\n\nt.me/${CFG.BOT_USERNAME || "AstoManiabot"}`
        : `${brand} ✨\n${r.title || "Расклад"}\n${q}${names}\n\nt.me/${CFG.BOT_USERNAME || "AstoManiabot"}`;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        toast(uiLang === "en" ? "Copied — paste into Stories" : "Скопировано — вставьте в Stories");
      }).catch(() => toast(text.slice(0, 120)));
    } else {
      toast(text.slice(0, 120));
    }
    // also try telegram share if available
    try {
      if (tg && tg.openTelegramLink) {
        const url = `https://t.me/share/url?url=${encodeURIComponent("https://t.me/" + (CFG.BOT_USERNAME || "AstoManiabot"))}&text=${encodeURIComponent(text)}`;
        // don't auto-open; user uses copy. optional second button already
      }
    } catch (_) {}
  }

  async function showInvite() {
    let code = window.__REF_CODE;
    if (!code && (await probeApi())) {
      try {
        const me2 = await api("/api/me");
        code = me2.ref_code;
        window.__REF_CODE = code;
      } catch (_) {}
    }
    code = code || "friend";
    const link = `https://t.me/${CFG.BOT_USERNAME || "AstoManiabot"}?start=ref_${code}`;
    const el = $("#invite-link");
    if (el) el.textContent = link;
    show("invite");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadOwnerStats() {
    const box = $("#owner-stats-text");
    if (box) box.textContent = "Загрузка…";
    show("ownerStats");
    try {
      if (!(await probeApi())) {
        if (box) box.textContent = "Сервер недоступен. Статистика только онлайн.";
        return;
      }
      const r = await api("/api/admin/stats");
      if (box) box.textContent = r.text || JSON.stringify(r, null, 2);
    } catch (e) {
      if (box) box.textContent = e.message || "Нет доступа. Нужен ADMIN_IDS на сервере.";
    }
  }

  async function openDay(kind) {
    // try server first for once-per-day + AI
    if (await probeApi()) {
      try {
        const r = await api("/api/reading/day", {
          method: "POST",
          body: JSON.stringify({ initData: initData(), kind }),
        });
        showResult({
          ...r,
          emoji: kind === "asc_day" ? "🌅" : "☀️",
          title: r.title,
          positions: ["Послание дня"],
        });
        refreshMe();
        return;
      } catch (e) {
        if (e.payload && e.payload.need_profile) {
          show("profile");
          return;
        }
        if (e.payload && e.payload.premium_required) {
          openPremium(e.message);
          return;
        }
        // fall through local
      }
    }

    if (kind === "asc_day" || kind === "sun_day" || kind === "moon_day") {
      const p = loadLocalProfile();
      if (!p || !p.sign) {
        show("profile");
        return;
      }
      let sign = p.sign;
      let emoji = p.emoji || "✦";
      let title = uiLang === "en" ? `Day by rising · ${sign}` : `День по восходящему · ${sign}`;
      let pos = uiLang === "en" ? "Rising day" : "День ASC";
      if (kind === "sun_day") {
        sign = p.sun_sign || p.sign;
        emoji = p.sun_emoji || "☀️";
        title = uiLang === "en" ? `Day by Sun · ${sign}` : `День по Солнцу · ${sign}`;
        pos = uiLang === "en" ? "Solar day" : "Солнечный день";
      } else if (kind === "moon_day") {
        sign = p.moon_sign || p.sign;
        emoji = p.moon_emoji || "🌙";
        title = uiLang === "en" ? `Day by Moon · ${sign}` : `День по Луне · ${sign}`;
        pos = uiLang === "en" ? "Lunar day" : "Лунный день";
      }
      const card = cardForDay(sign + kind);
      const day = (data.ascDay && data.ascDay[sign]) || {};
      const label =
        kind === "sun_day" ? (uiLang === "en" ? "Sun" : "Солнце")
        : kind === "moon_day" ? (uiLang === "en" ? "Moon" : "Луна")
        : (uiLang === "en" ? "Rising" : "Восходящий");
      const text = [
        `${emoji} ${label}: ${sign}`,
        day.mood || "",
        day.body || "",
        day.focus ? (uiLang === "en" ? `Focus: ${day.focus}` : `Фокус: ${day.focus}`) : "",
        day.care ? (uiLang === "en" ? `Care: ${day.care}` : `Забота: ${day.care}`) : "",
        uiLang === "en"
          ? `Card: ${card.name} — ${card.general}`
          : `Карта: ${card.name} — ${card.general}`,
        uiLang === "en" ? `Advice: ${card.advice}` : `Совет: ${card.advice}`,
      ]
        .filter(Boolean)
        .join("\n\n");
      showResult({
        title,
        emoji: kind === "sun_day" ? "☀️" : kind === "moon_day" ? "🌙" : "🌅",
        cards: [card],
        positions: [pos],
        ai_text: text,
        ai: false,
        provider: "local",
      });
      return;
    }

    const card = cardForDay("day");
    showResult({
      title: "Карта дня",
      emoji: "☀️",
      cards: [card],
      positions: ["Послание дня"],
      ai_text: `${card.general}\n\nСовет: ${card.advice}`,
      ai: false,
      provider: "local",
    });
  }

  // Profile: try server ASC, else manual sign pick stored as profile
  $("#profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#form-error");
    err.classList.add("hidden");
    $("#calc-label").textContent = "Считаю…";
    $("#btn-calc-asc").disabled = true;
    const payload = {
      initData: initData(),
      date: $("#f-date").value,
      time: $("#f-time").value,
      place: $("#f-place").value.trim(),
      label: $("#f-label").value.trim() || "Я",
      make_default: true,
    };
    try {
      if (await probeApi()) {
        const r = await api("/api/ascendant", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        saveLocalProfile(r);
        await openDay("asc_day");
      } else {
        // без сервера: просим выбрать знак вручную (точность ниже)
        err.textContent =
          "Сервер расчёта недоступен. Введите в поле «место» так: знак Лев — или откройте позже, когда сеть позволит.";
        err.classList.remove("hidden");
        const place = payload.place || "";
        const m = place.match(/знак\s+(\S+)/i) || place.match(/^(Овен|Телец|Близнецы|Рак|Лев|Дева|Весы|Скорпион|Стрелец|Козерог|Водолей|Рыбы)$/i);
        if (m) {
          const sign = m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase();
          const emoji = (data.signs || []).find((s) => s.name === sign)?.emoji || "✦";
          saveLocalProfile({
            sign,
            emoji,
            degree_in_sign: 15,
            place: payload.place,
            birth_date: payload.date,
            birth_time: payload.time,
          });
          await openDay("asc_day");
        }
      }
    } catch (ex) {
      err.textContent = ex.message;
      err.classList.remove("hidden");
    } finally {
      $("#btn-calc-asc").disabled = false;
      $("#calc-label").textContent = "Рассчитать восходящий знак";
    }
  });

  async function loadHistory() {
    const box = $("#history-list");
    box.innerHTML = "";
    if (await probeApi()) {
      try {
        const r = await api("/api/history");
        (r.items || []).forEach((it) => {
          const d = document.createElement("div");
          d.className = "history-item";
          const cards = (it.cards || []).map((c) => c.emoji || c.name).join(" ");
          d.innerHTML = `<strong>${it.title}</strong><div class="muted">${it.day_key || ""} · ${cards}</div>
            <p class="hist-preview">${(it.ai_text || "").slice(0, 160)}</p>`;
          box.appendChild(d);
        });
        if (!(r.items || []).length) box.innerHTML = "<p class='muted'>Пока пусто.</p>";
        show("history");
        return;
      } catch (_) {}
    }
    loadLocalHistory();
    if (!localHistory.length) box.innerHTML = "<p class='muted'>Пока пусто — сделайте расклад.</p>";
    localHistory.forEach((it) => {
      const d = document.createElement("div");
      d.className = "history-item";
      d.innerHTML = `<strong>${it.title}</strong><div class="muted">${it.day_key || ""}</div>
        <p class="hist-preview">${(it.ai_text || "").slice(0, 160)}</p>`;
      box.appendChild(d);
    });
    show("history");
  }

  async function loadTransits() {
    if (await probeApi()) {
      try {
        const r = await api("/api/transits");
        $("#transits-note").textContent = r.note || "";
        const box = $("#transits-list");
        box.innerHTML = "";
        (r.days || []).forEach((day) => {
          const el = document.createElement("div");
          el.className = "transit-day";
          el.innerHTML = `<strong>${day.label}</strong>
            <div class="muted">Луна в ${day.moon_sign} · Солнце в ${day.sun_sign}</div>
            <p>${day.tip}</p>`;
          box.appendChild(el);
        });
        show("transits");
        return;
      } catch (_) {}
    }
    $("#transits-note").textContent =
      "Точный календарь неба сейчас недоступен (нет связи с сервером). Расклады в приложении работают.";
    $("#transits-list").innerHTML = "";
    show("transits");
  }

  async function loadPlans() {
    const box = $("#plans-list");
    box.innerHTML = "";
    const plans = [
      { title: "Полный доступ на 7 дней", description: "Без ограничения прогнозов", stars: 50 },
      { title: "Полный доступ на 30 дней", description: "Выгоднее на месяц", stars: 150 },
      { title: "Глубокий разбор (разово)", description: "Сутки расширенного доступа", stars: 25 },
    ];
    if (await probeApi()) {
      try {
        const r = await api("/api/plans");
        if (r.plans) plans.splice(0, plans.length, ...r.plans);
      } catch (_) {}
    }
    plans.forEach((p) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "plan-card";
      el.innerHTML = `<div class="title">${p.title}</div>
        <div class="meta">${p.description || ""}</div>
        <div class="price">⭐ ${p.stars} звёзд</div>`;
      el.addEventListener("click", () => {
        if (tg && tg.openTelegramLink) tg.openTelegramLink("https://t.me/AstoManiabot?start=dostup");
        else window.open("https://t.me/AstoManiabot?start=dostup", "_blank");
      });
      box.appendChild(el);
    });
  }

  let libSystem = "lenormand";

  function renderLibrary(system) {
    if (system) libSystem = system;
    const grid = $("#lib-grid");
    grid.innerHTML = "";
    const tabs = $("#lib-tabs");
    if (tabs) {
      tabs.querySelectorAll("[data-lib]").forEach((el) => {
        el.classList.toggle("active", el.getAttribute("data-lib") === libSystem);
      });
    }
    const list = libSystem === "tarot" ? data.tarot || [] : data.deck || [];
    list.forEach((c, idx) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "lib-item";
      const num = libSystem === "tarot" ? idx + 1 : c.number;
      b.innerHTML = `<span class="em">${c.emoji}</span><span class="n">${num}</span><span class="nm">${c.name}</span>`;
      b.addEventListener("click", () => {
        const body = c.upright || c.general || "";
        let html = `
          <div class="detail-visual"><span class="em">${c.emoji}</span><span class="num">${c.name}</span></div>
          <div class="detail-block"><h4>Ключевые слова</h4><p>${c.keywords || "—"}</p></div>
          <div class="detail-block"><h4>Значение</h4><p>${body}</p></div>
          <div class="detail-block"><h4>Совет</h4><p>${c.advice || "—"}</p></div>`;
        if (c.love) html += `<div class="detail-block"><h4>Любовь</h4><p>${c.love}</p></div>`;
        if (c.work) html += `<div class="detail-block"><h4>Дело</h4><p>${c.work}</p></div>`;
        $("#card-detail").innerHTML = html;
        show("card");
      });
      grid.appendChild(b);
    });
  }

  function shareCard() {
    const r = lastResultPayload;
    if (!r) return;
    const canvas = $("#share-canvas");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const g = ctx.createLinearGradient(0, 0, w, h);
    g.addColorStop(0, "#fff8f2");
    g.addColorStop(1, "#efe3ff");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#3a2f36";
    ctx.font = "600 48px Georgia, serif";
    ctx.fillText(uiLang === "en" ? "Astromania" : "Астромания", 80, 120);
    ctx.font = "28px sans-serif";
    ctx.fillStyle = "#9a8790";
    ctx.fillText(r.title || (uiLang === "en" ? "Reading" : "Расклад"), 80, 180);
    if (r.question) {
      ctx.font = "22px sans-serif";
      ctx.fillStyle = "#6b5a63";
      const qline = (r.question || "").slice(0, 48);
      ctx.fillText(qline, 80, 230);
    }
    (r.cards || []).slice(0, 3).forEach((c, i) => {
      const x = 80 + i * 300;
      const y = 320;
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.roundRect(x, y, 260, 320, 28);
      ctx.fill();
      ctx.font = "72px serif";
      ctx.fillStyle = "#3a2f36";
      ctx.fillText(c.emoji || "✦", x + 90, y + 140);
      ctx.font = "26px sans-serif";
      ctx.fillText(c.name || "", x + 40, y + 220);
    });
    ctx.fillStyle = "#d4a574";
    ctx.font = "24px sans-serif";
    ctx.fillText("t.me/AstoManiabot", 80, h - 80);
    canvas.toBlob(async (blob) => {
      if (!blob) return;
      const file = new File([blob], "lenormand.png", { type: "image/png" });
      if (navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file], title: "Астромания" });
          return;
        } catch (_) {}
      }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "lenormand.png";
      a.click();
    });
  }

  function speak() {
    const text = $("#ai-text").textContent || "";
    if (!text || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.slice(0, 1500));
    u.lang = "ru-RU";
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  }

  // events
  $("#btn-day").addEventListener("click", () => openDay("day"));
  const btnTarotDay = $("#btn-tarot-day");
  if (btnTarotDay) {
    btnTarotDay.addEventListener("click", () => startSpread("t_day"));
  }
  $("#btn-asc-day").addEventListener("click", () => {
    const p = loadLocalProfile();
    if (p && p.sign) openDay("asc_day");
    else show("profile");
  });
  $("#btn-edit-profile").addEventListener("click", () => show("profile"));
  $("#btn-shuffle").addEventListener("click", runDraw);
  $("#btn-again").addEventListener("click", () => {
    if (lastSpreadId && lastSpreadId !== "day" && lastSpreadId !== "asc_day") startSpread(lastSpreadId);
    else show("home");
  });
  $("#btn-share").addEventListener("click", shareCard);
  $("#btn-speak").addEventListener("click", speak);
  $("#btn-history").addEventListener("click", loadHistory);
  $("#btn-transits").addEventListener("click", loadTransits);
  $("#btn-journal").addEventListener("click", () => {
    openPremium("Дневник доступен в полном доступе через бота");
  });
  $("#btn-premium").addEventListener("click", () => {
    loadPlans();
    show("premium");
  });
  $("#btn-profiles").addEventListener("click", () => {
    const p = loadLocalProfile();
    const box = $("#profiles-list");
    box.innerHTML = p
      ? `<div class="history-item"><strong>${p.sign}</strong><div class="muted">${p.place || ""}</div></div>`
      : "<p class='muted'>Профиля пока нет.</p>";
    show("profiles");
  });
  $("#btn-new-profile").addEventListener("click", () => show("profile"));
  $("#btn-library").addEventListener("click", () => {
    renderLibrary("lenormand");
    show("library");
  });
  const libTabs = $("#lib-tabs");
  if (libTabs) {
    libTabs.querySelectorAll("[data-lib]").forEach((el) => {
      el.addEventListener("click", () => renderLibrary(el.getAttribute("data-lib")));
    });
  }
  $("#btn-about").addEventListener("click", () => show("about"));

  function openSupport() {
    // только бот — без перехода в личный профиль автора
    const bot = CFG.SUPPORT_BOT || "https://t.me/AstoManiabot?start=podderzhka";
    if (tg && tg.openTelegramLink) tg.openTelegramLink(bot);
    else window.open(bot, "_blank");
  }
  const btnSupport = $("#btn-support");
  if (btnSupport) btnSupport.addEventListener("click", openSupport);
  const btnSupportAbout = $("#btn-support-about");
  if (btnSupportAbout) btnSupportAbout.addEventListener("click", openSupport);

  function payTipStars(n) {
    const stars = parseInt(n, 10);
    if (!stars || stars < 1 || stars > 100000) {
      alert(tr("thanks_bad"));
      return;
    }
    const bot = CFG.BOT_USERNAME || "AstoManiabot";
    // deep-link: бот сразу выставит счёт на N звёзд
    const url = `https://t.me/${bot}?start=tip_${stars}`;
    if (tg && tg.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, "_blank");
  }

  function renderTipGrid() {
    const grid = $("#tip-grid");
    if (!grid) return;
    grid.innerHTML = "";
    TIP_PRESETS.forEach((n) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tip-tile";
      b.innerHTML = `<span class="stars">⭐</span>${n}`;
      b.addEventListener("click", () => payTipStars(n));
      grid.appendChild(b);
    });
  }

  function openThanks() {
    renderTipGrid();
    show("thanks");
  }
  const btnThanks = $("#btn-thanks");
  if (btnThanks) btnThanks.addEventListener("click", openThanks);
  const btnResultThanks = $("#btn-result-thanks");
  if (btnResultThanks) btnResultThanks.addEventListener("click", openThanks);
  const btnTipCustom = $("#btn-tip-custom");
  if (btnTipCustom) {
    btnTipCustom.addEventListener("click", () => {
      const el = $("#tip-custom");
      payTipStars(el && el.value);
    });
  }
  const btnShareStory = $("#btn-result-share-text");
  if (btnShareStory) btnShareStory.addEventListener("click", shareStoryText);

  document.querySelectorAll("[data-quick]").forEach((btn) => {
    btn.addEventListener("click", () => openQuick(btn.getAttribute("data-quick")));
  });
  document.querySelectorAll("[data-astro-day]").forEach((btn) => {
    btn.addEventListener("click", () => openAstroDay(btn.getAttribute("data-astro-day")));
  });

  const btnInvite = $("#btn-invite");
  if (btnInvite) btnInvite.addEventListener("click", showInvite);
  const btnCopyInvite = $("#btn-copy-invite");
  if (btnCopyInvite) {
    btnCopyInvite.addEventListener("click", () => {
      const link = ($("#invite-link") && $("#invite-link").textContent) || "";
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(() => toast(tr("invite_copied")));
      } else toast(link);
    });
  }
  const btnNotify = $("#btn-notify");
  if (btnNotify) {
    btnNotify.addEventListener("click", () => {
      const bot = CFG.BOT_USERNAME || "AstoManiabot";
      const url = `https://t.me/${bot}?start=notify`;
      if (tg && tg.openTelegramLink) tg.openTelegramLink(url);
      else window.open(url, "_blank");
    });
  }


  const btnOwner = $("#btn-owner-stats");
  if (btnOwner) btnOwner.addEventListener("click", loadOwnerStats);
  const btnOwnerRefresh = $("#btn-owner-stats-refresh");
  if (btnOwnerRefresh) btnOwnerRefresh.addEventListener("click", loadOwnerStats);

  // синхронизация полей вопроса
  ["global-question", "draw-question"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", () => setQuestion(el.value));
    el.addEventListener("change", () => setQuestion(el.value));
  });

  $("#btn-compat-go").addEventListener("click", () => {
    const cq = $("#compat-q");
    if (cq) setQuestion(cq.value.trim());
    startSpread("compat");
  });

  $$("[data-go]").forEach((el) => {
    el.addEventListener("click", () => {
      const go = el.getAttribute("data-go");
      if (go === "library") {
        renderLibrary();
        show("library");
      } else if (go === "ownerStats") {
        loadOwnerStats();
      } else show(go);
    });
  });

  async function loadPublicConfig() {
    try {
      if (!(await probeApi())) return;
      const r = await fetchWithTimeout(API_BASE + "/api/public-config", {}, 5000).then((x) => x.json());
      // username автора намеренно не подставляем
      if (r.support_bot) CFG.SUPPORT_BOT = r.support_bot;
    } catch (_) {}
  }

  // language buttons
  document.querySelectorAll("[data-set-lang]").forEach((btn) => {
    btn.addEventListener("click", () => setLang(btn.getAttribute("data-set-lang")));
  });

  // boot
  uiLang = detectLang();
  applyI18n();
  setStatus(tr("status_loading"), "·");
  restoreQuestion();
  renderSpreads();
  show("home");
  loadPublicConfig().finally(() => refreshMe().then(() => handleDeepLink()));
})();
