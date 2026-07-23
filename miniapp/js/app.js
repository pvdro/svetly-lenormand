/* Светлый Ленорман — full Mini App */
(function () {
  "use strict";

  const data = window.LENORMAND_DATA;
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
  let lastSpreadId = null;
  let lastReadingId = null;
  let lastResultPayload = null;
  let pendingSpread = null;
  let profiles = [];

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
  };

  function initData() {
    if (tg && tg.initData) return tg.initData;
    // dev fallback
    return "dev:10001";
  }

  async function api(path, opts = {}) {
    const headers = {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData(),
      ...(opts.headers || {}),
    };
    const res = await fetch(path, { ...opts, headers });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(json.error || res.statusText);
      err.payload = json;
      err.status = res.status;
      throw err;
    }
    return json;
  }

  function show(name) {
    Object.values(views).forEach((v) => v && v.classList.remove("active"));
    if (views[name]) views[name].classList.add("active");
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      tg && tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
    } catch (_) {}
  }

  function openPremium(msg) {
    if (msg) {
      try {
        tg && tg.showAlert && tg.showAlert(msg);
      } catch (_) {
        alert(msg);
      }
    }
    loadPlans();
    show("premium");
  }

  async function refreshMe() {
    try {
      me = await api("/api/me");
      const prem = me.premium && me.premium.active;
      $("#status-ai").textContent = prem
        ? "ИИ: безлимит ⭐"
        : `ИИ сегодня: ${me.free_ai_used}/${me.free_ai_limit}`;
      $("#status-prem").textContent = prem
        ? `Premium до ${String(me.premium.until).slice(0, 10)}`
        : "Free";
      if (me.profile && me.profile.sign) {
        $("#profile-chip").classList.remove("hidden");
        $("#profile-chip-sign").textContent = `${me.profile.emoji || "✦"} ASC ${me.profile.sign}`;
        $("#profile-chip-meta").textContent = me.profile.place || "";
        $("#asc-hero-sub").textContent = `ASC ${me.profile.sign} — ваш день с ИИ`;
        $("#asc-hero-cta").textContent = "Открыть день ↗";
      }
    } catch (e) {
      $("#status-ai").textContent = "Гость / без Telegram auth";
      $("#status-prem").textContent = "";
    }
  }

  function renderSpreads() {
    const grid = $("#spread-grid");
    grid.innerHTML = "";
    const list = (data && data.spreads) || [];
    list
      .filter((s) => !["day", "asc_day"].includes(s.id))
      .forEach((s) => {
        const prem = ["path", "week", "month", "compat", "deep"].includes(s.id);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "spread-tile";
        btn.innerHTML = `
          <span class="emoji">${s.emoji}</span>
          <div class="title">${s.title}${prem ? ' <span class="pill-mini">PRO</span>' : ""}</div>
          <div class="meta">${s.n} карт · ${s.blurb}</div>
        `;
        btn.addEventListener("click", () => {
          if (s.id === "compat") {
            openCompat();
            return;
          }
          startSpread(s.id);
        });
        grid.appendChild(btn);
      });
  }

  function startSpread(spreadId) {
    const s = (data.spreads || []).find((x) => x.id === spreadId);
    if (!s) return;
    pendingSpread = s;
    lastSpreadId = spreadId;
    $("#draw-title").textContent = `${s.emoji} ${s.title}`;
    $("#draw-blurb").textContent = s.blurb;
    const q = $("#global-question").value.trim();
    $("#draw-q").textContent = q ? `Вопрос: ${q}` : "";
    $("#shuffle-label").textContent = "Перетасовать и вытянуть";
    $("#btn-shuffle").disabled = false;
    $("#deck-pile").classList.remove("shuffling");
    show("draw");
  }

  async function runDraw() {
    if (!pendingSpread) return;
    const btn = $("#btn-shuffle");
    btn.disabled = true;
    $("#shuffle-label").textContent = "Тасую и пишу прогноз…";
    $("#deck-pile").classList.add("shuffling");
    try {
      const body = {
        initData: initData(),
        spread_id: pendingSpread.id,
        question: $("#global-question").value.trim() || null,
        ai: true,
      };
      const r = await api("/api/draw", { method: "POST", body: JSON.stringify(body) });
      $("#deck-pile").classList.remove("shuffling");
      showResult(r);
      refreshMe();
    } catch (e) {
      $("#deck-pile").classList.remove("shuffling");
      btn.disabled = false;
      $("#shuffle-label").textContent = "Перетасовать и вытянуть";
      if (e.payload && e.payload.premium_required) {
        openPremium(e.message);
      } else {
        alert(e.message || "Ошибка");
      }
    }
  }

  function showResult(r) {
    lastReadingId = r.reading_id;
    lastResultPayload = r;
    $("#result-title").textContent = `${r.emoji || ""} ${r.title || "Расклад"}`.trim();
    $("#result-blurb").textContent = r.question
      ? `Вопрос: ${r.question}`
      : r.blurb || r.day_key || "";
    const list = $("#result-cards");
    list.innerHTML = "";
    const positions = r.positions || [];
    (r.cards || []).forEach((card, i) => {
      const el = document.createElement("article");
      el.className = "reading-card";
      el.innerHTML = `
        <div class="pos-label">${positions[i] || "Карта " + (i + 1)}</div>
        <div class="card-face">
          <div class="card-visual">
            <span class="em">${card.emoji}</span>
            <span class="num">${card.number}</span>
            <span class="nm">${card.name}</span>
          </div>
          <div class="card-body">
            <h3>${card.name}</h3>
            <p class="kw">${card.keywords || ""}</p>
            <p class="txt">${card.general || ""}</p>
          </div>
        </div>`;
      list.appendChild(el);
    });

    const aiBox = $("#ai-box");
    aiBox.classList.remove("hidden");
    $("#ai-loading").classList.add("hidden");
    if (r.ai_text) {
      $("#ai-text").textContent = r.ai_text;
      $("#ai-meta").textContent = r.ai
        ? `модель: ${r.provider || ""}${r.model ? " / " + r.model : ""}${r.cached ? " · кэш дня" : ""}`
        : "офлайн / лимит";
    } else if (r.limit) {
      $("#ai-text").textContent = r.limit.message || "Лимит ИИ на сегодня.";
      $("#ai-meta").textContent = "откройте Premium ⭐";
    } else {
      $("#ai-text").textContent = "Текст появится здесь.";
    }

    const jr = $("#journal-rate");
    if (me && me.premium && me.premium.active && lastReadingId) jr.classList.remove("hidden");
    else jr.classList.add("hidden");

    show("result");
    try {
      tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred("success");
    } catch (_) {}
  }

  async function openDay(kind) {
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
    } catch (e) {
      if (e.payload && e.payload.need_profile) {
        show("profile");
      } else if (e.payload && e.payload.premium_required) {
        openPremium(e.message);
      } else {
        alert(e.message || "Ошибка");
      }
    }
  }

  // Profile form
  $("#profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#form-error");
    err.classList.add("hidden");
    $("#calc-label").textContent = "Считаю…";
    $("#btn-calc-asc").disabled = true;
    try {
      const payload = {
        initData: initData(),
        date: $("#f-date").value,
        time: $("#f-time").value,
        place: $("#f-place").value.trim(),
        label: $("#f-label").value.trim() || "Я",
        make_default: true,
      };
      const r = await api("/api/ascendant", { method: "POST", body: JSON.stringify(payload) });
      await refreshMe();
      await openDay("asc_day");
    } catch (ex) {
      err.textContent = ex.message;
      err.classList.remove("hidden");
    } finally {
      $("#btn-calc-asc").disabled = false;
      $("#calc-label").textContent = "Рассчитать асцендент";
    }
  });

  async function loadHistory() {
    try {
      const r = await api("/api/history");
      const box = $("#history-list");
      box.innerHTML = "";
      if (!r.items.length) {
        box.innerHTML = "<p class='muted'>Пока пусто — сделайте расклад.</p>";
        return;
      }
      r.items.forEach((it) => {
        const d = document.createElement("div");
        d.className = "history-item";
        const cards = (it.cards || []).map((c) => c.emoji || c.name).join(" ");
        d.innerHTML = `<strong>${it.title}</strong><div class="muted">${it.day_key || ""} · ${cards}</div>
          <p class="hist-preview">${(it.ai_text || "").slice(0, 160)}</p>`;
        box.appendChild(d);
      });
      show("history");
    } catch (e) {
      alert(e.message);
    }
  }

  async function loadTransits() {
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
    } catch (e) {
      alert(e.message);
    }
  }

  async function loadJournal() {
    try {
      const r = await api("/api/journal");
      const box = $("#journal-list");
      box.innerHTML = "";
      if (!r.items.length) {
        box.innerHTML = "<p class='muted'>Отметьте оценку на экране результата расклада.</p>";
      } else {
        r.items.forEach((j) => {
          const el = document.createElement("div");
          el.className = "history-item";
          el.innerHTML = `<strong>${j.title || "Расклад"}</strong> · ${"⭐".repeat(Math.min(5, j.rating || 0))}
            <div class="muted">${j.note || ""}</div>`;
          box.appendChild(el);
        });
      }
      show("journal");
    } catch (e) {
      if (e.payload && e.payload.premium_required) openPremium(e.message);
      else alert(e.message);
    }
  }

  async function loadPlans() {
    const r = await api("/api/plans");
    const box = $("#plans-list");
    box.innerHTML = "";
    (r.plans || []).forEach((p) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "plan-card";
      el.innerHTML = `<div class="title">${p.title}</div>
        <div class="meta">${p.description}</div>
        <div class="price">⭐ ${p.stars} Stars</div>`;
      el.addEventListener("click", () => {
        // open bot for payment
        if (tg && tg.openTelegramLink) {
          tg.openTelegramLink("https://t.me/AstoManiabot?start=premium");
        } else {
          window.open("https://t.me/AstoManiabot?start=premium", "_blank");
        }
      });
      box.appendChild(el);
    });
  }

  async function loadProfiles() {
    try {
      const r = await api("/api/profiles");
      profiles = r.items || [];
      const box = $("#profiles-list");
      box.innerHTML = "";
      profiles.forEach((p) => {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "history-item";
        el.style.width = "100%";
        el.style.textAlign = "left";
        el.innerHTML = `<strong>${p.label || "Профиль"} ${p.is_default ? "· основной" : ""}</strong>
          <div class="muted">${p.emoji || ""} ${p.sign || "—"} · ${p.place || ""}</div>`;
        el.addEventListener("click", async () => {
          await api("/api/profile/default", {
            method: "POST",
            body: JSON.stringify({ initData: initData(), profile_id: p.id }),
          });
          await refreshMe();
          alert("Основной профиль: " + (p.label || p.sign));
        });
        box.appendChild(el);
      });
      show("profiles");
    } catch (e) {
      alert(e.message);
    }
  }

  async function openCompat() {
    try {
      const r = await api("/api/profiles");
      profiles = r.items || [];
      const a = $("#compat-a");
      const b = $("#compat-b");
      a.innerHTML = b.innerHTML = "";
      if (!profiles.length) {
        openPremium("Сначала создайте профили (ASC). Совместимость — Premium.");
        show("profile");
        return;
      }
      profiles.forEach((p) => {
        const o1 = new Option(`${p.label} · ${p.sign || "?"}`, p.id);
        const o2 = new Option(`${p.label} · ${p.sign || "?"}`, p.id);
        a.add(o1);
        b.add(o2.cloneNode(true));
      });
      show("compat");
    } catch (e) {
      alert(e.message);
    }
  }

  $("#btn-compat-go").addEventListener("click", async () => {
    $("#global-question").value = $("#compat-q").value.trim();
    // use server spread compat
    pendingSpread = (data.spreads || []).find((s) => s.id === "compat") || {
      id: "compat",
      title: "Совместимость",
      emoji: "💞",
      blurb: "мы",
    };
    lastSpreadId = "compat";
    show("draw");
    await runDraw();
  });

  // Share card
  function shareCard() {
    const r = lastResultPayload;
    if (!r) return;
    const canvas = $("#share-canvas");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const g = ctx.createLinearGradient(0, 0, w, h);
    g.addColorStop(0, "#fff8f2");
    g.addColorStop(0.5, "#fde8ef");
    g.addColorStop(1, "#efe3ff");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#3a2f36";
    ctx.font = "600 48px Georgia, serif";
    ctx.fillText("Светлый Ленорман", 80, 120);
    ctx.font = "28px sans-serif";
    ctx.fillStyle = "#9a8790";
    ctx.fillText(r.title || "Расклад", 80, 180);
    const cards = r.cards || [];
    cards.slice(0, 5).forEach((c, i) => {
      const x = 80 + (i % 3) * 300;
      const y = 280 + Math.floor(i / 3) * 360;
      ctx.fillStyle = "#fff";
      roundRect(ctx, x, y, 260, 320, 28);
      ctx.fill();
      ctx.font = "72px serif";
      ctx.fillStyle = "#3a2f36";
      ctx.fillText(c.emoji || "✦", x + 90, y + 140);
      ctx.font = "28px sans-serif";
      ctx.fillText(c.name || "", x + 40, y + 220);
    });
    ctx.fillStyle = "#d4a574";
    ctx.font = "24px sans-serif";
    ctx.fillText("t.me/AstoManiabot", 80, h - 80);

    canvas.toBlob(async (blob) => {
      if (!blob) return;
      const file = new File([blob], "lenormand.png", { type: "image/png" });
      if (tg && tg.shareToStory) {
        // not always available
      }
      if (navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file], title: "Светлый Ленорман" });
          return;
        } catch (_) {}
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "lenormand-day.png";
      a.click();
      URL.revokeObjectURL(url);
    }, "image/png");
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function speak() {
    const text = $("#ai-text").textContent || "";
    if (!text || !window.speechSynthesis) {
      alert("Озвучка недоступна в этом клиенте");
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.slice(0, 1500));
    u.lang = "ru-RU";
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  }

  // library
  function renderLibrary() {
    const grid = $("#lib-grid");
    grid.innerHTML = "";
    (data.deck || []).forEach((c) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "lib-item";
      b.innerHTML = `<span class="em">${c.emoji}</span><span class="n">${c.number}</span><span class="nm">${c.name}</span>`;
      b.addEventListener("click", () => {
        $("#card-detail").innerHTML = `
          <div class="detail-visual"><span class="em">${c.emoji}</span><span class="num">${c.number}. ${c.name}</span></div>
          <div class="detail-block"><h4>Общее</h4><p>${c.general}</p></div>
          <div class="detail-block"><h4>Любовь</h4><p>${c.love}</p></div>
          <div class="detail-block"><h4>Дело</h4><p>${c.work}</p></div>
          <div class="detail-block"><h4>Совет</h4><p>${c.advice}</p></div>`;
        show("card");
      });
      grid.appendChild(b);
    });
  }

  // events
  $("#btn-day").addEventListener("click", () => openDay("day"));
  $("#btn-asc-day").addEventListener("click", () => {
    if (me && me.profile && me.profile.sign) openDay("asc_day");
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
  $("#btn-journal").addEventListener("click", loadJournal);
  $("#btn-premium").addEventListener("click", () => {
    loadPlans();
    show("premium");
  });
  $("#btn-profiles").addEventListener("click", loadProfiles);
  $("#btn-new-profile").addEventListener("click", () => show("profile"));
  $("#btn-library").addEventListener("click", () => {
    renderLibrary();
    show("library");
  });
  $("#btn-about").addEventListener("click", () => show("about"));

  $$("#journal-rate [data-rate]").forEach((b) => {
    b.addEventListener("click", async () => {
      if (!lastReadingId) return;
      try {
        await api("/api/journal", {
          method: "POST",
          body: JSON.stringify({
            initData: initData(),
            reading_id: lastReadingId,
            rating: Number(b.getAttribute("data-rate")),
            note: "",
          }),
        });
        alert("Сохранено в журнале 🤍");
      } catch (e) {
        if (e.payload && e.payload.premium_required) openPremium(e.message);
        else alert(e.message);
      }
    });
  });

  $$("[data-go]").forEach((el) => {
    el.addEventListener("click", () => {
      const go = el.getAttribute("data-go");
      if (go === "library") {
        renderLibrary();
        show("library");
      } else show(go);
    });
  });

  // boot
  renderSpreads();
  refreshMe();
})();
