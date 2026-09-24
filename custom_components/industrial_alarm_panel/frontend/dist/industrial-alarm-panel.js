/*
 * Industrial Alarm Panel — crew-alerting display for Home Assistant.
 * Vanilla custom element, no build step. Priority is coded by shape + number + colour;
 * alarm state is a mark on the glyph (filled active, hollow cleared, struck shelved, dashed disabled).
 */
const DOMAIN = "industrial_alarm_panel";
const ALARMS_UPDATED_EVENT = "industrial_alarm_panel_alarms_updated";
const ASSET_BASE = `/${DOMAIN}/frontend/dist/`;

const PRIORITIES = {
  critical: { n: 1, label: "CRIT", name: "Critical", color: "var(--iap-crit)" },
  high: { n: 2, label: "HIGH", name: "High", color: "var(--iap-high)" },
  medium: { n: 3, label: "MED", name: "Medium", color: "var(--iap-med)" },
  low: { n: 4, label: "LOW", name: "Low", color: "var(--iap-low)" },
  info: { n: 5, label: "INFO", name: "Info", color: "var(--iap-info)" },
  status: { n: 6, label: "STAT", name: "Status", color: "var(--iap-info)" },
};
const PRIORITY_KEYS = Object.keys(PRIORITIES);
const ACTIVE_STATES = ["ACTIVE_UNACK", "ACTIVE_ACK"];
const UNACK_STATES = ["ACTIVE_UNACK", "CLEARED_UNACK"];
const SHELVE_PRESETS = [
  [60, "1h", "1 hour"],
  [240, "4h", "4 hours"],
  [480, "8h", "8 hours"],
  [1440, "1d", "1 day"],
  [4320, "3d", "3 days"],
  [10080, "7d", "7 days"],
];
const CONDITIONS = [
  ["above", "Above"],
  ["below", "Below"],
  ["equal", "Equal to"],
  ["not_equal", "Not equal to"],
  ["contains", "Contains"],
  ["is_on", "Is on"],
  ["is_off", "Is off"],
  ["state_changed", "State changed"],
  ["unavailable", "Unavailable"],
  ["unavailable_for", "Unavailable for (s)"],
  ["unknown_for", "Unknown for (s)"],
  ["manual", "Manual"],
];
const THRESHOLD_CONDITIONS = new Set(["above", "below", "equal", "not_equal", "contains", "unavailable_for", "unknown_for"]);
const PAGES = [
  ["alerts", "ALERTS"],
  ["unack", "UNACK"],
  ["history", "HISTORY"],
  ["shelved", "SHELVED"],
  ["disabled", "DISABLED"],
  ["rules", "RULES"],
  ["sys", "SYS"],
];
const LEGACY_TAB_NAMES = { active: "alerts", unacknowledged: "unack", settings: "sys" };
const EMPTY_RULE = {
  id: "",
  entity_id: "",
  name: "",
  tag: "",
  area: "",
  system: "",
  condition: "above",
  threshold: "",
  deadband: "",
  priority: "medium",
  delay_on_seconds: "",
  delay_off_seconds: "",
  min_active_duration_seconds: "",
  instructions: "",
  enabled: true,
  audible: true,
  requires_ack: true,
  shelving_allowed: true,
};
const NUMERIC_RULE_FIELDS = new Set(["deadband", "delay_on_seconds", "delay_off_seconds", "min_active_duration_seconds"]);
const BOOLEAN_RULE_FIELDS = new Set(["enabled", "audible", "requires_ack", "shelving_allowed"]);

