class IndustrialAlarmPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._alarms = [];
    this._history = [];
    this._rules = [];
    this._sound = {};
    this._tab = "active";
    this._search = "";
    this._priority = "all";
    this._audioEnabled = false;
    this._refreshing = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) {
      this._render();
      this._load();
      this._timer = window.setInterval(() => this._load(), 5000);
    }
    if (this._sound && this._sound.horn_active) {
      this._playBrowserHorn();
    }
  }

  set narrow(value) {
    this._narrow = value;
    this._render();
  }

  disconnectedCallback() {
    if (this._timer) {
      window.clearInterval(this._timer);
    }
  }

  async _callWS(payload) {
    if (!this._hass) return null;
    return this._hass.callWS(payload);
  }

  async _load() {
    if (this._refreshing || !this._hass) return;
    this._refreshing = true;
    try {
      const alarms = await this._callWS({ type: "industrial_alarm_panel/list_alarms" });
      const history = await this._callWS({ type: "industrial_alarm_panel/list_history", limit: 250 });
      const rules = await this._callWS({ type: "industrial_alarm_panel/list_rules" });
      this._alarms = alarms?.alarms || [];
      this._sound = alarms?.sound || {};
      this._history = history?.events || [];
      this._rules = rules?.rules || [];
      this._render();
    } catch (err) {
      this._error = err.message || String(err);
      this._render();
    } finally {
      this._refreshing = false;
    }
  }

  async _ack(ruleId) {
    await this._callWS({ type: "industrial_alarm_panel/acknowledge", rule_id: ruleId });
    await this._load();
  }

  async _ackAll() {
    await this._callWS({ type: "industrial_alarm_panel/acknowledge_all" });
    await this._load();
  }

  async _silence() {
    await this._callWS({ type: "industrial_alarm_panel/silence" });
    this._stopBrowserHorn();
    await this._load();
  }

  async _shelve(ruleId) {
    await this._callWS({
      type: "industrial_alarm_panel/shelve",
      rule_id: ruleId,
      duration_minutes: 60,
    });
    await this._load();
  }

  async _testSound() {
    this._audioEnabled = true;
    await this._callWS({ type: "industrial_alarm_panel/test_sound", priority: "critical" });
    await this._playBrowserHorn(true);
  }

  async _playBrowserHorn(once = false) {
    if (!this._audioEnabled && !once) return;
    try {
      const context = this._audioContext || new AudioContext();
      this._audioContext = context;
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = "square";
      oscillator.frequency.setValueAtTime(880, context.currentTime);
      gain.gain.setValueAtTime(0.0001, context.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.22, context.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.35);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start();
      oscillator.stop(context.currentTime + 0.38);
    } catch (err) {
      this._audioEnabled = false;
    }
  }

  _stopBrowserHorn() {
    this._sound = { ...this._sound, horn_active: false };
  }

  _filteredAlarms() {
    const search = this._search.trim().toLowerCase();
    return this._alarms
      .filter((alarm) => {
        if (this._tab === "active" && !["ACTIVE_UNACK", "ACTIVE_ACK", "CLEARED_UNACK"].includes(alarm.lifecycle_state)) return false;
        if (this._tab === "unacknowledged" && !["ACTIVE_UNACK", "CLEARED_UNACK"].includes(alarm.lifecycle_state)) return false;
        if (this._tab === "shelved" && alarm.lifecycle_state !== "SHELVED") return false;
        if (this._tab === "disabled" && alarm.lifecycle_state !== "DISABLED") return false;
        if (this._priority !== "all" && alarm.priority !== this._priority) return false;
        if (!search) return true;
        return [alarm.tag, alarm.name, alarm.entity_id, alarm.area, alarm.system]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(search);
      })
      .sort((a, b) => (b.severity - a.severity) || String(a.active_since || "").localeCompare(String(b.active_since || "")));
  }

  _render() {
    if (!this.shadowRoot) return;
    const visible = this._filteredAlarms();
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <main class="panel">
        <header class="topbar">
          <div>
            <h1>Industrial Alarms</h1>
            <div class="metrics">
              <span>${this._alarms.filter((a) => ["ACTIVE_UNACK", "ACTIVE_ACK"].includes(a.lifecycle_state)).length} active</span>
              <span>${this._alarms.filter((a) => ["ACTIVE_UNACK", "CLEARED_UNACK"].includes(a.lifecycle_state)).length} unack</span>
              <span class="${this._sound.horn_active ? "horn on" : "horn"}">${this._sound.horn_active ? "Horn active" : "Horn idle"}</span>
            </div>
          </div>
          <div class="actions">
            ${!this._audioEnabled ? `<button class="secondary" data-action="enable-audio">Enable Alarm Sound</button>` : ""}
            <button class="danger" data-action="silence">Silence</button>
            <button class="primary" data-action="ack-all">Ack All</button>
          </div>
        </header>
        <nav class="tabs">${this._tabs()}</nav>
        ${this._error ? `<div class="error">${this._escape(this._error)}</div>` : ""}
        ${this._tab === "history" ? this._historyView() : ""}
        ${this._tab === "rules" ? this._rulesView() : ""}
        ${this._tab === "settings" ? this._settingsView() : ""}
        ${["active", "unacknowledged", "shelved", "disabled"].includes(this._tab) ? this._alarmView(visible) : ""}
      </main>
    `;
    this._wire();
    this._rendered = true;
  }

  _tabs() {
    const tabs = [
      ["active", "Active Alarms"],
      ["unacknowledged", "Unacknowledged"],
      ["history", "History"],
      ["shelved", "Shelved"],
      ["disabled", "Disabled"],
      ["rules", "Rules"],
      ["settings", "Settings"],
    ];
    return tabs.map(([id, label]) => `<button class="${this._tab === id ? "selected" : ""}" data-tab="${id}">${label}</button>`).join("");
  }

  _alarmView(alarms) {
    return `
      <section class="toolbar">
        <input type="search" placeholder="Search tag, alarm, entity, area" value="${this._escape(this._search)}" data-field="search">
        <select data-field="priority">
          ${["all", "critical", "high", "medium", "low", "info", "status"].map((priority) => `<option value="${priority}" ${this._priority === priority ? "selected" : ""}>${priority}</option>`).join("")}
        </select>
        <button data-action="refresh">Refresh</button>
      </section>
      <section class="table-shell">
        <table>
          <thead>
            <tr>
              <th>Time</th><th>Priority</th><th>Area</th><th>System</th><th>Tag</th><th>Alarm</th><th>Source Value</th><th>State</th><th>Ack</th><th>Shelve</th><th>Instructions</th>
            </tr>
          </thead>
          <tbody>
            ${alarms.length ? alarms.map((alarm) => this._alarmRow(alarm)).join("") : `<tr><td colspan="11" class="empty">No alarms in this view</td></tr>`}
          </tbody>
        </table>
      </section>
    `;
  }

  _alarmRow(alarm) {
    const flash = alarm.lifecycle_state === "ACTIVE_UNACK" || alarm.lifecycle_state === "CLEARED_UNACK";
    return `
      <tr class="priority-${alarm.priority} ${flash ? "flash" : ""}">
        <td>${this._time(alarm.active_since || alarm.cleared_at)}</td>
        <td><span class="badge">${alarm.priority}</span></td>
        <td>${this._escape(alarm.area || "")}</td>
        <td>${this._escape(alarm.system || "")}</td>
        <td>${this._escape(alarm.tag || alarm.id)}</td>
        <td>${this._escape(alarm.name)}</td>
        <td>${this._escape(String(alarm.last_value ?? alarm.last_source_state ?? ""))}</td>
        <td>${this._escape(alarm.lifecycle_state)}</td>
        <td><button data-ack="${this._escape(alarm.id)}" ${alarm.acknowledged ? "disabled" : ""}>Ack</button></td>
        <td><button data-shelve="${this._escape(alarm.id)}" ${alarm.shelved || alarm.disabled ? "disabled" : ""}>Shelve</button></td>
        <td>${this._escape(alarm.instructions || "")}</td>
      </tr>
    `;
  }

  _historyView() {
    return `
      <section class="table-shell">
        <table>
          <thead><tr><th>Time</th><th>Event</th><th>Priority</th><th>Area</th><th>Tag</th><th>Alarm</th><th>From</th><th>To</th><th>Operator</th></tr></thead>
          <tbody>
            ${this._history.length ? this._history.map((event) => `
              <tr>
                <td>${this._time(event.timestamp)}</td>
                <td>${this._escape(event.event_type)}</td>
                <td>${this._escape(event.priority || "")}</td>
                <td>${this._escape(event.area || "")}</td>
                <td>${this._escape(event.tag || event.rule_id || "")}</td>
                <td>${this._escape(event.name || event.message || "")}</td>
                <td>${this._escape(event.previous_state || "")}</td>
                <td>${this._escape(event.new_state || "")}</td>
                <td>${this._escape(event.operator || "")}</td>
              </tr>`).join("") : `<tr><td colspan="9" class="empty">No history rows</td></tr>`}
          </tbody>
        </table>
      </section>
    `;
  }

  _rulesView() {
    return `
      <section class="rules">
        <div class="rule-form">
          <input placeholder="Rule id" data-new="id">
          <input placeholder="Entity id" data-new="entity_id">
          <input placeholder="Name" data-new="name">
          <select data-new="condition">
            ${["above", "below", "equal", "not_equal", "contains", "is_on", "is_off", "state_changed", "unavailable", "unavailable_for", "unknown_for", "manual"].map((c) => `<option>${c}</option>`).join("")}
          </select>
          <input placeholder="Threshold" data-new="threshold">
          <select data-new="priority">
            ${["critical", "high", "medium", "low", "info", "status"].map((p) => `<option>${p}</option>`).join("")}
          </select>
          <button class="primary" data-action="create-rule">Add Rule</button>
        </div>
        <div class="table-shell">
          <table>
            <thead><tr><th>ID</th><th>Entity</th><th>Name</th><th>Condition</th><th>Priority</th><th>Enabled</th></tr></thead>
            <tbody>${this._rules.map((rule) => `<tr><td>${this._escape(rule.id)}</td><td>${this._escape(rule.entity_id)}</td><td>${this._escape(rule.name)}</td><td>${this._escape(rule.condition)}</td><td>${this._escape(rule.priority)}</td><td>${rule.enabled ? "yes" : "no"}</td></tr>`).join("")}</tbody>
          </table>
        </div>
      </section>
    `;
  }

  _settingsView() {
    return `
      <section class="settings">
        <dl>
          <dt>Sound mode</dt><dd>${this._escape(this._sound.sound_mode || "browser_only")}</dd>
          <dt>Browser sound</dt><dd>${this._sound.browser_enabled ? "enabled" : "disabled"}</dd>
          <dt>Media player sound</dt><dd>${this._sound.media_player_enabled ? "enabled" : "disabled"}</dd>
          <dt>Active audible alarms</dt><dd>${(this._sound.active_audible_alarms || []).length}</dd>
        </dl>
        <button data-action="test-sound">Test Sound</button>
      </section>
    `;
  }

  _wire() {
    this.shadowRoot.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        this._tab = button.dataset.tab;
        this._render();
      });
    });
    this.shadowRoot.querySelector("[data-action='ack-all']")?.addEventListener("click", () => this._ackAll());
    this.shadowRoot.querySelector("[data-action='silence']")?.addEventListener("click", () => this._silence());
    this.shadowRoot.querySelector("[data-action='refresh']")?.addEventListener("click", () => this._load());
    this.shadowRoot.querySelector("[data-action='enable-audio']")?.addEventListener("click", () => this._testSound());
    this.shadowRoot.querySelector("[data-action='test-sound']")?.addEventListener("click", () => this._testSound());
    this.shadowRoot.querySelector("[data-action='create-rule']")?.addEventListener("click", () => this._createRule());
    this.shadowRoot.querySelector("[data-field='search']")?.addEventListener("input", (event) => {
      this._search = event.target.value;
      this._render();
    });
    this.shadowRoot.querySelector("[data-field='priority']")?.addEventListener("change", (event) => {
      this._priority = event.target.value;
      this._render();
    });
    this.shadowRoot.querySelectorAll("[data-ack]").forEach((button) => button.addEventListener("click", () => this._ack(button.dataset.ack)));
    this.shadowRoot.querySelectorAll("[data-shelve]").forEach((button) => button.addEventListener("click", () => this._shelve(button.dataset.shelve)));
  }

  async _createRule() {
    const fields = {};
    this.shadowRoot.querySelectorAll("[data-new]").forEach((field) => {
      if (field.value !== "") fields[field.dataset.new] = field.value;
    });
    if (fields.threshold !== undefined && fields.threshold !== "") fields.threshold = Number(fields.threshold);
    await this._callWS({ type: "industrial_alarm_panel/create_rule", rule: fields });
    await this._load();
  }

  _time(value) {
    if (!value) return "";
    try {
      return new Date(value).toLocaleString();
    } catch (_err) {
      return value;
    }
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    })[char]);
  }

  _styles() {
    return `
      :host { display: block; color: #e6edf3; background: #101316; min-height: 100vh; font-family: Arial, sans-serif; }
      .panel { min-height: 100vh; }
      .topbar { display: flex; justify-content: space-between; gap: 16px; align-items: center; padding: 14px 18px; background: #181d22; border-bottom: 1px solid #303942; }
      h1 { margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0; }
      .metrics { display: flex; gap: 10px; margin-top: 6px; color: #9fb1c1; font-size: 13px; }
      .horn.on { color: #ffcf33; font-weight: 700; }
      .actions, .toolbar, .tabs, .rule-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
      button, select, input { background: #202832; color: #e6edf3; border: 1px solid #3d4a57; min-height: 34px; border-radius: 4px; padding: 0 10px; font-size: 14px; }
      input { min-width: 260px; }
      button { cursor: pointer; }
      button:hover { background: #2a3541; }
      button:disabled { opacity: .45; cursor: default; }
      .primary { background: #2563eb; border-color: #3473ff; }
      .danger { background: #9f1d1d; border-color: #d23b3b; }
      .secondary { background: #30515d; border-color: #4b7b8c; }
      .tabs { padding: 10px 18px; background: #14191f; border-bottom: 1px solid #26313b; }
      .tabs button.selected { background: #d9e2ec; color: #101316; border-color: #d9e2ec; }
      .toolbar { padding: 12px 18px; }
      .table-shell { overflow: auto; padding: 0 18px 18px; }
      table { width: 100%; border-collapse: collapse; background: #11161b; table-layout: auto; }
      th, td { border-bottom: 1px solid #28323c; padding: 8px 9px; text-align: left; font-size: 13px; white-space: nowrap; }
      th { background: #202832; color: #b8c7d4; position: sticky; top: 0; z-index: 1; }
      td:nth-child(6), td:nth-child(11) { white-space: normal; min-width: 180px; }
      tr { border-left: 6px solid #4b5563; }
      .priority-critical { border-left-color: #e31b23; }
      .priority-high { border-left-color: #ff8c00; }
      .priority-medium { border-left-color: #ffd400; }
      .priority-low { border-left-color: #3f8cff; }
      .priority-info { border-left-color: #8aa4b2; }
      .priority-status { border-left-color: #54c6d6; }
      .badge { text-transform: uppercase; font-size: 12px; font-weight: 700; }
      .flash { animation: flashRow 1s step-end infinite; }
      @keyframes flashRow { 50% { background: rgba(255,255,255,.16); } }
      .empty, .error { color: #9fb1c1; padding: 18px; }
      .error { margin: 12px 18px; color: #ffd5d5; background: #5b1c1c; border: 1px solid #a83737; }
      .rules, .settings { padding: 12px 18px 18px; }
      .rule-form { margin-bottom: 12px; }
      .settings dl { display: grid; grid-template-columns: max-content minmax(120px, 1fr); gap: 10px 18px; max-width: 560px; }
      .settings dt { color: #9fb1c1; }
      .settings dd { margin: 0; }
      @media (max-width: 720px) {
        .topbar { align-items: flex-start; flex-direction: column; }
        input { min-width: 0; width: 100%; }
        .actions, .toolbar, .rule-form { width: 100%; }
        button, select { flex: 1 1 auto; }
      }
    `;
  }
}

customElements.define("industrial-alarm-panel", IndustrialAlarmPanel);