function ensureFonts() {
  if (document.getElementById("iap-fonts")) return;
  const style = document.createElement("style");
  style.id = "iap-fonts";
  style.textContent = `
    @font-face { font-family: "B612"; font-weight: 400; font-display: swap; src: url("${ASSET_BASE}fonts/B612-Regular.woff2") format("woff2"); }
    @font-face { font-family: "B612"; font-weight: 700; font-display: swap; src: url("${ASSET_BASE}fonts/B612-Bold.woff2") format("woff2"); }
    @font-face { font-family: "B612 Mono"; font-weight: 400; font-display: swap; src: url("${ASSET_BASE}fonts/B612Mono-Regular.woff2") format("woff2"); }
  `;
  document.head.appendChild(style);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

function priorityOf(key) {
  return PRIORITIES[key] || PRIORITIES.info;
}

/** Priority glyph: shape + number + colour. mode: filled | hollow | struck | dashed | normal | pending */
function glyph(priority, mode = "filled", size = 22) {
  const p = priorityOf(priority);
  const key = PRIORITIES[priority] ? priority : "info";
  const shapes = {
    critical: '<path d="M11 1.5 20.5 11 11 20.5 1.5 11Z"/>',
    high: '<path d="M11 2 20.5 19.5H1.5Z"/>',
    medium: '<rect x="2.5" y="2.5" width="17" height="17"/>',
    low: '<circle cx="11" cy="11" r="8.8"/>',
    info: '<circle cx="11" cy="11" r="8.8"/>',
    status: '<path d="M6 2.5h10l4.5 8.5L16 19.5H6L1.5 11Z"/>',
  };
  const muted = mode === "normal" || mode === "pending";
  const color = muted ? "var(--iap-faint)" : p.color;
  const solid = mode === "filled" && key !== "info" && key !== "status";
  const fill = solid ? color : "none";
  const text = solid ? "#050505" : color;
  const dash = mode === "dashed" ? ' stroke-dasharray="2.5 2.5"' : "";
  const textY = key === "high" ? 16 : 14.6;
  const strike = mode === "struck" ? `<line x1="1.5" y1="20.5" x2="20.5" y2="1.5" stroke="${color}" stroke-width="1.6"/>` : "";
  return `<svg class="g m-${mode}" style="--gc:${color}" width="${size}" height="${size}" viewBox="0 0 22 22" aria-hidden="true" focusable="false"><g class="shape" fill="${fill}" stroke="${color}" stroke-width="1.6"${dash}>${shapes[key]}</g><text class="num" x="11" y="${textY}" text-anchor="middle" fill="${text}">${p.n}</text>${strike}</svg>`;
}

function glyphMode(alarm) {
  switch (alarm.lifecycle_state) {
    case "SHELVED":
      return "struck";
    case "DISABLED":
      return "dashed";
    case "CLEARED_UNACK":
      return "hollow";
    case "ACTIVE_UNACK":
    case "ACTIVE_ACK":
      return "filled";
    default:
      return "normal";
  }
}

function parseTime(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatClock(value) {
  const date = parseTime(value);
  if (!date) return "";
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  if (sameDay) return time;
  return `${date.toLocaleDateString([], { day: "2-digit", month: "short" })} ${time.slice(0, 5)}`;
}

function formatShort(value) {
  const date = parseTime(value);
  if (!date) return "";
  const today = new Date();
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  if (date.toDateString() === today.toDateString()) return time;
  return `${date.toLocaleDateString([], { day: "2-digit", month: "short" })} ${time}`;
}

function formatAge(value) {
  const date = parseTime(value);
  if (!date) return "";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ${minutes % 60} min ago`;
  return `${Math.floor(hours / 24)} days ago`;
}

function storageGet(key, fallback) {
  try {
    const value = window.localStorage.getItem(`${DOMAIN}.${key}`);
    return value === null ? fallback : JSON.parse(value);
  } catch (_err) {
    return fallback;
  }
}

function storageSet(key, value) {
  try {
    window.localStorage.setItem(`${DOMAIN}.${key}`, JSON.stringify(value));
  } catch (_err) {
    /* storage unavailable: the preference lasts for this session only */
  }
}

class IndustrialAlarmPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._alarms = [];
    this._rules = [];
    this._history = [];
    this._sound = {};
    this._display = {};
    this._page = "alerts";
    this._pageFromOptions = false;
    this._selectedId = null;
    this._statusOpen = false;
    this._filters = { q: "", priority: "all", area: "all" };
    this._historyFilters = { q: "", priority: "all", eventType: "all", range: "24h" };
    this._density = storageGet("density", null);
    this._flashPref = storageGet("flash", true);
    this._rulesMode = "board";
    this._editor = null;
    this._selectedRuleIds = new Set();
    this._suggestionDraft = {
      power_threshold_w: 2000,
      low_voltage_v: 207,
      high_voltage_v: 253,
      high_solar_water_temp_c: 75,
    };
    this._suggestedRules = [];
    this._selectedSuggestedRuleIds = new Set();
    this._suggestOpen = false;
    this._loading = false;
    this._loadPending = false;
    this._loadTimer = undefined;
    this._pollTimer = undefined;
    this._hornTimer = undefined;
    this._visualTimer = undefined;
    this._unsubscribe = undefined;
    this._subscribed = false;
    this._audioEnabled = false;
    this._audioContext = undefined;
    this._alarmVisualDelayMs = 2000;
    this._browserHornIntervalMs = 2000;
    this._lastBrowserHornAt = 0;
    this._trendCache = new Map();
    this._lastLiveState = undefined;
    this._columnWidths = {};
    this._built = false;
    this._onKeyDown = (event) => this._handleKey(event);
    this._onResize = () => {
      window.clearTimeout(this._resizeTimer);
      this._resizeTimer = window.setTimeout(() => this._renderAll(), 150);
    };
  }

  /* ---------- Home Assistant wiring ---------- */

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._subscribeUpdates();
      this._load();
    }
    this._updateLiveValue();
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    this._narrow = Boolean(value);
    if (!this._built) return;
    this.shadowRoot.querySelector(".panel").classList.toggle("narrow", this._narrow);
    this._renderAll();
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    ensureFonts();
    if (!this._built) this._build();
    if (this._hass) {
      this._subscribeUpdates();
      this._load();
    }
    if (!this._pollTimer) this._pollTimer = window.setInterval(() => this._load(), 30000);
    this.shadowRoot.addEventListener("keydown", this._onKeyDown);
    window.addEventListener("resize", this._onResize);
    this._syncHorn();
  }

  disconnectedCallback() {
    window.clearInterval(this._pollTimer);
    this._pollTimer = undefined;
    window.clearTimeout(this._loadTimer);
    window.clearTimeout(this._visualTimer);
    this._visualTimer = undefined;
    this._stopHornLoop();
    this.shadowRoot.removeEventListener("keydown", this._onKeyDown);
    window.removeEventListener("resize", this._onResize);
    window.clearTimeout(this._resizeTimer);
    if (this._unsubscribe) {
      Promise.resolve(this._unsubscribe)
        .then((unsubscribe) => {
          if (typeof unsubscribe === "function") unsubscribe();
        })
        .catch(() => undefined);
    }
    this._unsubscribe = undefined;
    this._subscribed = false;
  }

  _subscribeUpdates() {
    const connection = this._hass?.connection;
    if (this._subscribed || !connection?.subscribeEvents) return;
    this._subscribed = true;
    try {
      this._unsubscribe = connection.subscribeEvents((event) => this._handleAlarmUpdateEvent(event), ALARMS_UPDATED_EVENT);
    } catch (_err) {
      this._subscribed = false;
      this._unsubscribe = undefined;
    }
  }

  _handleAlarmUpdateEvent(event) {
    const entryId = this._panel?.config?.entry_id;
    if (entryId && event?.data?.entry_id && event.data.entry_id !== entryId) return;
    this._scheduleLoad();
  }

  _scheduleLoad(delay = 150) {
    window.clearTimeout(this._loadTimer);
    this._loadTimer = window.setTimeout(() => this._load(), delay);
  }

  async _callWS(payload) {
    if (!this._hass) return null;
    return this._hass.callWS(payload);
  }

  async _load() {
    if (!this._hass) return;
    if (this._loading) {
      this._loadPending = true;
      return;
    }
    this._loading = true;
    try {
      const wantHistory = this._page === "history";
      const [alarms, rules, history] = await Promise.all([
        this._callWS({ type: `${DOMAIN}/list_alarms` }),
        this._callWS({ type: `${DOMAIN}/list_rules` }),
        wantHistory ? this._callWS(this._historyQuery()) : Promise.resolve(null),
      ]);
      this._alarms = alarms?.alarms || [];
      this._sound = alarms?.sound || {};
      this._display = alarms?.display || {};
      this._rules = rules?.rules || [];
      if (history) this._history = history.events || [];
      this._applyDisplayDefaults();
      const ruleIds = new Set(this._rules.map((rule) => rule.id));
      this._selectedRuleIds = new Set([...this._selectedRuleIds].filter((id) => ruleIds.has(id)));
      this._suggestedRules = this._suggestedRules.filter((rule) => !ruleIds.has(rule.id));
      this._error = "";
      this._renderAll();
      this._syncHorn();
    } catch (err) {
      this._error = err?.message || String(err);
      this._renderError();
    } finally {
      this._loading = false;
      if (this._loadPending) {
        this._loadPending = false;
        this._scheduleLoad(0);
      }
    }
  }

  _applyDisplayDefaults() {
    if (this._density === null) this._density = this._display?.enable_compact_mode ? "compact" : "comfortable";
    if (this._pageFromOptions) return;
    this._pageFromOptions = true;
    const configured = this._display?.default_tab;
    if (!configured) return;
    const page = LEGACY_TAB_NAMES[configured] || configured;
    if (PAGES.some(([id]) => id === page)) this._page = page;
  }

  /* ---------- Derived data ---------- */

  _unit(alarm) {
    return this._hass?.states?.[alarm.entity_id]?.attributes?.unit_of_measurement || "";
  }

  _displayValue(alarm) {
    const live = this._hass?.states?.[alarm.entity_id];
    const raw = live ? live.state : alarm.last_value ?? alarm.last_source_state;
    if (raw === undefined || raw === null || raw === "") return { value: "", unit: "" };
    const numeric = Number(raw);
    if (Number.isFinite(numeric) && String(raw).trim() !== "") {
      const decimals = Math.abs(numeric) >= 100 ? 1 : Math.abs(numeric) >= 10 ? 1 : 2;
      return { value: numeric.toFixed(decimals), unit: this._unit(alarm) };
    }
    return { value: String(raw), unit: "" };
  }

  _isActive(alarm) {
    return ACTIVE_STATES.includes(alarm.lifecycle_state);
  }

  _isUnack(alarm) {
    return UNACK_STATES.includes(alarm.lifecycle_state);
  }

  _isPendingColour(alarm) {
    if (!this._isUnack(alarm)) return false;
    const since = parseTime(alarm.active_since || alarm.cleared_at);
    if (!since) return false;
    const remaining = this._alarmVisualDelayMs - (Date.now() - since.getTime());
    if (remaining <= 0) return false;
    this._scheduleVisualRefresh(remaining + 50);
    return true;
  }

  _scheduleVisualRefresh(delay) {
    if (this._visualTimer) return;
    this._visualTimer = window.setTimeout(() => {
      this._visualTimer = undefined;
      this._renderAll();
    }, delay);
  }

  _pageAlarms(page = this._page) {
    const { q, priority, area } = this._filters;
    const query = q.trim().toLowerCase();
    return this._alarms
      .filter((alarm) => {
        const state = alarm.lifecycle_state;
        if (page === "alerts" && !(ACTIVE_STATES.includes(state) || state === "CLEARED_UNACK")) return false;
        if (page === "unack" && !UNACK_STATES.includes(state)) return false;
        if (page === "shelved" && state !== "SHELVED") return false;
        if (page === "disabled" && state !== "DISABLED") return false;
        if (priority !== "all" && alarm.priority !== priority) return false;
        if (area !== "all" && (alarm.area || "") !== area) return false;
        if (!query) return true;
        return [alarm.tag, alarm.name, alarm.entity_id, alarm.area, alarm.system]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(query);
      })
      .sort((a, b) => {
        const severity = (b.severity || 0) - (a.severity || 0);
        if (severity) return severity;
        const unack = Number(this._isUnack(b)) - Number(this._isUnack(a));
        if (unack) return unack;
        return String(b.active_since || b.cleared_at || "").localeCompare(String(a.active_since || a.cleared_at || ""));
      });
  }

  _count(predicate) {
    return this._alarms.filter(predicate).length;
  }

  _flashEnabled() {
    if (this._display?.enable_flashing === false) return false;
    return this._flashPref !== false;
  }

  /* ---------- Shell (built once) ---------- */

  _build() {
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <main class="panel ${this._narrow ? "narrow" : ""} density-${this._density}" part="panel">
        <div class="master" id="master">
          <button type="button" class="menu" data-action="toggle-menu" aria-label="Open Home Assistant sidebar">
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/></svg>
          </button>
          <button type="button" class="key key-warn" data-action="master-warn" id="key-warn">
            <span class="face">MASTER<br>WARN</span><span class="cap" id="key-warn-cap"></span>
          </button>
          <button type="button" class="key key-caut" data-action="master-caut" id="key-caut">
            <span class="face">MASTER<br>CAUT</span><span class="cap" id="key-caut-cap"></span>
          </button>
          <div class="legend" id="legend" role="group" aria-label="Active alarms by priority"></div>
          <div class="horn" id="horn">
            <div class="horn-state"><i></i><span id="horn-text"></span></div>
            <button type="button" id="horn-button" data-action="silence">SILENCE</button>
          </div>
          <button type="button" class="key key-ack" data-action="ack-all" id="key-ack">
            <span class="face">ACK<br>ALL</span><span class="cap" id="key-ack-cap"></span>
          </button>
        </div>
        <section class="next" id="next" aria-live="polite"></section>
        <nav class="pages" id="pages" role="tablist" aria-label="Alarm pages"></nav>
        <div class="error" id="error" role="alert" hidden></div>

        <section class="view" id="view-alarms">
          <div class="filters">
            <input class="field search" id="alarm-search" type="search" placeholder="Search tag, alarm, entity, area" aria-label="Search alarms" data-input="alarm-search">
            <select class="field" id="alarm-priority" aria-label="Priority" data-input="alarm-priority"></select>
            <select class="field" id="alarm-area" aria-label="Area" data-input="alarm-area"></select>
            <span class="spacer"></span>
            <button type="button" class="chip" data-action="toggle-density" id="density-chip" aria-pressed="false">COMPACT</button>
          </div>
          <div class="split">
            <div class="stack">
              <div class="stack-head" aria-hidden="true"><span></span><span>TIME</span><span class="c-tag">TAG</span><span>MESSAGE</span><span class="c-val">VALUE</span><span class="c-state">STATE</span></div>
              <div id="stack" role="listbox" aria-label="Alarms"></div>
            </div>
            <aside class="status" id="status" aria-label="Alarm status page"></aside>
          </div>
        </section>

        <section class="view" id="view-history" hidden>
          <div class="filters">
            <input class="field search" id="history-search" type="search" placeholder="Search events" aria-label="Search history" data-input="history-search">
            <select class="field" id="history-type" aria-label="Event type" data-input="history-type">
              <option value="all">All events</option><option value="activated">Activated</option><option value="acknowledged">Acknowledged</option>
              <option value="cleared">Cleared</option><option value="shelved">Shelved</option><option value="unshelved">Unshelved</option>
              <option value="disabled">Disabled</option><option value="enabled">Enabled</option><option value="silenced">Silenced</option>
            </select>
            <select class="field" id="history-priority" aria-label="Priority" data-input="history-priority"></select>
            <select class="field" id="history-range" aria-label="Time range" data-input="history-range">
              <option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="all">All</option>
            </select>
            <span class="spacer"></span>
            <button type="button" class="chip" data-action="export-csv">EXPORT CSV</button>
          </div>
          <div class="table-shell">
            <table data-table-id="history">
              <thead><tr><th>TIME</th><th>PRI</th><th>EVENT</th><th>TAG</th><th>MESSAGE</th><th>FROM → TO</th><th>VALUE</th><th>OPERATOR</th></tr></thead>
              <tbody id="history-body"></tbody>
            </table>
          </div>
        </section>

        <section class="view" id="view-rules" hidden>
          <div class="filters">
            <div class="seg" role="group" aria-label="Rules layout">
              <button type="button" data-action="rules-mode" data-mode="board" id="rules-mode-board">BOARD</button>
              <button type="button" data-action="rules-mode" data-mode="list" id="rules-mode-list">LIST</button>
            </div>
            <span class="muted" id="rules-summary"></span>
            <span class="spacer"></span>
            <button type="button" class="chip" data-action="toggle-suggest" id="suggest-chip" aria-expanded="false">SUGGEST RULES</button>
            <button type="button" class="chip" data-action="new-rule">+ NEW RULE</button>
          </div>
          <div class="suggest" id="suggest" hidden>
            <div class="suggest-form">
              <label>High power W<input class="field" type="number" min="1" step="50" data-suggest="power_threshold_w"></label>
              <label>Low voltage V<input class="field" type="number" min="1" step="1" data-suggest="low_voltage_v"></label>
              <label>High voltage V<input class="field" type="number" min="1" step="1" data-suggest="high_voltage_v"></label>
              <label>Solar water °C<input class="field" type="number" min="1" step="1" data-suggest="high_solar_water_temp_c"></label>
              <button type="button" class="btn" data-action="preview-suggested-rules">PREVIEW SUGGESTED RULES</button>
            </div>
            <div class="suggest-result" id="suggest-result"></div>
          </div>
          <div class="split rules-split">
            <div class="rules-main" id="rules-main"></div>
            <aside class="status editor" id="rule-editor" aria-label="Rule editor"></aside>
          </div>
        </section>

        <section class="view" id="view-sys" hidden></section>
        <div class="toast" id="toast" role="status" aria-live="polite" hidden></div>
        <dialog class="confirm" id="confirm">
          <form method="dialog">
            <p id="confirm-text"></p>
            <div class="confirm-actions">
              <button type="submit" class="btn" value="cancel">CANCEL</button>
              <button type="submit" class="btn danger" value="ok" id="confirm-ok">CONFIRM</button>
            </div>
          </form>
        </dialog>
      </main>
    `;
    const root = this.shadowRoot;
    root.addEventListener("click", (event) => this._handleClick(event));
    root.addEventListener("input", (event) => this._handleInput(event));
    root.addEventListener("change", (event) => this._handleChange(event));
    const priorityOptions = `<option value="all">All priorities</option>${PRIORITY_KEYS.map((key) => `<option value="${key}">${PRIORITIES[key].name}</option>`).join("")}`;
    root.getElementById("alarm-priority").innerHTML = priorityOptions;
    root.getElementById("history-priority").innerHTML = priorityOptions;
    root.querySelectorAll("[data-suggest]").forEach((input) => {
      input.value = this._suggestionDraft[input.dataset.suggest];
    });
    this._wireColumnResizers();
    this._built = true;
    this._renderAll();
  }

  /* ---------- Rendering ---------- */

  _renderAll() {
    if (!this._built) return;
    const panel = this.shadowRoot.querySelector(".panel");
    panel.classList.toggle("narrow", Boolean(this._narrow));
    panel.classList.toggle("no-flash", !this._flashEnabled());
    panel.classList.toggle("density-compact", this._density === "compact");
    const alarmPage = ["alerts", "unack", "shelved", "disabled"].includes(this._page);
    panel.classList.toggle("shell", alarmPage && !this._narrow && window.innerWidth > 860);
    this._renderMaster();
    this._renderNext();
    this._renderPages();
    this._renderError();
    const root = this.shadowRoot;
    root.getElementById("view-alarms").hidden = !alarmPage;
    root.getElementById("view-history").hidden = this._page !== "history";
    root.getElementById("view-rules").hidden = this._page !== "rules";
    root.getElementById("view-sys").hidden = this._page !== "sys";
    if (alarmPage) {
      this._renderAreaOptions();
      this._renderStack();
      this._renderStatus();
    } else if (this._page === "history") {
      this._renderHistory();
    } else if (this._page === "rules") {
      this._renderRules();
    } else if (this._page === "sys") {
      this._renderSys();
    }
  }

  _renderError() {
    const el = this.shadowRoot.getElementById("error");
    if (!el) return;
    el.hidden = !this._error;
    el.textContent = this._error ? `Could not reach the alarm engine: ${this._error}` : "";
  }

  _renderMaster() {
    const root = this.shadowRoot;
    const crit = this._alarms.filter((a) => a.priority === "critical");
    const caut = this._alarms.filter((a) => a.priority === "high" || a.priority === "medium");
    const critActive = crit.filter((a) => this._isActive(a)).length;
    const cautActive = caut.filter((a) => this._isActive(a)).length;
    const critUnack = crit.some((a) => a.lifecycle_state === "ACTIVE_UNACK");
    const cautUnack = caut.some((a) => a.lifecycle_state === "ACTIVE_UNACK");
    const warn = root.getElementById("key-warn");
    warn.className = `key key-warn${critActive ? " lit" : ""}${critUnack ? " flash" : ""}`;
    warn.setAttribute("aria-label", `Master warning, ${critActive} critical active. Press to acknowledge critical alarms and silence the horn.`);
    root.getElementById("key-warn-cap").textContent = `CRITICAL ${critActive}`;
    const cautKey = root.getElementById("key-caut");
    cautKey.className = `key key-caut${cautActive ? " lit" : ""}${cautUnack ? " flash" : ""}`;
    cautKey.setAttribute("aria-label", `Master caution, ${cautActive} high or medium active. Press to acknowledge them.`);
    root.getElementById("key-caut-cap").textContent = `HIGH/MED ${cautActive}`;
    const unack = this._count((a) => this._isUnack(a));
    root.getElementById("key-ack-cap").textContent = `${unack} UNACK`;
    root.getElementById("key-ack").disabled = unack === 0;
    root.getElementById("legend").innerHTML = PRIORITY_KEYS.map((key) => {
      const count = this._count((a) => a.priority === key && this._isActive(a));
      return `<span class="lg ${count ? "" : "zero"}" title="${PRIORITIES[key].name}: ${count} active">${glyph(key, count ? "filled" : "normal", 20)}<span>${PRIORITIES[key].label}</span><b>${count}</b></span>`;
    }).join("");
    const horn = root.getElementById("horn");
    const hornOn = Boolean(this._sound?.horn_active);
    horn.classList.toggle("on", hornOn);
    const hornButton = root.getElementById("horn-button");
    if (!this._audioEnabled && this._sound?.browser_enabled !== false) {
      root.getElementById("horn-text").textContent = hornOn ? "HORN · BROWSER MUTED" : "BROWSER SOUND OFF";
      hornButton.textContent = hornOn ? "SILENCE" : "ENABLE SOUND";
      hornButton.dataset.action = hornOn ? "silence" : "enable-audio";
    } else {
      root.getElementById("horn-text").textContent = hornOn ? "HORN SOUNDING" : "HORN QUIET";
      hornButton.textContent = "SILENCE";
      hornButton.dataset.action = "silence";
    }
  }

  _renderNext() {
    const el = this.shadowRoot.getElementById("next");
    if (!this._narrow) {
      el.innerHTML = "";
      return;
    }
    const pending = this._pageAlarms("unack");
    const top = pending[0];
    if (!top) {
      const active = this._count((a) => this._isActive(a));
      el.innerHTML = `<h2 class="calm">${active ? `${active} alarm${active === 1 ? "" : "s"} active, all acknowledged` : "Nothing is in alarm"}</h2>`;
      return;
    }
    const { value, unit } = this._displayValue(top);
    const p = priorityOf(top.priority);
    el.innerHTML = `
      <div class="next-id">${glyph(top.priority, glyphMode(top), 30)}<span class="mono">${escapeHtml(top.tag || top.id)}</span><span>${formatClock(top.active_since || top.cleared_at)}</span></div>
      <h2 style="color:${p.color}">${escapeHtml(top.name)}</h2>
      ${value ? `<div class="next-value">${escapeHtml(value)}<small>${escapeHtml(unit)}</small></div>` : ""}
      <div class="next-meta">${escapeHtml([top.area, top.system].filter(Boolean).join(" · "))}${top.lifecycle_state === "CLEARED_UNACK" ? " · returned to normal" : ""}</div>
      <div class="next-actions">
        <button type="button" class="btn big ack" data-action="ack" data-id="${escapeHtml(top.id)}">ACK</button>
        <button type="button" class="btn big" data-action="ack-all">ACK ALL · ${pending.length}</button>
      </div>`;
  }

  _renderPages() {
    const counts = {
      alerts: this._count((a) => this._isActive(a) || a.lifecycle_state === "CLEARED_UNACK"),
      unack: this._count((a) => this._isUnack(a)),
      shelved: this._count((a) => a.lifecycle_state === "SHELVED"),
      disabled: this._count((a) => a.lifecycle_state === "DISABLED"),
      rules: this._rules.length,
    };
    this.shadowRoot.getElementById("pages").innerHTML = PAGES.map(([id, label]) => {
      const count = counts[id];
      const attention = id === "unack" && count > 0;
      return `<button type="button" role="tab" data-action="page" data-page="${id}" aria-selected="${this._page === id}" class="${attention ? "attention" : ""}">${label}${count !== undefined ? `<span>${count}</span>` : ""}</button>`;
    }).join("");
  }

  _renderAreaOptions() {
    const select = this.shadowRoot.getElementById("alarm-area");
    const areas = [...new Set(this._alarms.map((a) => a.area).filter(Boolean))].sort();
    const signature = areas.join("|");
    if (select.dataset.signature === signature) return;
    select.dataset.signature = signature;
    select.innerHTML = `<option value="all">All areas</option>${areas.map((area) => `<option value="${escapeHtml(area)}">${escapeHtml(area)}</option>`).join("")}`;
    select.value = areas.includes(this._filters.area) ? this._filters.area : "all";
    this._filters.area = select.value;
  }

  _renderStack() {
    const list = this._pageAlarms();
    if (list.length && !list.some((a) => a.id === this._selectedId)) {
      this._selectedId = list[0].id;
    }
    if (!list.length) {
      this._selectedId = null;
      this._statusOpen = false;
    }
    const stack = this.shadowRoot.getElementById("stack");
    const densityChip = this.shadowRoot.getElementById("density-chip");
    densityChip.setAttribute("aria-pressed", String(this._density === "compact"));
    if (!list.length) {
      const empty = {
        alerts: "Nothing is in alarm",
        unack: "Every alarm is acknowledged",
        shelved: "No shelved alarms",
        disabled: "No disabled alarms",
      }[this._page];
      const filtered = this._filters.q || this._filters.priority !== "all" || this._filters.area !== "all";
      stack.innerHTML = `<div class="empty">${filtered ? "No alarms match these filters" : empty}</div>`;
      this._placeStatus();
      return;
    }
    stack.innerHTML = list.map((alarm) => this._alarmRow(alarm)).join("");
    this._placeStatus();
  }

  /** On narrow screens the status page unfolds directly under the tapped row. */
  _placeStatus() {
    const status = this.shadowRoot.getElementById("status");
    const split = this.shadowRoot.querySelector("#view-alarms .split");
    const row = this._selectedId ? this.shadowRoot.querySelector(`#stack .row[data-id="${CSS.escape(this._selectedId)}"]`) : null;
    if (this._narrow && this._statusOpen && row) {
      if (status.previousElementSibling !== row) row.after(status);
      status.classList.add("inline");
    } else {
      if (status.parentElement !== split) split.appendChild(status);
      status.classList.remove("inline", "unfolding");
    }
  }

  _alarmRow(alarm) {
    const pending = this._isPendingColour(alarm);
    const mode = pending ? "pending" : glyphMode(alarm);
    const { value, unit } = this._displayValue(alarm);
    const classes = [
      "row",
      `p-${PRIORITIES[alarm.priority] ? alarm.priority : "info"}`,
      this._isActive(alarm) && !pending ? "active" : "",
      !this._isActive(alarm) && alarm.lifecycle_state !== "CLEARED_UNACK" ? "dim" : "",
      this._isUnack(alarm) && !pending ? "unack" : "",
      pending ? "pending" : "",
      alarm.lifecycle_state === "SHELVED" ? "shelved" : "",
    ].filter(Boolean).join(" ");
    const selected = alarm.id === this._selectedId;
    return `<button type="button" class="${classes}" role="option" aria-selected="${selected}" data-action="select-alarm" data-id="${escapeHtml(alarm.id)}">
      ${glyph(alarm.priority, mode)}
      <span class="time">${formatClock(alarm.active_since || alarm.cleared_at)}</span>
      <span class="tag mono c-tag">${escapeHtml(alarm.tag || alarm.id)}</span>
      <span class="msg"><b>${escapeHtml(alarm.name)}</b><span>${escapeHtml([alarm.area, alarm.system].filter(Boolean).join(" · ") || alarm.entity_id)}</span></span>
      <span class="val c-val">${escapeHtml(value)}${unit ? `<small> ${escapeHtml(unit)}</small>` : ""}</span>
      <span class="state c-state">${this._stateLabel(alarm)}</span>
    </button>`;
  }

  _stateLabel(alarm) {
    switch (alarm.lifecycle_state) {
      case "ACTIVE_UNACK":
        return "UNACK";
      case "ACTIVE_ACK":
        return "ACK";
      case "CLEARED_UNACK":
        return "CLR · UNACK";
      case "SHELVED":
        return alarm.shelve_expiry ? `SHELVED ${formatShort(alarm.shelve_expiry)}` : "SHELVED";
      case "DISABLED":
        return "DISABLED";
      default:
        return "NORMAL";
    }
  }

  _renderStatus() {
    const el = this.shadowRoot.getElementById("status");
    const alarm = this._alarms.find((a) => a.id === this._selectedId);
    if (!alarm) {
      el.innerHTML = `<div class="empty">Select an alarm to see its status page</div>`;
      return;
    }
    const rule = this._rules.find((r) => r.id === alarm.id) || {};
    const p = priorityOf(alarm.priority);
    const { value, unit } = this._displayValue(alarm);
    const unackable = this._isUnack(alarm);
    const shelved = alarm.lifecycle_state === "SHELVED";
    const disabled = alarm.lifecycle_state === "DISABLED";
    const canShelve = !shelved && !disabled && rule.shelving_allowed !== false;
    const timeline = [
      [alarm.active_since, "Activated"],
      [alarm.acknowledged_at, `Acknowledged${alarm.ack_user ? ` by ${alarm.ack_user}` : ""}`],
      [alarm.cleared_at, "Returned to normal"],
      [shelved ? alarm.shelve_expiry : null, "Shelve ends"],
    ]
      .filter(([time]) => parseTime(time))
      .sort((a, b) => parseTime(b[0]) - parseTime(a[0]));
    el.innerHTML = `
      <header class="status-head">${glyph(alarm.priority, glyphMode(alarm), 34)}
        <div><h2>${escapeHtml(alarm.name)}</h2><p><span class="mono">${escapeHtml(alarm.tag || alarm.id)}</span> · ${p.label} · ${this._stateLabel(alarm)}</p></div>
      </header>
      <div class="readout">
        <div class="big" id="live-value">${escapeHtml(value || "—")}<small>${escapeHtml(unit)}</small></div>
        <div class="limit">LIMIT<b>${escapeHtml(this._conditionText(alarm, unit))}</b></div>
      </div>
      <div class="trend" id="trend"></div>
      <dl class="facts">
        <dt>AREA</dt><dd>${escapeHtml([alarm.area, alarm.system].filter(Boolean).join(" · ") || "—")}</dd>
        <dt>SINCE</dt><dd>${alarm.active_since ? `${formatClock(alarm.active_since)} · ${formatAge(alarm.active_since)}` : "—"}</dd>
        <dt>ENTITY</dt><dd class="mono">${escapeHtml(alarm.entity_id || "—")}</dd>
        <dt>RULE</dt><dd>${escapeHtml(this._ruleSummary(rule))} <button type="button" class="link" data-action="edit-rule" data-id="${escapeHtml(alarm.id)}">Edit rule</button></dd>
      </dl>
      ${alarm.instructions ? `<div class="instructions"><b>INSTRUCTIONS</b>${escapeHtml(alarm.instructions)}</div>` : ""}
      ${timeline.length ? `<ul class="timeline">${timeline.map(([time, text]) => `<li><span>${formatShort(time)}</span><span>${escapeHtml(text)}</span></li>`).join("")}</ul>` : ""}
      <div class="actions">
        <div class="pair">
          <button type="button" class="btn ack" data-action="ack" data-id="${escapeHtml(alarm.id)}" ${unackable ? "" : "disabled"}>${unackable ? "ACK" : "ACKNOWLEDGED"}</button>
          <button type="button" class="btn" data-action="${disabled ? "enable-alarm" : "disable-alarm"}" data-id="${escapeHtml(alarm.id)}">${disabled ? "ENABLE" : "DISABLE"}</button>
        </div>
        ${shelved
          ? `<button type="button" class="btn" data-action="unshelve" data-id="${escapeHtml(alarm.id)}">UNSHELVE NOW</button>`
          : `<div class="shelve" role="group" aria-label="Shelve for"><span>SHELVE</span>${SHELVE_PRESETS.map(([minutes, short, long]) => `<button type="button" data-action="shelve" data-id="${escapeHtml(alarm.id)}" data-minutes="${minutes}" aria-label="Shelve for ${long}" ${canShelve ? "" : "disabled"}>${short}</button>`).join("")}</div>`}
      </div>`;
    this._lastLiveState = this._hass?.states?.[alarm.entity_id];
    this._renderTrend(alarm, rule);
  }

  _conditionText(alarm, unit = "") {
    const threshold = alarm.threshold;
    const suffix = unit ? ` ${unit}` : "";
    switch (alarm.condition) {
      case "above":
        return `> ${threshold}${suffix}`;
      case "below":
        return `< ${threshold}${suffix}`;
      case "equal":
        return `= ${threshold}`;
      case "not_equal":
        return `≠ ${threshold}`;
      case "contains":
        return `contains ${threshold}`;
      case "is_on":
        return "is on";
      case "is_off":
        return "is off";
      case "state_changed":
        return "any change";
      case "unavailable":
        return "unavailable";
      case "unavailable_for":
        return `unavailable ${threshold}s`;
      case "unknown_for":
        return `unknown ${threshold}s`;
      default:
        return alarm.condition || "manual";
    }
  }

  _ruleSummary(rule) {
    if (!rule?.id) return "—";
    const parts = [CONDITIONS.find(([key]) => key === rule.condition)?.[1] || rule.condition];
    if (THRESHOLD_CONDITIONS.has(rule.condition) && rule.threshold !== null && rule.threshold !== undefined) parts[0] += ` ${rule.threshold}`;
    if (rule.delay_on_seconds) parts.push(`on-delay ${rule.delay_on_seconds}s`);
    if (rule.delay_off_seconds) parts.push(`off-delay ${rule.delay_off_seconds}s`);
    if (rule.deadband) parts.push(`deadband ${rule.deadband}`);
    return parts.join(" · ");
  }

  async _renderTrend(alarm, rule) {
    const el = this.shadowRoot.getElementById("trend");
    if (!el || !alarm.entity_id || !this._hass) return;
    const entityId = alarm.entity_id;
    const cached = this._trendCache.get(entityId);
    let points = cached && Date.now() - cached.at < 60000 ? cached.points : null;
    if (!points) {
      try {
        const end = new Date();
        const start = new Date(end.getTime() - 6 * 3600 * 1000);
        const result = await this._callWS({
          type: "history/history_during_period",
          start_time: start.toISOString(),
          end_time: end.toISOString(),
          entity_ids: [entityId],
          minimal_response: true,
          no_attributes: true,
          significant_changes_only: false,
        });
        points = (result?.[entityId] || [])
          .map((row) => [Number(row.lu ?? row.lc) * 1000, Number(row.s)])
          .filter(([time, value]) => Number.isFinite(time) && Number.isFinite(value));
        this._trendCache.set(entityId, { at: Date.now(), points });
      } catch (_err) {
        points = [];
      }
    }
    if (this._selectedId !== alarm.id || !this.shadowRoot.getElementById("trend")) return;
    if (points.length < 2) {
      el.innerHTML = "";
      return;
    }
    const now = Date.now();
    const series = [...points, [now, points[points.length - 1][1]]];
    const t0 = now - 6 * 3600 * 1000;
    const values = series.map(([, v]) => v);
    const threshold = Number(rule?.threshold ?? alarm.threshold);
    const hasThreshold = Number.isFinite(threshold) && ["above", "below"].includes(alarm.condition);
    let lo = Math.min(...values, hasThreshold ? threshold : Infinity);
    let hi = Math.max(...values, hasThreshold ? threshold : -Infinity);
    if (hi === lo) {
      hi += 1;
      lo -= 1;
    }
    const pad = (hi - lo) * 0.12;
    lo -= pad;
    hi += pad;
    const W = 300;
    const H = 88;
    const x = (time) => ((Math.max(time, t0) - t0) / (now - t0)) * W;
    const y = (value) => H - ((value - lo) / (hi - lo)) * H;
    let path = "";
    series.forEach(([time, value], index) => {
      const px = x(time).toFixed(1);
      const py = y(value).toFixed(1);
      if (index === 0) path += `M${px},${py}`;
      else path += `H${px}V${py}`;
    });
    const color = priorityOf(alarm.priority).color;
    const last = series[series.length - 1];
    el.innerHTML = `
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Last 6 hours of ${escapeHtml(alarm.name)}">
        ${hasThreshold ? `<line x1="0" x2="${W}" y1="${y(threshold).toFixed(1)}" y2="${y(threshold).toFixed(1)}" stroke="${color}" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>` : ""}
        <path d="${path}V${H}H0Z" fill="${color}" opacity=".08"/>
        <path d="${path}" fill="none" stroke="var(--iap-text)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
        <circle cx="${x(last[0]).toFixed(1)}" cy="${y(last[1]).toFixed(1)}" r="3" fill="${color}"/>
      </svg>
      <div class="trend-cap"><span>−6 H</span><span>${hasThreshold ? `LIMIT ${escapeHtml(this._conditionText(alarm, this._unit(alarm)))}` : ""}</span><span>NOW</span></div>`;
  }

  _updateLiveValue() {
    if (!this._built || !this._selectedId) return;
    const alarm = this._alarms.find((a) => a.id === this._selectedId);
    if (!alarm) return;
    const state = this._hass?.states?.[alarm.entity_id];
    if (!state || state === this._lastLiveState) return;
    this._lastLiveState = state;
    const el = this.shadowRoot.getElementById("live-value");
    if (!el) return;
    const { value, unit } = this._displayValue(alarm);
    el.innerHTML = `${escapeHtml(value || "—")}<small>${escapeHtml(unit)}</small>`;
  }

  /* ---------- History ---------- */

  _historyQuery() {
    const { priority, eventType, range } = this._historyFilters;
    const query = { type: `${DOMAIN}/list_history`, limit: 500 };
    const hours = { "24h": 24, "7d": 168, "30d": 720 }[range];
    if (hours) query.start_time = new Date(Date.now() - hours * 3600 * 1000).toISOString();
    if (priority !== "all") query.priority = priority;
    if (eventType !== "all") query.event_type = eventType;
    return query;
  }

  async _loadHistory() {
    try {
      const history = await this._callWS(this._historyQuery());
      this._history = history?.events || [];
      this._renderHistory();
    } catch (err) {
      this._toast(`History could not load: ${err?.message || err}`, true);
    }
  }

  _renderHistory() {
    const body = this.shadowRoot.getElementById("history-body");
    const query = this._historyFilters.q.trim().toLowerCase();
    const rows = this._history.filter((event) => {
      if (!query) return true;
      return [event.tag, event.rule_id, event.name, event.message, event.operator, event.event_type, event.area]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
    body.innerHTML = rows.length
      ? rows.map((event) => `<tr>
          <td>${formatClock(event.timestamp)}</td>
          <td>${event.priority ? glyph(event.priority, "filled", 18) : ""}</td>
          <td class="event">${escapeHtml(String(event.event_type || "").replace(/_/g, " ").toUpperCase())}</td>
          <td class="mono">${escapeHtml(event.tag || event.rule_id || "")}</td>
          <td class="msg-cell">${escapeHtml(event.name || event.message || "")}</td>
          <td class="mono">${escapeHtml([event.previous_state, event.new_state].filter(Boolean).join(" → "))}</td>
          <td>${escapeHtml(event.source_value ?? event.source_state ?? "")}</td>
          <td>${escapeHtml(event.operator || "")}</td>
        </tr>`).join("")
      : `<tr><td colspan="8" class="empty">No events in this range</td></tr>`;
  }

  async _exportCsv() {
    try {
      const payload = { type: `${DOMAIN}/export_history`, format: "csv" };
      const start = this._historyQuery().start_time;
      if (start) payload.start_time = start;
      const result = await this._callWS(payload);
      const rows = result?.rows || [];
      const columns = ["timestamp", "event_type", "priority", "rule_id", "tag", "name", "area", "system", "previous_state", "new_state", "source_value", "source_state", "operator", "message"];
      const cell = (value) => {
        const text = value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
        return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
      };
      const csv = [columns.join(","), ...rows.map((row) => columns.map((column) => cell(row[column])).join(","))].join("\n");
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `industrial-alarms-history-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      this._toast(result?.truncated ? `Exported the first ${rows.length} events. Narrow the time range to export the rest.` : `Exported ${rows.length} events`);
    } catch (err) {
      this._toast(`Export failed: ${err?.message || err}`, true);
    }
  }

  /* ---------- Rules ---------- */

  _renderRules() {
    const root = this.shadowRoot;
    const auto = this._rules.filter((rule) => String(rule.id || "").startsWith("auto_")).length;
    const inAlarm = this._rules.filter((rule) => this._isActive(this._alarmFor(rule.id) || {})).length;
    root.getElementById("rules-summary").textContent = `${this._rules.length} rules · ${inAlarm} in alarm${auto ? ` · ${auto} auto-generated` : ""}`;
    root.getElementById("rules-mode-board").setAttribute("aria-pressed", String(this._rulesMode === "board"));
    root.getElementById("rules-mode-list").setAttribute("aria-pressed", String(this._rulesMode === "list"));
    root.getElementById("suggest").hidden = !this._suggestOpen;
    root.getElementById("suggest-chip").setAttribute("aria-expanded", String(this._suggestOpen));
    this._renderSuggestResult();
    const main = root.getElementById("rules-main");
    if (!this._rules.length) {
      main.innerHTML = `<div class="empty">No rules yet. Use SUGGEST RULES to generate rules from your sensors, or + NEW RULE.</div>`;
    } else if (this._rulesMode === "board") {
      main.innerHTML = `<div class="board">${this._rules.map((rule) => this._ruleTile(rule)).join("")}</div>`;
    } else {
      main.innerHTML = this._rulesTable(auto);
      this._wireColumnResizers();
    }
    this._renderEditor();
  }

  _alarmFor(ruleId) {
    return this._alarms.find((alarm) => alarm.id === ruleId);
  }

  _ruleTile(rule) {
    const alarm = this._alarmFor(rule.id) || {};
    const state = alarm.lifecycle_state || (rule.enabled === false ? "DISABLED" : "NORMAL");
    const lit = ACTIVE_STATES.includes(state);
    const priority = PRIORITIES[rule.priority] ? rule.priority : "info";
    const classes = ["tile", `p-${priority}`, lit ? "lit" : "", state === "ACTIVE_UNACK" ? "unack" : "", state === "CLEARED_UNACK" ? "cleared-unack" : "", state === "SHELVED" ? "shelved" : "", state === "DISABLED" || rule.enabled === false ? "disabled" : "", this._editor?.id === rule.id ? "editing" : ""].filter(Boolean).join(" ");
    const labels = { NORMAL: "NORMAL", ACTIVE_UNACK: "IN ALARM · UNACK", ACTIVE_ACK: "IN ALARM", CLEARED_UNACK: "CLEARED · UNACK", SHELVED: "SHELVED", DISABLED: "DISABLED" };
    return `<button type="button" class="${classes}" data-action="edit-rule" data-id="${escapeHtml(rule.id)}" aria-label="${escapeHtml(rule.name)}, ${labels[state] || state}. Edit rule">
      <span class="t mono">${escapeHtml(rule.tag || rule.id)}</span>
      <span class="n">${escapeHtml(rule.name)}</span>
      <span class="c">P${priorityOf(priority).n} · ${labels[state] || state}</span>
    </button>`;
  }

  _rulesTable(autoCount) {
    const selected = this._selectedRuleIds.size;
    return `
      <div class="bulk">
        <span>${selected} selected · about ${selected * 4} entities</span>
        <button type="button" class="chip" data-action="select-all-rules">SELECT ALL</button>
        <button type="button" class="chip" data-action="deselect-all-rules" ${selected ? "" : "disabled"}>DESELECT ALL</button>
        <span class="spacer"></span>
        <button type="button" class="chip danger" data-action="delete-selected-rules" ${selected ? "" : "disabled"}>DELETE SELECTED</button>
        <button type="button" class="chip danger" data-action="remove-auto-generated-rules" ${autoCount ? "" : "disabled"}>REMOVE AUTO-GENERATED (${autoCount})</button>
      </div>
      <div class="table-shell">
        <table data-table-id="rules">
          <thead><tr><th></th><th>PRI</th><th>TAG / ID</th><th>NAME</th><th>ENTITY</th><th>CONDITION</th><th>ENABLED</th><th></th></tr></thead>
          <tbody>${this._rules.map((rule) => `<tr>
            <td><input class="check" type="checkbox" data-rule-select="${escapeHtml(rule.id)}" aria-label="Select ${escapeHtml(rule.name)}" ${this._selectedRuleIds.has(rule.id) ? "checked" : ""}></td>
            <td>${glyph(rule.priority, "filled", 18)}</td>
            <td class="mono">${escapeHtml(rule.tag || rule.id)}</td>
            <td class="msg-cell">${escapeHtml(rule.name)}</td>
            <td class="mono">${escapeHtml(rule.entity_id)}</td>
            <td>${escapeHtml(this._ruleSummary(rule))}</td>
            <td><button type="button" class="switch" role="switch" aria-checked="${rule.enabled !== false}" data-action="toggle-rule" data-id="${escapeHtml(rule.id)}" aria-label="Rule enabled"><span></span></button></td>
            <td><button type="button" class="link" data-action="edit-rule" data-id="${escapeHtml(rule.id)}">Edit</button></td>
          </tr>`).join("")}</tbody>
        </table>
      </div>`;
  }

  _openEditor(mode, source = {}) {
    const draft = { ...EMPTY_RULE };
    Object.keys(EMPTY_RULE).forEach((key) => {
      if (source[key] !== undefined && source[key] !== null) draft[key] = source[key];
    });
    if (mode === "clone") {
      draft.id = `${source.id}_copy`;
      draft.name = `${source.name} (copy)`;
      if (draft.tag) draft.tag = `${draft.tag}-COPY`;
    }
    this._editor = { mode: mode === "edit" ? "edit" : "create", id: mode === "edit" ? source.id : null, original: mode === "edit" ? { ...source } : null, draft, error: "" };
    this._page = "rules";
    this._editorRendered = false;
    this._renderAll();
    this.shadowRoot.querySelector("#rule-editor [data-rule-field]")?.focus();
  }

  _renderEditor() {
    const el = this.shadowRoot.getElementById("rule-editor");
    const split = this.shadowRoot.querySelector(".rules-split");
    split.classList.toggle("with-editor", Boolean(this._editor));
    el.classList.toggle("open", Boolean(this._editor));
    if (!this._editor) {
      el.innerHTML = "";
      this._editorRendered = false;
      return;
    }
    if (this._editorRendered) {
      const error = el.querySelector(".form-error");
      if (error) {
        error.textContent = this._editor.error || "";
        error.hidden = !this._editor.error;
      }
      return;
    }
    this._editorRendered = true;
    const { mode, draft } = this._editor;
    const entityOptions = Object.keys(this._hass?.states || {})
      .filter((id) => /^(sensor|binary_sensor|switch|input_boolean|input_number|climate|water_heater|lock|cover|device_tracker|person)\./.test(id))
      .sort()
      .map((id) => `<option value="${escapeHtml(id)}"></option>`)
      .join("");
    const field = (name, label, type = "text", attrs = "") => `<label class="f"><span>${label}</span><input class="field" type="${type}" data-rule-field="${name}" value="${escapeHtml(draft[name])}" ${attrs}></label>`;
    const check = (name, label) => `<label class="ck"><input type="checkbox" data-rule-field="${name}" ${draft[name] ? "checked" : ""}><span>${label}</span></label>`;
    el.innerHTML = `
      <header class="status-head editor-head">
        ${glyph(draft.priority, "filled", 30)}
        <div><h2>${mode === "edit" ? "Edit rule" : "New rule"}</h2><p class="mono">${escapeHtml(mode === "edit" ? draft.id : "Rules watch one entity each")}</p></div>
      </header>
      <form class="rule-form" data-form="rule" novalidate>
        <datalist id="iap-entities">${entityOptions}</datalist>
        ${field("name", "Name", "text", 'required maxlength="120"')}
        ${field("entity_id", "Entity", "text", 'list="iap-entities" required spellcheck="false"')}
        <div class="two">
          <label class="f"><span>Condition</span><select class="field" data-rule-field="condition">${CONDITIONS.map(([key, label]) => `<option value="${key}" ${draft.condition === key ? "selected" : ""}>${label}</option>`).join("")}</select></label>
          ${field("threshold", "Threshold", "text", 'spellcheck="false"')}
        </div>
        <label class="f"><span>Priority</span><select class="field" data-rule-field="priority">${PRIORITY_KEYS.map((key) => `<option value="${key}" ${draft.priority === key ? "selected" : ""}>${PRIORITIES[key].n} · ${PRIORITIES[key].name}</option>`).join("")}</select></label>
        <div class="three">
          ${field("tag", "Tag", "text", 'spellcheck="false"')}
          ${field("area", "Area")}
          ${field("system", "System")}
        </div>
        <div class="three">
          ${field("delay_on_seconds", "On-delay s", "number", 'min="0" step="1"')}
          ${field("delay_off_seconds", "Off-delay s", "number", 'min="0" step="1"')}
          ${field("deadband", "Deadband", "number", 'min="0" step="any"')}
        </div>
        ${field("min_active_duration_seconds", "Minimum active time s", "number", 'min="0" step="1"')}
        <label class="f"><span>Instructions</span><textarea class="field" rows="3" data-rule-field="instructions">${escapeHtml(draft.instructions)}</textarea></label>
        ${mode === "create" ? field("id", "Rule ID (optional)", "text", 'spellcheck="false" pattern="[a-z0-9_]*"') : ""}
        <div class="checks">
          ${check("enabled", "Enabled")}
          ${check("audible", "Sounds the horn")}
          ${check("requires_ack", "Needs acknowledgement")}
          ${check("shelving_allowed", "Can be shelved")}
        </div>
        <p class="form-error" role="alert" ${this._editor.error ? "" : "hidden"}>${escapeHtml(this._editor.error)}</p>
        <div class="actions">
          <div class="pair">
            <button type="submit" class="btn ack">${mode === "edit" ? "SAVE RULE" : "CREATE RULE"}</button>
            <button type="button" class="btn" data-action="close-editor">CANCEL</button>
          </div>
          ${mode === "edit" ? `<div class="pair">
            <button type="button" class="btn" data-action="clone-rule" data-id="${escapeHtml(this._editor.id)}">CLONE</button>
            <button type="button" class="btn danger" data-action="delete-rule" data-id="${escapeHtml(this._editor.id)}">DELETE</button>
          </div>` : ""}
        </div>
      </form>`;
    el.querySelector("[data-form='rule']").addEventListener("submit", (event) => {
      event.preventDefault();
      this._saveRule();
    });
  }

  _ruleFieldValue(name, value) {
    if (BOOLEAN_RULE_FIELDS.has(name)) return Boolean(value);
    if (NUMERIC_RULE_FIELDS.has(name)) return value === "" ? null : Number(value);
    return value;
  }

  async _saveRule() {
    const editor = this._editor;
    if (!editor) return;
    const draft = editor.draft;
    if (!String(draft.name).trim() || !String(draft.entity_id).trim()) {
      editor.error = "Name and entity are required.";
      this._renderEditor();
      return;
    }
    const fields = {};
    Object.keys(EMPTY_RULE).forEach((key) => {
      let value = draft[key];
      if (key === "threshold") {
        if (value === "" || value === null) return;
        const numeric = Number(value);
        value = Number.isFinite(numeric) && String(value).trim() !== "" ? numeric : value;
      } else {
        value = this._ruleFieldValue(key, value);
      }
      if (value === null || value === "") return;
      fields[key] = value;
    });
    try {
      if (editor.mode === "edit") {
        const changes = {};
        Object.entries(fields).forEach(([key, value]) => {
          if (key === "id") return;
          if (editor.original?.[key] !== value) changes[key] = value;
        });
        if (!Object.keys(changes).length) {
          this._closeEditor();
          return;
        }
        await this._callWS({ type: `${DOMAIN}/update_rule`, rule_id: editor.id, changes });
        this._toast("Rule saved");
      } else {
        await this._callWS({ type: `${DOMAIN}/create_rule`, rule: fields });
        this._toast("Rule created");
      }
      this._closeEditor();
      await this._load();
    } catch (err) {
      editor.error = err?.message || String(err);
      this._renderEditor();
    }
  }

  _closeEditor() {
    this._editor = null;
    this._editorRendered = false;
    this._renderRules();
  }

  _renderSuggestResult() {
    const el = this.shadowRoot.getElementById("suggest-result");
    const count = this._suggestedRules.length;
    const selected = this._selectedSuggestedRuleIds.size;
    const message = this._suggestedRulesResult ? `<p class="muted">${escapeHtml(this._suggestedRulesResult)}</p>` : "";
    if (!count) {
      el.innerHTML = message;
      return;
    }
    el.innerHTML = `${message}
      <div class="bulk">
        <span>${count} suggested · ${selected} selected · about ${selected * 4} entities</span>
        <button type="button" class="chip" data-action="select-all-suggested-rules" ${selected === count ? "disabled" : ""}>SELECT ALL</button>
        <button type="button" class="chip" data-action="deselect-all-suggested-rules" ${selected ? "" : "disabled"}>DESELECT ALL</button>
        <span class="spacer"></span>
        <button type="button" class="chip strong" data-action="create-selected-suggested-rules" ${selected ? "" : "disabled"}>CREATE SELECTED</button>
        <button type="button" class="chip strong" data-action="create-all-suggested-rules">CREATE ALL</button>
      </div>
      <div class="table-shell">
        <table data-table-id="suggested-rules">
          <thead><tr><th></th><th>PRI</th><th>ID</th><th>NAME</th><th>ENTITY</th><th>CONDITION</th></tr></thead>
          <tbody>${this._suggestedRules.map((rule) => `<tr>
            <td><input class="check" type="checkbox" data-suggested-select="${escapeHtml(rule.id)}" aria-label="Select ${escapeHtml(rule.name)}" ${this._selectedSuggestedRuleIds.has(rule.id) ? "checked" : ""}></td>
            <td>${glyph(rule.priority, "filled", 18)}</td>
            <td class="mono">${escapeHtml(rule.id)}</td>
            <td class="msg-cell">${escapeHtml(rule.name)}</td>
            <td class="mono">${escapeHtml(rule.entity_id)}</td>
            <td>${escapeHtml(this._ruleSummary(rule))}</td>
          </tr>`).join("")}</tbody>
        </table>
      </div>`;
  }

  _suggestionPayload() {
    const fields = {};
    Object.entries(this._suggestionDraft).forEach(([key, value]) => {
      if (value !== "" && value !== null) fields[key] = Number(value);
    });
    return fields;
  }

  async _previewSuggestedRules() {
    try {
      const result = await this._callWS({ type: `${DOMAIN}/list_suggested_rules`, ...this._suggestionPayload() });
      this._suggestedRules = result?.suggested || [];
      this._selectedSuggestedRuleIds = new Set(this._suggestedRules.map((rule) => rule.id));
      this._suggestedRulesResult = this._suggestedRules.length
        ? `Previewing ${this._suggestedRules.length} suggested rules, about ${this._suggestedRules.length * 4} entities`
        : "No new rules to suggest for these thresholds";
    } catch (err) {
      this._suggestedRulesResult = err?.message || String(err);
    }
    this._renderSuggestResult();
  }

  async _createSuggestedRules(ruleIds) {
    const count = ruleIds.length;
    if (!count) return;
    const ok = await this._confirm(`Create ${count} suggested rules? This adds about ${count * 4} entities to Home Assistant.`, "CREATE");
    if (!ok) return;
    try {
      const result = await this._callWS({ type: `${DOMAIN}/create_suggested_rules`, ...this._suggestionPayload(), rule_ids: ruleIds });
      const created = result?.created_count || 0;
      const skipped = result?.skipped_rule_ids?.length || 0;
      this._suggestedRulesResult = created
        ? `Created ${created} rules${skipped ? `, skipped ${skipped} that already exist` : ""}`
        : "No new rules were created";
      this._selectedSuggestedRuleIds = new Set();
      await this._load();
    } catch (err) {
      this._suggestedRulesResult = err?.message || String(err);
      this._renderSuggestResult();
    }
  }

  async _deleteRules(payload, count, label) {
    if (!count) return;
    const ok = await this._confirm(`Delete ${count} ${label}? About ${count * 4} alarm entities are removed. The sensors they watch are not touched.`, "DELETE");
    if (!ok) return;
    try {
      const result = await this._callWS({ type: `${DOMAIN}/delete_rules`, ...payload });
      const deleted = result?.deleted_count || 0;
      const removed = result?.removed_entity_count || 0;
      this._toast(`Deleted ${deleted} rules and ${removed} entities`);
      this._selectedRuleIds = new Set();
      await this._load();
    } catch (err) {
      this._toast(err?.message || String(err), true);
    }
  }

  /* ---------- SYS page ---------- */

  _renderSys() {
    const sound = this._sound || {};
    const audible = (sound.active_audible_alarms || []).length;
    this.shadowRoot.getElementById("view-sys").innerHTML = `
      <div class="sys">
        <section>
          <h3>SOUND</h3>
          <dl>
            <dt>Mode</dt><dd class="mono">${escapeHtml(String(sound.sound_mode || "browser_only").replace(/_/g, " ").toUpperCase())}</dd>
            <dt>Browser sound</dt><dd>${sound.browser_enabled === false ? "Off in options" : this._audioEnabled ? "On in this browser" : "Waiting for a tap"}</dd>
            <dt>Media player sound</dt><dd>${sound.media_player_enabled ? "On" : "Off"}</dd>
            <dt>Horn</dt><dd>${sound.horn_active ? "Sounding" : "Quiet"}</dd>
            <dt>Audible alarms</dt><dd>${audible}</dd>
          </dl>
          <p>Browsers only play sound after you interact with the page. Press TEST HORN once on every screen that should sound, such as a wall tablet.</p>
          <div class="pair"><button type="button" class="btn" data-action="test-sound">TEST HORN</button><button type="button" class="btn" data-action="silence">SILENCE</button></div>
        </section>
        <section>
          <h3>DISPLAY</h3>
          <dl>
            <dt>Row density</dt><dd><button type="button" class="switch" role="switch" aria-checked="${this._density === "compact"}" data-action="toggle-density" aria-label="Compact rows"><span></span></button></dd>
            <dt>Flash unacknowledged</dt><dd><button type="button" class="switch" role="switch" aria-checked="${this._flashPref !== false}" data-action="toggle-flash" aria-label="Flash unacknowledged alarms" ${this._display?.enable_flashing === false ? "disabled" : ""}><span></span></button></dd>
            <dt>Reduced motion</dt><dd>Steady marker instead of flashing</dd>
          </dl>
          <p>Display settings are saved in this browser only.${this._display?.enable_flashing === false ? " Flashing is turned off in the integration options." : ""}</p>
        </section>
        <section>
          <h3>SHORTCUTS</h3>
          <dl class="keys">
            <dt><kbd>↑</kbd> <kbd>↓</kbd></dt><dd>Move through alarms</dd>
            <dt><kbd>A</kbd></dt><dd>Acknowledge the selected alarm</dd>
            <dt><kbd>S</kbd></dt><dd>Silence the horn</dd>
          </dl>
        </section>
        <section>
          <h3>PRIORITY KEY</h3>
          <ul class="key-list">${PRIORITY_KEYS.map((key) => `<li>${glyph(key, "filled", 20)}<span>${PRIORITIES[key].n} · ${PRIORITIES[key].name}</span></li>`).join("")}</ul>
          <ul class="key-list">
            <li>${glyph("high", "filled", 20)}<span>Active</span></li>
            <li>${glyph("high", "hollow", 20)}<span>Cleared, not yet acknowledged</span></li>
            <li>${glyph("high", "struck", 20)}<span>Shelved</span></li>
            <li>${glyph("high", "dashed", 20)}<span>Disabled</span></li>
          </ul>
        </section>
      </div>`;
  }

  /* ---------- Actions ---------- */

  async _run(action, success) {
    try {
      await action();
      if (success) this._toast(success);
    } catch (err) {
      this._toast(err?.message || String(err), true);
    }
    this._scheduleLoad(0);
  }

  _ack(ruleId) {
    return this._run(() => this._callWS({ type: `${DOMAIN}/acknowledge`, rule_id: ruleId }));
  }

  _ackAll() {
    return this._run(() => this._callWS({ type: `${DOMAIN}/acknowledge_all` }), "All alarms acknowledged");
  }

  _ackPriorities(priorities, silence) {
    const targets = this._alarms.filter((alarm) => priorities.includes(alarm.priority) && this._isUnack(alarm));
    return this._run(async () => {
      if (silence) await this._callWS({ type: `${DOMAIN}/silence` });
      await Promise.all(targets.map((alarm) => this._callWS({ type: `${DOMAIN}/acknowledge`, rule_id: alarm.id })));
    });
  }

  _silence() {
    this._stopHornLoop();
    return this._run(() => this._callWS({ type: `${DOMAIN}/silence` }), "Horn silenced");
  }

  _shelve(ruleId, minutes) {
    const label = SHELVE_PRESETS.find(([value]) => value === minutes)?.[2] || `${minutes} minutes`;
    return this._run(() => this._callWS({ type: `${DOMAIN}/shelve`, rule_id: ruleId, duration_minutes: minutes }), `Shelved for ${label}`);
  }

  _callService(service, ruleId, success) {
    return this._run(() => this._hass.callService(DOMAIN, service, { rule_id: ruleId }), success);
  }

  async _toggleRule(ruleId) {
    const rule = this._rules.find((r) => r.id === ruleId);
    if (!rule) return;
    await this._run(() => this._callWS({ type: `${DOMAIN}/update_rule`, rule_id: ruleId, changes: { enabled: rule.enabled === false } }), rule.enabled === false ? "Rule enabled" : "Rule disabled");
  }

  async _deleteRule(ruleId) {
    const rule = this._rules.find((r) => r.id === ruleId);
    const ok = await this._confirm(`Delete the rule "${rule?.name || ruleId}"? Its alarm entities are removed. The sensor it watches is not touched.`, "DELETE");
    if (!ok) return;
    this._editor = null;
    this._editorRendered = false;
    await this._run(() => this._callWS({ type: `${DOMAIN}/delete_rule`, rule_id: ruleId }), "Rule deleted");
  }

  async _testSound() {
    this._audioEnabled = true;
    this._playBrowserHorn(true);
    this._renderMaster();
    await this._run(() => this._callWS({ type: `${DOMAIN}/test_sound`, priority: "critical" }));
  }

  _enableAudio() {
    this._audioEnabled = true;
    this._playBrowserHorn(true);
    this._syncHorn();
    this._renderMaster();
    if (this._page === "sys") this._renderSys();
  }

  /* ---------- Browser horn: its own cadence, never tied to hass updates ---------- */

  _syncHorn() {
    const shouldSound = Boolean(this._sound?.horn_active) && this._audioEnabled && this._sound?.browser_enabled !== false && this.isConnected;
    if (shouldSound && !this._hornTimer) {
      this._maybePlayBrowserHorn();
      this._hornTimer = window.setInterval(() => this._maybePlayBrowserHorn(), this._browserHornIntervalMs);
    } else if (!shouldSound) {
      this._stopHornLoop();
    }
  }

  _stopHornLoop() {
    window.clearInterval(this._hornTimer);
    this._hornTimer = undefined;
  }

  _maybePlayBrowserHorn() {
    if (document.visibilityState === "hidden") return;
    const now = Date.now();
    if (now - this._lastBrowserHornAt < this._browserHornIntervalMs - 100) return;
    this._lastBrowserHornAt = now;
    this._playBrowserHorn();
  }

  _playBrowserHorn(once = false) {
    if (!this._audioEnabled && !once) return;
    try {
      const context = this._audioContext || new AudioContext();
      this._audioContext = context;
      if (context.state === "suspended") context.resume();
      [0, 0.22].forEach((offset) => {
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        const start = context.currentTime + offset;
        oscillator.type = "square";
        oscillator.frequency.setValueAtTime(offset ? 660 : 880, start);
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.2, start + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.18);
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start(start);
        oscillator.stop(start + 0.2);
      });
    } catch (_err) {
      this._audioEnabled = false;
    }
  }

  /* ---------- UI helpers ---------- */

  _confirm(message, label = "CONFIRM") {
    const dialog = this.shadowRoot.getElementById("confirm");
    this.shadowRoot.getElementById("confirm-text").textContent = message;
    this.shadowRoot.getElementById("confirm-ok").textContent = label;
    if (typeof dialog.showModal !== "function") return Promise.resolve(window.confirm(message));
    return new Promise((resolve) => {
      const onClose = () => {
        dialog.removeEventListener("close", onClose);
        resolve(dialog.returnValue === "ok");
      };
      dialog.addEventListener("close", onClose);
      dialog.returnValue = "cancel";
      dialog.showModal();
    });
  }

  _toast(message, isError = false) {
    const toast = this.shadowRoot.getElementById("toast");
    toast.textContent = message;
    toast.classList.toggle("bad", isError);
    toast.hidden = false;
    window.clearTimeout(this._toastTimer);
    this._toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, isError ? 7000 : 3500);
  }

  _toggleSidebar() {
    this.dispatchEvent(new CustomEvent("hass-toggle-menu", { detail: { open: true }, bubbles: true, composed: true }));
  }

  _setMembership(set, value, selected) {
    if (!value) return;
    if (selected) set.add(value);
    else set.delete(value);
  }

  _handleKey(event) {
    const target = event.composedPath()[0];
    if (target?.closest?.("input, textarea, select, dialog")) return;
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (!["alerts", "unack", "shelved", "disabled"].includes(this._page)) return;
    const list = this._pageAlarms();
    const index = list.findIndex((alarm) => alarm.id === this._selectedId);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = list[Math.min(list.length - 1, Math.max(0, index + (event.key === "ArrowDown" ? 1 : -1)))];
      if (next) {
        this._selectedId = next.id;
        this._renderStack();
        this._renderStatus();
        this.shadowRoot.querySelector(`.row[data-id="${CSS.escape(next.id)}"]`)?.focus();
      }
    } else if (event.key === "a" || event.key === "A") {
      const alarm = list[index];
      if (alarm && this._isUnack(alarm)) this._ack(alarm.id);
    } else if (event.key === "s" || event.key === "S") {
      if (this._sound?.horn_active) this._silence();
    }
  }

  _handleClick(event) {
    const el = event.target.closest("[data-action]");
    if (!el || el.disabled) return;
    const { action, id } = el.dataset;
    switch (action) {
      case "toggle-menu":
        this._toggleSidebar();
        break;
      case "page":
        this._page = el.dataset.page;
        this._statusOpen = false;
        this._renderAll();
        if (this._page === "history") this._loadHistory();
        break;
      case "select-alarm": {
        const collapse = this._narrow && this._statusOpen && this._selectedId === id;
        this._selectedId = id;
        this._statusOpen = !collapse;
        this._renderStack();
        this._renderStatus();
        if (this._statusOpen && this._narrow) {
          const status = this.shadowRoot.getElementById("status");
          status.classList.add("unfolding");
          window.setTimeout(() => status.classList.remove("unfolding"), 200);
        }
        break;
      }
      case "ack":
        this._ack(id);
        break;
      case "ack-all":
        this._ackAll();
        break;
      case "master-warn":
        this._ackPriorities(["critical"], true);
        break;
      case "master-caut":
        this._ackPriorities(["high", "medium"], false);
        break;
      case "silence":
        this._silence();
        break;
      case "enable-audio":
        this._enableAudio();
        break;
      case "test-sound":
        this._testSound();
        break;
      case "shelve":
        this._shelve(id, Number(el.dataset.minutes));
        break;
      case "unshelve":
        this._callService("unshelve_alarm", id, "Alarm unshelved");
        break;
      case "disable-alarm":
        this._callService("disable_alarm", id, "Alarm disabled");
        break;
      case "enable-alarm":
        this._callService("enable_alarm", id, "Alarm enabled");
        break;
      case "toggle-density":
        this._density = this._density === "compact" ? "comfortable" : "compact";
        storageSet("density", this._density);
        this._renderAll();
        break;
      case "toggle-flash":
        this._flashPref = this._flashPref === false;
        storageSet("flash", this._flashPref);
        this._renderAll();
        break;
      case "export-csv":
        this._exportCsv();
        break;
      case "rules-mode":
        this._rulesMode = el.dataset.mode;
        this._renderRules();
        break;
      case "toggle-suggest":
        this._suggestOpen = !this._suggestOpen;
        this._renderRules();
        break;
      case "new-rule":
        this._openEditor("create");
        break;
      case "edit-rule": {
        const rule = this._rules.find((r) => r.id === id);
        if (rule) this._openEditor("edit", rule);
        break;
      }
      case "clone-rule": {
        const rule = this._rules.find((r) => r.id === id);
        if (rule) this._openEditor("clone", rule);
        break;
      }
      case "delete-rule":
        this._deleteRule(id);
        break;
      case "close-editor":
        this._closeEditor();
        break;
      case "toggle-rule":
        this._toggleRule(id);
        break;
      case "select-all-rules":
        this._selectedRuleIds = new Set(this._rules.map((rule) => rule.id));
        this._renderRules();
        break;
      case "deselect-all-rules":
        this._selectedRuleIds = new Set();
        this._renderRules();
        break;
      case "delete-selected-rules": {
        const ids = [...this._selectedRuleIds];
        this._deleteRules({ rule_ids: ids }, ids.length, "selected rules");
        break;
      }
      case "remove-auto-generated-rules": {
        const count = this._rules.filter((rule) => String(rule.id || "").startsWith("auto_")).length;
        this._deleteRules({ generated_only: true }, count, "auto-generated rules");
        break;
      }
      case "preview-suggested-rules":
        this._previewSuggestedRules();
        break;
      case "select-all-suggested-rules":
        this._selectedSuggestedRuleIds = new Set(this._suggestedRules.map((rule) => rule.id));
        this._renderSuggestResult();
        break;
      case "deselect-all-suggested-rules":
        this._selectedSuggestedRuleIds = new Set();
        this._renderSuggestResult();
        break;
      case "create-selected-suggested-rules":
        this._createSuggestedRules([...this._selectedSuggestedRuleIds]);
        break;
      case "create-all-suggested-rules":
        this._createSuggestedRules(this._suggestedRules.map((rule) => rule.id));
        break;
      default:
        break;
    }
  }

  _handleInput(event) {
    const target = event.target;
    const input = target.dataset?.input;
    if (input === "alarm-search") {
      this._filters.q = target.value;
      this._renderStack();
      this._renderStatus();
    } else if (input === "history-search") {
      this._historyFilters.q = target.value;
      this._renderHistory();
    } else if (target.dataset?.suggest) {
      this._suggestionDraft[target.dataset.suggest] = target.value;
      this._suggestedRules = [];
      this._selectedSuggestedRuleIds = new Set();
      this._suggestedRulesResult = "Preview again after changing thresholds";
      this._renderSuggestResult();
    } else if (target.dataset?.ruleField && this._editor) {
      const name = target.dataset.ruleField;
      this._editor.draft[name] = target.type === "checkbox" ? target.checked : target.value;
    }
  }

  _handleChange(event) {
    const target = event.target;
    const input = target.dataset?.input;
    if (input === "alarm-priority") {
      this._filters.priority = target.value;
      this._renderStack();
      this._renderStatus();
    } else if (input === "alarm-area") {
      this._filters.area = target.value;
      this._renderStack();
      this._renderStatus();
    } else if (input === "history-type" || input === "history-priority" || input === "history-range") {
      const key = { "history-type": "eventType", "history-priority": "priority", "history-range": "range" }[input];
      this._historyFilters[key] = target.value;
      this._loadHistory();
    } else if (target.dataset?.ruleSelect) {
      this._setMembership(this._selectedRuleIds, target.dataset.ruleSelect, target.checked);
      this._renderRules();
    } else if (target.dataset?.suggestedSelect) {
      this._setMembership(this._selectedSuggestedRuleIds, target.dataset.suggestedSelect, target.checked);
      this._renderSuggestResult();
    } else if (target.dataset?.ruleField && this._editor) {
      const name = target.dataset.ruleField;
      this._editor.draft[name] = target.type === "checkbox" ? target.checked : target.value;
      if (name === "priority") {
        const head = this.shadowRoot.querySelector(".editor-head .g");
        if (head) head.outerHTML = glyph(target.value, "filled", 30);
      }
    }
  }

  _wireColumnResizers() {
    this.shadowRoot.querySelectorAll("table[data-table-id]").forEach((table) => {
      const tableId = table.dataset.tableId;
      const headers = Array.from(table.querySelectorAll("thead th"));
      const saved = this._columnWidths[tableId] || {};
      headers.forEach((header, index) => {
        if (saved[index]) header.style.width = `${saved[index]}px`;
        if (header.querySelector(".col-resizer")) return;
        header.classList.add("resizable-column");
        const handle = document.createElement("span");
        handle.className = "col-resizer";
        handle.addEventListener("pointerdown", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const startX = event.clientX;
          const startWidth = header.getBoundingClientRect().width;
          const onMove = (moveEvent) => {
            const width = Math.max(48, startWidth + moveEvent.clientX - startX);
            this._columnWidths[tableId] = this._columnWidths[tableId] || {};
            this._columnWidths[tableId][index] = width;
            header.style.width = `${width}px`;
          };
          const onUp = () => {
            document.removeEventListener("pointermove", onMove);
            document.removeEventListener("pointerup", onUp);
            document.removeEventListener("pointercancel", onUp);
          };
          document.addEventListener("pointermove", onMove);
          document.addEventListener("pointerup", onUp);
          document.addEventListener("pointercancel", onUp);
        });
        header.appendChild(handle);
      });
    });
  }

  _styles() {
    return `
      :host {
        --iap-bg: #05080b; --iap-panel: #0b1116; --iap-panel-2: #0f171d; --iap-line: #1c2730; --iap-line-2: #2a3843;
        --iap-text: #d8e1e7; --iap-dim: #a3b0ba; --iap-faint: #7d8b96; --iap-focus: #7fd8ff;
        --iap-crit: #ff4036; --iap-high: #ffab1a; --iap-med: #f0d23a; --iap-low: #3cc8e2; --iap-info: #e9eef2;
        --iap-sans: "B612", "Segoe UI", Roboto, system-ui, sans-serif;
        --iap-mono: "B612 Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
        --iap-flash: 1s;
        display: block; min-height: 100%; background: var(--iap-bg); color: var(--iap-text);
        font: 14px/1.45 var(--iap-sans); color-scheme: dark;
      }
      * { box-sizing: border-box; }
      ::selection { background: #1f4d63; color: #fff; }
      button, input, select, textarea { font: inherit; color: inherit; }
      :focus-visible { outline: 2px solid var(--iap-focus); outline-offset: 2px; }
      [hidden] { display: none !important; }
      .mono { font-family: var(--iap-mono); }
      .muted { color: var(--iap-dim); font-size: 12px; }
      .panel { min-height: 100vh; display: flex; flex-direction: column; font-variant-numeric: tabular-nums; }
      .g { display: block; flex: none; }
      .g text { font: 700 10px var(--iap-sans); }
      @keyframes iap-blink { 50% { opacity: .25; } }
      @keyframes iap-unlit { 50% { background: #0a0f13; color: var(--lit); border-color: var(--lit); } }
      @keyframes iap-glyph-empty { 50% { fill: none; } }
      @keyframes iap-glyph-fill { 50% { fill: var(--gc); } }
      @keyframes iap-num-colour { 50% { fill: var(--gc); } }
      @keyframes iap-num-dark { 50% { fill: #050505; } }
      @keyframes iap-unfold { from { clip-path: inset(0 0 100% 0); } to { clip-path: inset(0 0 0 0); } }

      /* Master strip */
      .master { display: grid; grid-template-columns: auto auto 1fr auto auto; gap: 10px; align-items: stretch; padding: 12px; background: var(--iap-panel); border-bottom: 1px solid var(--iap-line); }
      .menu { display: none; background: transparent; border: 1px solid var(--iap-line-2); border-radius: 3px; cursor: pointer; padding: 0 10px; min-width: 44px; }
      .key { min-width: 112px; min-height: 64px; display: grid; grid-template-rows: 1fr auto; padding: 0; border: 1px solid var(--iap-line-2); border-radius: 3px; background: #0a0f13; cursor: pointer; overflow: hidden; text-align: center; }
      .key .face { display: grid; place-items: center; padding: 6px 10px; font-weight: 700; font-size: 13px; letter-spacing: .12em; line-height: 1.15; color: var(--iap-faint); }
      .key .cap { font-size: 10px; letter-spacing: .14em; color: var(--iap-dim); background: #070b0e; border-top: 1px solid var(--iap-line); padding: 3px 6px; }
      .key:hover:not(:disabled) { border-color: #3b4d5a; }
      .key:disabled { cursor: default; }
      .key-warn { --lit: var(--iap-crit); } .key-caut { --lit: var(--iap-high); }
      .key-warn.lit .face { background: var(--iap-crit); color: #1a0200; }
      .key-caut.lit .face { background: var(--iap-high); color: #1a0e00; }
      .key-ack:not(:disabled) .face { color: var(--iap-text); }
      .key.flash .face { animation: iap-unlit var(--iap-flash) steps(1, end) infinite; }
      .legend { display: flex; flex-wrap: wrap; align-content: center; gap: 6px 16px; padding: 0 8px; min-width: 0; }
      .lg { display: inline-flex; align-items: center; gap: 7px; color: var(--iap-dim); font-size: 12px; letter-spacing: .06em; }
      .lg b { color: var(--iap-text); font-size: 15px; min-width: 1.4ch; }
      .lg.zero b { color: var(--iap-faint); font-weight: 400; }
      .horn { display: grid; grid-template-rows: auto 1fr; min-width: 160px; border: 1px solid var(--iap-line-2); border-radius: 3px; background: #0a0f13; }
      .horn-state { display: flex; align-items: center; gap: 8px; padding: 6px 10px; font-size: 11px; letter-spacing: .14em; color: var(--iap-dim); border-bottom: 1px solid var(--iap-line); white-space: nowrap; }
      .horn-state i { width: 9px; height: 9px; border-radius: 50%; background: var(--iap-faint); flex: none; }
      .horn.on .horn-state { color: var(--iap-high); }
      .horn.on .horn-state i { background: var(--iap-high); animation: iap-blink var(--iap-flash) steps(1, end) infinite; }
      .horn button { background: transparent; border: 0; cursor: pointer; font-weight: 700; font-size: 13px; letter-spacing: .12em; padding: 8px 10px; min-height: 44px; }
      .horn button:hover { background: #111a21; }

      /* Pages */
      .pages { display: flex; gap: 2px; padding: 0 12px; background: var(--iap-panel); border-bottom: 1px solid var(--iap-line); overflow-x: auto; scrollbar-width: thin; scrollbar-color: var(--iap-line-2) transparent; }
      .pages button { background: transparent; border: 0; border-bottom: 2px solid transparent; padding: 11px 12px 9px; cursor: pointer; color: var(--iap-dim); font-size: 12px; letter-spacing: .12em; white-space: nowrap; display: inline-flex; gap: 7px; align-items: baseline; }
      .pages button span { font-size: 11px; color: var(--iap-faint); }
      .pages button[aria-selected="true"] { color: var(--iap-text); border-bottom-color: var(--iap-text); }
      .pages button.attention span { color: var(--iap-high); }
      .error { margin: 12px; padding: 10px 12px; border: 1px solid var(--iap-crit); border-radius: 3px; color: #ffd9d6; font-size: 13px; }

      /* Filters and controls */
      .filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--iap-line); }
      .field { background: #080d11; border: 1px solid var(--iap-line-2); border-radius: 3px; padding: 7px 10px; font-size: 13px; min-height: 36px; min-width: 0; }
      .field::placeholder { color: var(--iap-faint); }
      textarea.field { resize: vertical; line-height: 1.4; }
      .search { flex: 1 1 240px; }
      .spacer { flex: 1 1 auto; }
      .chip { background: transparent; border: 1px solid var(--iap-line-2); border-radius: 3px; padding: 6px 10px; cursor: pointer; color: var(--iap-dim); font-size: 12px; letter-spacing: .08em; min-height: 36px; }
      .chip:hover:not(:disabled) { color: var(--iap-text); border-color: var(--iap-dim); }
      .chip[aria-pressed="true"], .chip[aria-expanded="true"] { color: var(--iap-text); border-color: var(--iap-dim); }
      .chip.strong:not(:disabled) { color: var(--iap-text); border-color: var(--iap-text); }
      .chip.danger:not(:disabled) { color: #ff8b84; border-color: #6b2a27; }
      .chip:disabled, .btn:disabled { opacity: .45; cursor: default; }
      .seg { display: inline-flex; border: 1px solid var(--iap-line-2); border-radius: 3px; overflow: hidden; }
      .seg button { background: transparent; border: 0; padding: 7px 12px; cursor: pointer; color: var(--iap-dim); font-size: 12px; letter-spacing: .1em; min-height: 34px; }
      .seg button[aria-pressed="true"] { background: var(--iap-line-2); color: var(--iap-text); }
      .btn { min-height: 44px; border-radius: 3px; border: 1px solid var(--iap-line-2); background: #0a1015; cursor: pointer; font-weight: 700; font-size: 12.5px; letter-spacing: .12em; padding: 0 14px; }
      .btn:hover:not(:disabled) { background: #111b22; }
      .btn.ack:not(:disabled) { border-color: var(--iap-text); }
      .btn.danger:not(:disabled) { color: #ff8b84; border-color: #6b2a27; }
      .btn.big { min-height: 54px; font-size: 14px; }
      .link { background: none; border: 0; padding: 0; color: var(--iap-focus); cursor: pointer; text-decoration: underline; text-underline-offset: 3px; font-size: inherit; }
      .switch { width: 42px; height: 24px; border-radius: 12px; border: 1px solid var(--iap-line-2); background: #080d11; padding: 0; cursor: pointer; position: relative; }
      .switch span { position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: var(--iap-faint); transition: transform .15s ease; }
      .switch[aria-checked="true"] { border-color: var(--iap-dim); }
      .switch[aria-checked="true"] span { transform: translateX(18px); background: var(--iap-text); }
      .check { width: 18px; height: 18px; accent-color: var(--iap-text); }

      /* Split: stack + status */
      .view { flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0; }
      .split { display: grid; grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr); flex: 1 1 auto; min-height: 480px; }
      .stack { border-right: 1px solid var(--iap-line); min-width: 0; }
      .stack-head, .row { display: grid; grid-template-columns: 26px 92px 150px minmax(0, 1fr) 118px 104px; gap: 12px; align-items: center; padding: 0 14px; }
      .stack-head { height: 32px; font-size: 10.5px; letter-spacing: .14em; color: var(--iap-faint); border-bottom: 1px solid var(--iap-line); }
      .stack-head .c-val, .stack-head .c-state { text-align: right; }
      .row { position: relative; width: 100%; min-height: 54px; background: transparent; border: 0; border-bottom: 1px solid var(--iap-line); text-align: left; cursor: pointer; }
      .density-compact .row { min-height: 38px; }
      .density-compact .row .msg span { display: none; }
      .row:hover { background: #0c1318; }
      .row[aria-selected="true"] { background: #111c24; outline: 1px solid var(--iap-line-2); outline-offset: -1px; }
      .row.unack .g.m-filled .shape { animation: iap-glyph-empty var(--iap-flash) steps(1, end) infinite; }
      .row.unack .g.m-filled .num { animation: iap-num-colour var(--iap-flash) steps(1, end) infinite; }
      .row.unack .g.m-hollow .shape { animation: iap-glyph-fill var(--iap-flash) steps(1, end) infinite; }
      .row.unack .g.m-hollow .num { animation: iap-num-dark var(--iap-flash) steps(1, end) infinite; }
      .row .time { color: var(--iap-dim); font-size: 12.5px; white-space: nowrap; }
      .row .tag { color: var(--iap-dim); font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .row .msg { min-width: 0; }
      .row .msg b { display: block; font-size: 13px; letter-spacing: .05em; text-transform: uppercase; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .row .msg span { display: block; font-size: 11.5px; letter-spacing: .04em; color: var(--iap-faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .row .val { text-align: right; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .row .val small { color: var(--iap-faint); font-size: 11px; }
      .row .state { text-align: right; font-size: 10.5px; letter-spacing: .12em; color: var(--iap-dim); white-space: nowrap; }
      .row.unack .state { color: var(--iap-text); }
      .row.dim .msg b, .row.dim .val, .row.pending .msg b { color: var(--iap-dim); }
      .row.shelved .msg b { text-decoration: line-through; text-decoration-thickness: 1px; }
      .row.p-critical.active .msg b { color: var(--iap-crit); }
      .row.p-high.active .msg b { color: var(--iap-high); }
      .row.p-medium.active .msg b { color: var(--iap-med); }
      .row.p-low.active .msg b { color: var(--iap-low); }
      .empty { padding: 44px 16px; text-align: center; color: var(--iap-faint); font-size: 12.5px; letter-spacing: .06em; }

      /* Status page */
      .status { background: var(--iap-panel-2); min-width: 0; display: flex; flex-direction: column; }
      .panel.shell { height: 100vh; min-height: 0; }
      .shell #view-alarms { min-height: 0; }
      .shell #view-alarms .split { min-height: 0; overflow: hidden; }
      .shell #view-alarms .stack, .shell #view-alarms .status { min-height: 0; overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--iap-line-2) transparent; }
      .shell #view-alarms .status .actions { position: sticky; bottom: 0; background: var(--iap-panel-2); }
      .status.inline { border-bottom: 1px solid var(--iap-line); }
      .status.inline .status-head h2 { display: none; }
      .status.inline .status-head p { margin: 0; }
      .status.inline.unfolding { animation: iap-unfold .15s ease-out; }
      .status-head { display: grid; grid-template-columns: auto 1fr; gap: 12px; align-items: center; padding: 14px 16px 12px; border-bottom: 1px solid var(--iap-line); }
      .status-head h2 { margin: 0; font-size: 15px; line-height: 1.25; letter-spacing: .06em; text-transform: uppercase; text-wrap: balance; }
      .status-head p { margin: 3px 0 0; font-size: 11.5px; letter-spacing: .08em; color: var(--iap-dim); }
      .readout { display: grid; grid-template-columns: 1fr auto; align-items: end; gap: 6px 12px; padding: 14px 16px 6px; }
      .readout .big { font-weight: 700; font-size: 34px; line-height: 1; overflow-wrap: anywhere; }
      .readout .big small { font-size: 15px; font-weight: 400; color: var(--iap-dim); margin-left: 5px; }
      .readout .limit { text-align: right; font-size: 11px; letter-spacing: .08em; color: var(--iap-dim); }
      .readout .limit b { display: block; font-size: 14px; color: var(--iap-text); letter-spacing: 0; }
      .trend { padding: 4px 16px 10px; min-height: 12px; }
      .trend svg { display: block; width: 100%; height: 88px; }
      .trend-cap { display: flex; justify-content: space-between; margin-top: 2px; font-size: 10.5px; letter-spacing: .08em; color: var(--iap-faint); }
      .facts { margin: 0; padding: 10px 16px; display: grid; grid-template-columns: 70px 1fr; gap: 7px 12px; border-top: 1px solid var(--iap-line); font-size: 12.5px; }
      .facts dt { font-size: 10.5px; letter-spacing: .1em; color: var(--iap-faint); padding-top: 2px; }
      .facts dd { margin: 0; overflow-wrap: anywhere; }
      .instructions { margin: 0 16px 12px; padding: 10px 12px; border: 1px solid var(--iap-line-2); border-radius: 3px; font-size: 12.5px; white-space: pre-line; }
      .instructions b { display: block; margin-bottom: 4px; font-size: 10.5px; letter-spacing: .14em; color: var(--iap-dim); }
      .timeline { list-style: none; margin: 0; padding: 2px 16px 12px; font-size: 12px; }
      .timeline li { display: grid; grid-template-columns: 96px 1fr; gap: 10px; padding: 3px 0; color: var(--iap-dim); }
      .timeline li span:first-child { color: var(--iap-faint); }
      .actions { margin-top: auto; padding: 12px 16px 16px; border-top: 1px solid var(--iap-line); display: grid; gap: 8px; }
      .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
      .shelve { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
      .shelve span { margin-right: 2px; font-size: 11px; letter-spacing: .1em; color: var(--iap-dim); }
      .shelve button { min-height: 36px; min-width: 40px; padding: 0 9px; border: 1px solid var(--iap-line-2); border-radius: 3px; background: transparent; cursor: pointer; color: var(--iap-dim); font: 12px var(--iap-mono); }
      .shelve button:hover:not(:disabled) { color: var(--iap-text); border-color: var(--iap-dim); }
      .shelve button:disabled { opacity: .4; cursor: default; }

      /* Tables */
      .table-shell { overflow: auto; }
      table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
      th { position: sticky; top: 0; z-index: 1; background: var(--iap-bg); text-align: left; font-weight: 400; font-size: 10.5px; letter-spacing: .14em; color: var(--iap-faint); padding: 9px 14px; border-bottom: 1px solid var(--iap-line); white-space: nowrap; }
      td { padding: 8px 14px; border-bottom: 1px solid var(--iap-line); color: var(--iap-dim); white-space: nowrap; vertical-align: middle; }
      td .g { display: inline-block; vertical-align: middle; }
      td.event { color: var(--iap-text); font-size: 11.5px; letter-spacing: .08em; }
      td.msg-cell { color: var(--iap-text); white-space: normal; min-width: 180px; }
      .resizable-column { position: relative; padding-right: 18px; }
      .col-resizer { position: absolute; top: 0; right: 0; width: 8px; height: 100%; cursor: col-resize; touch-action: none; }
      .col-resizer:hover { background: rgba(255, 255, 255, .12); }

      /* Rules */
      .suggest { padding: 12px; border-bottom: 1px solid var(--iap-line); background: var(--iap-panel); display: grid; gap: 10px; }
      .suggest-form { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
      .suggest-form label { display: grid; gap: 4px; font-size: 11px; letter-spacing: .06em; color: var(--iap-dim); }
      .suggest-form .field { width: 130px; }
      .bulk { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px 12px; font-size: 12px; color: var(--iap-dim); }
      .rules-split { grid-template-columns: minmax(0, 1fr); }
      .rules-split.with-editor { grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr); }
      .rules-main { min-width: 0; border-right: 1px solid var(--iap-line); }
      .editor:not(.open) { display: none; }
      .board { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 6px; padding: 12px; }
      .tile { min-height: 76px; display: grid; grid-template-rows: auto 1fr auto; gap: 3px; padding: 8px 9px; border: 1px solid var(--iap-line-2); border-radius: 3px; background: #080d11; color: var(--iap-dim); text-align: left; cursor: pointer; }
      .tile:hover { border-color: #3b4d5a; }
      .tile.editing { outline: 2px solid var(--iap-text); outline-offset: 1px; }
      .tile .t { font-size: 11px; color: var(--iap-faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .tile .n { font-size: 11.5px; line-height: 1.25; letter-spacing: .05em; text-transform: uppercase; overflow-wrap: anywhere; }
      .tile .c { font: 10.5px var(--iap-mono); color: var(--iap-faint); }
      .tile.lit { color: #0a0a0a; border-color: transparent; }
      .tile.lit .t, .tile.lit .c { color: inherit; opacity: .72; }
      .tile.p-critical { --lit: var(--iap-crit); } .tile.p-high { --lit: var(--iap-high); } .tile.p-medium { --lit: var(--iap-med); } .tile.p-low { --lit: var(--iap-low); } .tile.p-info, .tile.p-status { --lit: var(--iap-info); }
      .tile.lit.p-critical { background: var(--iap-crit); }
      .tile.lit.p-high { background: var(--iap-high); }
      .tile.lit.p-medium { background: var(--iap-med); }
      .tile.lit.p-low { background: var(--iap-low); }
      .tile.lit.p-info, .tile.lit.p-status { background: var(--iap-info); }
      .tile.lit.unack { animation: iap-unlit var(--iap-flash) steps(1, end) infinite; }
      .tile.cleared-unack { border-color: var(--lit); color: var(--iap-text); }
      .tile.shelved .n { text-decoration: line-through; }
      .tile.disabled { border-style: dashed; opacity: .6; }
      .rule-form { display: grid; gap: 10px; padding: 14px 16px 0; }
      .rule-form .actions { margin: 4px -16px 0; }
      .f { display: grid; gap: 4px; font-size: 11px; letter-spacing: .06em; color: var(--iap-dim); min-width: 0; }
      .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
      .three { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
      .checks { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; }
      .ck { display: flex; gap: 8px; align-items: center; font-size: 12.5px; min-height: 32px; cursor: pointer; }
      .ck input { width: 18px; height: 18px; accent-color: var(--iap-text); }
      .form-error { margin: 0; color: #ff8b84; font-size: 12.5px; }

      /* SYS */
      .sys { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; padding: 16px; }
      .sys section { border: 1px solid var(--iap-line); border-radius: 3px; padding: 14px; display: grid; gap: 10px; align-content: start; }
      .sys h3 { margin: 0; font-size: 11px; font-weight: 400; letter-spacing: .16em; color: var(--iap-dim); }
      .sys dl { margin: 0; display: grid; grid-template-columns: 1fr auto; gap: 8px 12px; align-items: center; font-size: 13px; }
      .sys dl.keys { grid-template-columns: auto 1fr; }
      .sys dd { margin: 0; text-align: right; }
      .sys dl.keys dd { text-align: left; color: var(--iap-dim); }
      .sys p { margin: 0; max-width: 60ch; font-size: 12.5px; color: var(--iap-dim); }
      kbd { font: 11px var(--iap-mono); border: 1px solid var(--iap-line-2); border-radius: 3px; padding: 1px 5px; }
      .key-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; font-size: 12.5px; }
      .key-list li { display: flex; gap: 10px; align-items: center; }

      /* Next decision (narrow) */
      .next:empty { display: none; }
      .next { padding: 16px 14px; background: var(--iap-panel-2); border-bottom: 1px solid var(--iap-line); }
      .next-label { display: flex; justify-content: space-between; font-size: 10.5px; letter-spacing: .16em; color: var(--iap-dim); }
      .next-id { display: flex; gap: 10px; align-items: center; margin-top: 10px; font-size: 12px; color: var(--iap-dim); }
      .next h2 { margin: 10px 0 2px; font-size: 22px; line-height: 1.15; letter-spacing: .04em; text-transform: uppercase; text-wrap: balance; }
      .next h2.calm { color: var(--iap-text); text-transform: none; letter-spacing: 0; font-size: 18px; }
      .next-value { font-weight: 700; font-size: 40px; line-height: 1.05; margin-top: 8px; }
      .next-value small { font-size: 16px; font-weight: 400; color: var(--iap-dim); margin-left: 4px; }
      .next-meta { font-size: 12px; color: var(--iap-dim); }
      .next-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }

      /* Toast and confirm */
      .toast { position: fixed; left: 50%; bottom: calc(16px + env(safe-area-inset-bottom, 0px)); transform: translateX(-50%); z-index: 20; max-width: min(560px, calc(100% - 32px)); padding: 10px 14px; border: 1px solid var(--iap-line-2); border-radius: 3px; background: #0d151b; font-size: 13px; box-shadow: 0 6px 24px rgba(0, 0, 0, .5); }
      .toast.bad { border-color: var(--iap-crit); color: #ffd9d6; }
      .confirm { border: 1px solid var(--iap-line-2); border-radius: 4px; background: var(--iap-panel-2); color: var(--iap-text); padding: 18px; max-width: 440px; }
      .confirm::backdrop { background: rgba(0, 0, 0, .6); }
      .confirm p { margin: 0 0 16px; line-height: 1.5; }
      .confirm-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }

      /* Narrow (phone): the single next decision */
      .narrow .master { grid-template-columns: auto 1fr 1fr; padding: 10px; }
      .narrow .menu { display: inline-flex; align-items: center; justify-content: center; }
      .narrow .key-ack { display: none; }
      .narrow .horn { order: 4; }
      .narrow .legend { order: 5; grid-column: 1 / -1; padding: 2px 2px 0; gap: 4px 14px; }
      .narrow .key { min-width: 0; }
      .narrow .horn { grid-column: 1 / -1; grid-template-columns: 1fr auto; grid-template-rows: none; min-width: 0; }
      .narrow .horn-state { border-bottom: 0; border-right: 1px solid var(--iap-line); }
      .narrow .split, .narrow .rules-split.with-editor { grid-template-columns: minmax(0, 1fr); }
      .narrow .stack, .narrow .rules-main { border-right: 0; }
      .narrow .stack-head { display: none; }
      .narrow .row { grid-template-columns: 24px minmax(0, 1fr) auto; gap: 10px; padding: 8px 12px; min-height: 56px; }
      .narrow .row .time, .narrow .row .tag, .narrow .row .state { display: none; }
      .narrow .row.unack .state { display: block; grid-column: 2 / -1; text-align: left; margin-top: -4px; }
      .narrow .status:not(.editor):not(.inline) { display: none; }
      .narrow .pages { flex-wrap: wrap; overflow: visible; padding: 0 6px; }
      .narrow .pages button { padding: 12px 10px 10px; }
      .narrow .editor.open { position: fixed; inset: 0; z-index: 10; overflow-y: auto; }
      .narrow .filters .chip[data-action="toggle-density"] { display: none; }
      .narrow .three { grid-template-columns: 1fr; }

      .narrow .shelve button, .narrow .chip, .narrow .field, .narrow .seg button, .narrow .ck { min-height: 44px; }
      .narrow .shelve button { min-width: 44px; }
      @media (pointer: coarse), (max-width: 1366px) {
        .shelve button, .chip, .field, .seg button, .ck, .horn button { min-height: 44px; }
        .shelve button { min-width: 44px; }
      }
      @media (max-width: 1100px) {
        .panel:not(.narrow) .stack-head, .panel:not(.narrow) .row { grid-template-columns: 26px 84px minmax(0, 1fr) 104px 96px; }
        .panel:not(.narrow) .c-tag { display: none; }
      }
      @media (max-width: 860px) {
        .panel:not(.narrow) .master { grid-template-columns: 1fr 1fr; }
        .panel:not(.narrow) .legend { grid-column: 1 / -1; order: 5; }
        .panel:not(.narrow) .horn { grid-column: 1 / -1; }
        .panel:not(.narrow) .split, .panel:not(.narrow) .rules-split.with-editor { grid-template-columns: minmax(0, 1fr); }
        .panel:not(.narrow) .stack, .panel:not(.narrow) .rules-main { border-right: 0; }
        .panel:not(.narrow) .key-ack { grid-column: 1 / -1; min-height: 52px; }
        .panel:not(.narrow) .stack-head { display: none; }
        .panel:not(.narrow) .row { grid-template-columns: 24px minmax(0, 1fr) auto; gap: 10px; padding: 8px 12px; min-height: 56px; }
        .panel:not(.narrow) .row .time, .panel:not(.narrow) .row .tag, .panel:not(.narrow) .row .state { display: none; }
        .three { grid-template-columns: 1fr; }
      }
      .no-flash .key.flash .face, .no-flash .tile.lit.unack, .no-flash .horn.on .horn-state i, .no-flash .row.unack .g .shape, .no-flash .row.unack .g .num { animation: none; }
      .no-flash .row.unack .g { outline: 2px solid var(--gc); outline-offset: 2px; }
      @media (prefers-reduced-motion: reduce) {
        .key.flash .face, .tile.lit.unack, .horn.on .horn-state i, .row.unack .g .shape, .row.unack .g .num, .status.inline.unfolding { animation: none; }
        .row.unack .g { outline: 2px solid var(--gc); outline-offset: 2px; }
        .key.flash .face { outline: 3px solid #fff; outline-offset: -6px; }
        .switch span { transition: none; }
      }
    `;
  }
}

if (!customElements.get("industrial-alarm-panel")) {
  customElements.define("industrial-alarm-panel", IndustrialAlarmPanel);
}
