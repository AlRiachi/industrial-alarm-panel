const ALARMS_UPDATED_EVENT = "industrial_alarm_panel_alarms_updated";

class IndustrialAlarmPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._alarms = [];
    this._history = [];
    this._rules = [];
    this._ruleDraft = {
      id: "",
      entity_id: "",
      name: "",
      condition: "above",
      threshold: "",
      priority: "medium",
    };
    this._suggestionDraft = {
      power_threshold_w: 2000,
      low_voltage_v: 207,
      high_voltage_v: 253,
      high_solar_water_temp_c: 75,
    };
    this._suggestedRules = [];
    this._selectedSuggestedRuleIds = new Set();
    this._selectedRuleIds = new Set();
    this._rulesResult = null;
    this._suggestedRulesResult = null;
    this._sound = {};
    this._tab = "active";
    this._search = "";
    this._priority = "all";
    this._audioEnabled = false;
    this._refreshing = false;
    this._updatesSubscribed = false;
    this._unsubscribeUpdates = undefined;
    this._columnWidths = {};
    this._tableScrollLeft = {};
    this._alarmVisualDelayMs = 2000;
    this._alarmFirstSeenAt = {};
    this._alarmVisualRefreshTimer = undefined;
    this._browserHornCooldownMs = 2000;
    this._lastBrowserHornAt = 0;
  }

  set hass(hass) {
    this._hass = hass;
    this._subscribeUpdates();
    if (!this._rendered) {
      this._render();
      this._load();
      this._timer = window.setInterval(() => this._load(), 5000);
    }
    this._maybePlayBrowserHorn();
  }

  set narrow(value) {
    this._narrow = value;
    this._render();
  }

  set panel(panel) {
    this._panel = panel;
  }

  disconnectedCallback() {
    if (this._timer) {
      window.clearInterval(this._timer);
    }
    if (this._alarmVisualRefreshTimer) {
      window.clearTimeout(this._alarmVisualRefreshTimer);
      this._alarmVisualRefreshTimer = undefined;
    }
    if (this._unsubscribeUpdates) {
      Promise.resolve(this._unsubscribeUpdates)
        .then((unsubscribe) => {
          if (typeof unsubscribe === "function") unsubscribe();
        })
        .catch(() => undefined);
      this._unsubscribeUpdates = undefined;
      this._updatesSubscribed = false;
    }
  }

  async _callWS(payload) {
    if (!this._hass) return null;
    return this._hass.callWS(payload);
  }

  _subscribeUpdates() {
    const connection = this._hass?.connection;
    if (this._updatesSubscribed || !connection?.subscribeEvents) return;
    this._updatesSubscribed = true;
    try {
      this._unsubscribeUpdates = connection.subscribeEvents(
        (event) => this._handleAlarmUpdateEvent(event),
        ALARMS_UPDATED_EVENT
      );
    } catch (_err) {
      this._updatesSubscribed = false;
      this._unsubscribeUpdates = undefined;
    }
  }

  _handleAlarmUpdateEvent(event) {
    const entryId = this._panel?.config?.entry_id;
    if (entryId && event?.data?.entry_id && event.data.entry_id !== entryId) return;
    this._load();
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
      const ruleIds = new Set(this._rules.map((rule) => rule.id));
      this._selectedRuleIds = new Set([...this._selectedRuleIds].filter((id) => ruleIds.has(id)));
      this._suggestedRules = this._suggestedRules.filter((rule) => !ruleIds.has(rule.id));
      const suggestedRuleIds = new Set(this._suggestedRules.map((rule) => rule.id));
      this._selectedSuggestedRuleIds = new Set([...this._selectedSuggestedRuleIds].filter((id) => suggestedRuleIds.has(id)));
      this._maybePlayBrowserHorn();
      if (!this._isEditingRulesForm()) this._render();
    } catch (err) {
      this._error = err.message || String(err);
      if (!this._isEditingRulesForm()) this._render();
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

  _maybePlayBrowserHorn() {
    if (!this._sound?.horn_active || !this._audioEnabled) return;
    const now = Date.now();
    if (now - this._lastBrowserHornAt < this._browserHornCooldownMs) return;
    this._lastBrowserHornAt = now;
    this._playBrowserHorn();
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
    this._captureTableScroll();
    const visible = this._filteredAlarms();
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <main class="panel">
        <header class="topbar">
          ${this._narrow ? `<button class="secondary menu-button" data-action="toggle-menu" aria-label="Open sidebar">Menu</button>` : ""}
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
    this._restoreTableScroll();
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
        <table data-table-id="alarms">
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
    const stateClass = this._alarmStateClass(alarm);
    const flash = stateClass !== "state-pending-color" && (alarm.lifecycle_state === "ACTIVE_UNACK" || alarm.lifecycle_state === "CLEARED_UNACK");
    return `
      <tr class="alarm-row priority-${alarm.priority} ${stateClass} ${flash ? "flash" : ""}">
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
        <table data-table-id="history">
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
    const ruleDraft = this._ruleDraft;
    const suggestionDraft = this._suggestionDraft;
    const selectedSuggestedCount = this._selectedSuggestedRuleIds.size;
    const selectedRuleCount = this._selectedRuleIds.size;
    const autoGeneratedCount = this._rules.filter((rule) => String(rule.id || "").startsWith("auto_")).length;
    return `
      <section class="rules">
        <div class="suggested-rules">
          <h2>Suggested Rules</h2>
          <div class="suggested-rules-controls">
            <label>High W <input type="number" min="1" step="50" value="${this._escape(suggestionDraft.power_threshold_w)}" data-suggest="power_threshold_w"></label>
            <label>Low V <input type="number" min="1" step="1" value="${this._escape(suggestionDraft.low_voltage_v)}" data-suggest="low_voltage_v"></label>
            <label>High V <input type="number" min="1" step="1" value="${this._escape(suggestionDraft.high_voltage_v)}" data-suggest="high_voltage_v"></label>
            <label>Solar C <input type="number" min="1" step="1" value="${this._escape(suggestionDraft.high_solar_water_temp_c)}" data-suggest="high_solar_water_temp_c"></label>
            <button class="secondary" data-action="preview-suggested-rules">Preview Suggested Rules</button>
            <button class="secondary" data-action="select-all-suggested-rules" ${this._suggestedRules.length && selectedSuggestedCount !== this._suggestedRules.length ? "" : "disabled"}>Select All</button>
            <button class="secondary" data-action="deselect-all-suggested-rules" ${selectedSuggestedCount ? "" : "disabled"}>Deselect All</button>
            <button class="primary" data-action="create-selected-suggested-rules" ${selectedSuggestedCount ? "" : "disabled"}>Create Selected</button>
            <button class="primary" data-action="create-all-suggested-rules" ${this._suggestedRules.length ? "" : "disabled"}>Create All</button>
            <button class="danger" data-action="remove-auto-generated-rules" ${autoGeneratedCount ? "" : "disabled"}>Remove Auto-Generated Rules</button>
          </div>
          <div class="bulk-summary">
            <span>${this._suggestedRules.length} suggested</span>
            <span>${selectedSuggestedCount} selected</span>
            <span>${selectedSuggestedCount * 4} estimated entities</span>
            <span>${this._suggestedRules.length * 4} generated estimated entities</span>
          </div>
          ${this._suggestedRulesResult ? `<div class="notice">${this._escape(this._suggestedRulesResult)}</div>` : ""}
          ${this._suggestedRules.length ? `
            <div class="table-shell suggested-preview">
              <table data-table-id="suggested-rules">
                <thead><tr><th></th><th>ID</th><th>Entity</th><th>Name</th><th>Condition</th><th>Threshold</th><th>Priority</th></tr></thead>
                <tbody>${this._suggestedRules.map((rule) => `
                  <tr>
                    <td><input class="row-select" type="checkbox" data-suggested-select="${this._escape(rule.id)}" ${this._selectedSuggestedRuleIds.has(rule.id) ? "checked" : ""}></td>
                    <td>${this._escape(rule.id)}</td>
                    <td>${this._escape(rule.entity_id)}</td>
                    <td>${this._escape(rule.name)}</td>
                    <td>${this._escape(rule.condition)}</td>
                    <td>${this._escape(rule.threshold ?? "")}</td>
                    <td>${this._escape(rule.priority)}</td>
                  </tr>`).join("")}</tbody>
              </table>
            </div>
          ` : ""}
        </div>
        <div class="rule-form">
          <input placeholder="Rule id" value="${this._escape(ruleDraft.id)}" data-new="id">
          <input placeholder="Entity id" value="${this._escape(ruleDraft.entity_id)}" data-new="entity_id">
          <input placeholder="Name" value="${this._escape(ruleDraft.name)}" data-new="name">
          <select data-new="condition">
            ${["above", "below", "equal", "not_equal", "contains", "is_on", "is_off", "state_changed", "unavailable", "unavailable_for", "unknown_for", "manual"].map((c) => `<option value="${c}" ${ruleDraft.condition === c ? "selected" : ""}>${c}</option>`).join("")}
          </select>
          <input placeholder="Threshold" value="${this._escape(ruleDraft.threshold)}" data-new="threshold">
          <select data-new="priority">
            ${["critical", "high", "medium", "low", "info", "status"].map((p) => `<option value="${p}" ${ruleDraft.priority === p ? "selected" : ""}>${p}</option>`).join("")}
          </select>
          <button class="primary" data-action="create-rule">Add Rule</button>
        </div>
        ${this._rulesResult ? `<div class="notice">${this._escape(this._rulesResult)}</div>` : ""}
        <div class="bulk-actions">
          <span>${this._rules.length} rules</span>
          <span>${selectedRuleCount} selected</span>
          <span>${autoGeneratedCount} auto-generated</span>
          <span>${selectedRuleCount * 4} estimated entities</span>
          <span>${autoGeneratedCount * 4} auto-generated estimated entities</span>
          <button class="danger" data-action="delete-selected-rules" ${selectedRuleCount ? "" : "disabled"}>Delete Selected</button>
        </div>
        <div class="table-shell">
          <table data-table-id="rules">
            <thead><tr><th></th><th>ID</th><th>Entity</th><th>Name</th><th>Condition</th><th>Priority</th><th>Enabled</th></tr></thead>
            <tbody>${this._rules.length ? this._rules.map((rule) => `<tr><td><input class="row-select" type="checkbox" data-rule-select="${this._escape(rule.id)}" ${this._selectedRuleIds.has(rule.id) ? "checked" : ""}></td><td>${this._escape(rule.id)}</td><td>${this._escape(rule.entity_id)}</td><td>${this._escape(rule.name)}</td><td>${this._escape(rule.condition)}</td><td>${this._escape(rule.priority)}</td><td>${rule.enabled ? "yes" : "no"}</td></tr>`).join("") : `<tr><td colspan="7" class="empty">No rules configured</td></tr>`}</tbody>
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
    this.shadowRoot.querySelector("[data-action='toggle-menu']")?.addEventListener("click", () => this._toggleSidebar());
    this.shadowRoot.querySelector("[data-action='enable-audio']")?.addEventListener("click", () => this._testSound());
    this.shadowRoot.querySelector("[data-action='test-sound']")?.addEventListener("click", () => this._testSound());
    this.shadowRoot.querySelector("[data-action='create-rule']")?.addEventListener("click", () => this._createRule());
    this.shadowRoot.querySelector("[data-action='preview-suggested-rules']")?.addEventListener("click", () => this._previewSuggestedRules());
    this.shadowRoot.querySelector("[data-action='select-all-suggested-rules']")?.addEventListener("click", () => this._selectAllSuggestedRules());
    this.shadowRoot.querySelector("[data-action='deselect-all-suggested-rules']")?.addEventListener("click", () => this._deselectAllSuggestedRules());
    this.shadowRoot.querySelector("[data-action='create-selected-suggested-rules']")?.addEventListener("click", () => this._createSelectedSuggestedRules());
    this.shadowRoot.querySelector("[data-action='create-all-suggested-rules']")?.addEventListener("click", () => this._createAllSuggestedRules());
    this.shadowRoot.querySelector("[data-action='delete-selected-rules']")?.addEventListener("click", () => this._deleteSelectedRules());
    this.shadowRoot.querySelector("[data-action='remove-auto-generated-rules']")?.addEventListener("click", () => this._removeAutoGeneratedRules());
    this.shadowRoot.querySelectorAll("[data-new]").forEach((field) => {
      const updateDraft = () => {
        this._ruleDraft[field.dataset.new] = field.value;
      };
      field.addEventListener("input", updateDraft);
      field.addEventListener("change", updateDraft);
    });
    this.shadowRoot.querySelectorAll("[data-suggest]").forEach((field) => {
      const updateDraft = () => {
        this._suggestionDraft[field.dataset.suggest] = field.value;
        this._clearSuggestedPreview();
      };
      field.addEventListener("input", updateDraft);
      field.addEventListener("change", updateDraft);
    });
    this.shadowRoot.querySelectorAll("[data-suggested-select]").forEach((field) => {
      field.addEventListener("change", () => {
        this._setMembership(this._selectedSuggestedRuleIds, field.dataset.suggestedSelect, field.checked);
        this._render();
      });
    });
    this.shadowRoot.querySelectorAll("[data-rule-select]").forEach((field) => {
      field.addEventListener("change", () => {
        this._setMembership(this._selectedRuleIds, field.dataset.ruleSelect, field.checked);
        this._render();
      });
    });
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
    this._wireColumnResizers();
  }

  async _createRule() {
    const fields = { ...this._ruleDraft };
    Object.keys(fields).forEach((key) => {
      if (fields[key] === "") delete fields[key];
    });
    if (fields.threshold !== undefined && fields.threshold !== "") fields.threshold = Number(fields.threshold);
    await this._callWS({ type: "industrial_alarm_panel/create_rule", rule: fields });
    this._ruleDraft = {
      id: "",
      entity_id: "",
      name: "",
      condition: "above",
      threshold: "",
      priority: "medium",
    };
    await this._load();
  }

  _toggleSidebar() {
    this.dispatchEvent(new CustomEvent("hass-toggle-menu", {
      detail: { open: true },
      bubbles: true,
      composed: true,
    }));
  }

  async _previewSuggestedRules() {
    try {
      const result = await this._callWS({
        type: "industrial_alarm_panel/list_suggested_rules",
        ...this._suggestionPayload(),
      });
      this._suggestedRules = result?.suggested || [];
      this._selectedSuggestedRuleIds = new Set(this._suggestedRules.map((rule) => rule.id));
      this._suggestedRulesResult = this._suggestedRules.length
        ? `Previewing ${this._suggestedRules.length} suggested rules, ${this._suggestedRules.length * 4} estimated entities`
        : "No suggested rules found";
    } catch (err) {
      this._suggestedRulesResult = err.message || String(err);
    }
    this._render();
  }

  async _createSelectedSuggestedRules() {
    await this._createSuggestedRules([...this._selectedSuggestedRuleIds]);
  }

  async _createAllSuggestedRules() {
    await this._createSuggestedRules(this._suggestedRules.map((rule) => rule.id));
  }

  _selectAllSuggestedRules() {
    this._selectedSuggestedRuleIds = new Set(this._suggestedRules.map((rule) => rule.id));
    this._render();
  }

  _deselectAllSuggestedRules() {
    this._selectedSuggestedRuleIds = new Set();
    this._render();
  }

  async _createSuggestedRules(ruleIds) {
    const count = ruleIds.length;
    if (!count) {
      this._suggestedRulesResult = "Select suggested rules before creating them";
      this._render();
      return;
    }
    const estimatedEntities = count * 4;
    if (!window.confirm(`Create ${count} suggested rules and about ${estimatedEntities} entities?`)) return;
    try {
      const result = await this._callWS({
        type: "industrial_alarm_panel/create_suggested_rules",
        ...this._suggestionPayload(),
        rule_ids: ruleIds,
      });
      const createdCount = result?.created_count || 0;
      const skippedCount = result?.skipped_rule_ids?.length || 0;
      this._suggestedRulesResult = createdCount
        ? `Created ${createdCount} suggested rules, ${createdCount * 4} estimated entities${skippedCount ? `, skipped ${skippedCount}` : ""}`
        : "No new suggested alarm rules";
      this._selectedSuggestedRuleIds = new Set();
      await this._load();
    } catch (err) {
      this._suggestedRulesResult = err.message || String(err);
      this._render();
    }
  }

  async _deleteSelectedRules() {
    const ruleIds = [...this._selectedRuleIds];
    await this._deleteRules({ rule_ids: ruleIds }, ruleIds.length, "selected rules");
  }

  async _removeAutoGeneratedRules() {
    const count = this._rules.filter((rule) => String(rule.id || "").startsWith("auto_")).length;
    await this._deleteRules({ generated_only: true }, count, "auto-generated rules");
  }

  async _deleteRules(payload, count, label) {
    if (!count) {
      this._rulesResult = `No ${label} to delete`;
      this._render();
      return;
    }
    const estimatedEntities = count * 4;
    if (!window.confirm(`Delete ${count} ${label} and about ${estimatedEntities} entities? Source entities will not be removed.`)) return;
    try {
      const result = await this._callWS({
        type: "industrial_alarm_panel/delete_rules",
        ...payload,
      });
      const deletedCount = result?.deleted_count || 0;
      const removedEntityCount = result?.removed_entity_count || 0;
      const skippedCount = result?.skipped_rule_ids?.length || 0;
      this._rulesResult = `Deleted ${deletedCount} rules and ${removedEntityCount} entities${skippedCount ? `, skipped ${skippedCount}` : ""}`;
      this._selectedRuleIds = new Set();
      await this._load();
    } catch (err) {
      this._rulesResult = err.message || String(err);
      this._render();
    }
  }

  _suggestionPayload() {
    const fields = {};
    Object.entries(this._suggestionDraft).forEach(([key, value]) => {
      if (value !== "") fields[key] = Number(value);
    });
    return fields;
  }

  _clearSuggestedPreview() {
    this._suggestedRules = [];
    this._selectedSuggestedRuleIds = new Set();
    this._suggestedRulesResult = "Preview suggested rules again after changing thresholds";
  }

  _setMembership(set, value, selected) {
    if (!value) return;
    if (selected) set.add(value);
    else set.delete(value);
  }

  _isEditingRulesForm() {
    const active = this.shadowRoot?.activeElement;
    if (this._tab !== "rules" || !active) return false;
    return Boolean(active.matches("[data-new], [data-suggest]"));
  }

  _alarmStateClass(alarm) {
    const lifecycle = String(alarm.lifecycle_state || "NORMAL");
    const stateClass = `state-${lifecycle.toLowerCase().replace(/_/g, "-")}`;
    if (!["ACTIVE_UNACK", "CLEARED_UNACK"].includes(lifecycle)) return stateClass;
    if (this._isAlarmVisualDelayElapsed(alarm, lifecycle)) return stateClass;
    this._scheduleAlarmVisualRefresh();
    return "state-pending-color";
  }

  _isAlarmVisualDelayElapsed(alarm, lifecycle) {
    const timestamp = Date.parse(alarm.active_since || alarm.cleared_at || "");
    if (!Number.isNaN(timestamp)) {
      return Date.now() - timestamp >= this._alarmVisualDelayMs;
    }
    const key = `${alarm.id || alarm.entity_id || alarm.name}:${lifecycle}`;
    this._alarmFirstSeenAt[key] = this._alarmFirstSeenAt[key] || Date.now();
    return Date.now() - this._alarmFirstSeenAt[key] >= this._alarmVisualDelayMs;
  }

  _scheduleAlarmVisualRefresh() {
    if (this._alarmVisualRefreshTimer) return;
    this._alarmVisualRefreshTimer = window.setTimeout(() => {
      this._alarmVisualRefreshTimer = undefined;
      if (!this._isEditingRulesForm()) this._render();
    }, this._alarmVisualDelayMs);
  }

  _captureTableScroll() {
    this.shadowRoot.querySelectorAll("table[data-table-id]").forEach((table) => {
      const shell = table.closest(".table-shell");
      if (shell) this._tableScrollLeft[table.dataset.tableId] = shell.scrollLeft;
    });
  }

  _restoreTableScroll() {
    const restore = () => {
      this.shadowRoot.querySelectorAll("table[data-table-id]").forEach((table) => {
        const shell = table.closest(".table-shell");
        const scrollLeft = this._tableScrollLeft[table.dataset.tableId];
        if (shell && scrollLeft !== undefined) shell.scrollLeft = scrollLeft;
      });
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(restore);
    else restore();
  }

  _wireColumnResizers() {
    this.shadowRoot.querySelectorAll("table").forEach((table, tableIndex) => {
      const tableId = table.dataset.tableId || `table-${tableIndex}`;
      const headers = Array.from(table.querySelectorAll("thead th"));
      if (!headers.length) return;
      let colgroup = table.querySelector("colgroup");
      if (!colgroup) {
        colgroup = document.createElement("colgroup");
        headers.forEach(() => colgroup.appendChild(document.createElement("col")));
        table.insertBefore(colgroup, table.firstElementChild);
      }
      const columns = Array.from(colgroup.children);
      const savedWidths = this._columnWidths[tableId] || {};
      headers.forEach((header, index) => {
        const savedWidth = savedWidths[index];
        if (savedWidth) {
          header.style.width = `${savedWidth}px`;
          if (columns[index]) columns[index].style.width = `${savedWidth}px`;
        }
        header.classList.add("resizable-column");
        if (header.querySelector(".col-resizer")) return;
        const handle = document.createElement("span");
        handle.className = "col-resizer";
        handle.addEventListener("pointerdown", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const startX = event.clientX;
          const startWidth = header.getBoundingClientRect().width;
          const column = columns[index];
          const onMove = (moveEvent) => {
            const width = Math.max(72, startWidth + moveEvent.clientX - startX);
            this._columnWidths[tableId] = this._columnWidths[tableId] || {};
            this._columnWidths[tableId][index] = width;
            header.style.width = `${width}px`;
            if (column) column.style.width = `${width}px`;
          };
          const onUp = () => {
            document.removeEventListener("pointermove", onMove);
            document.removeEventListener("pointerup", onUp);
            document.removeEventListener("pointercancel", onUp);
          };
          document.addEventListener("pointermove", onMove);
          document.addEventListener("pointerup", onUp, { once: true });
          document.addEventListener("pointercancel", onUp, { once: true });
        });
        header.appendChild(handle);
      });
    });
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
      .menu-button { display: none; flex: 0 0 auto; }
      h1 { margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0; }
      .metrics { display: flex; gap: 10px; margin-top: 6px; color: #9fb1c1; font-size: 13px; }
      .horn.on { color: #ffcf33; font-weight: 700; }
      .actions, .toolbar, .tabs, .rule-form, .bulk-actions, .bulk-summary { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
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
      .alarm-row { background: #11161b; color: #e6edf3; }
      .alarm-row td { border-bottom-color: rgba(16, 19, 22, .35); }
      .alarm-row button { background: rgba(16, 19, 22, .22); color: inherit; border-color: rgba(16, 19, 22, .4); }
      .alarm-row button:hover { background: rgba(16, 19, 22, .34); }
      .alarm-row.priority-critical.state-active-unack { background: #ef2b1d; color: #101316; border-left-color: #8f1711; }
      .alarm-row.priority-high.state-active-unack { background: #ff9f00; color: #101316; border-left-color: #a85b00; }
      .alarm-row.priority-medium.state-active-unack { background: #ffd800; color: #101316; border-left-color: #b69100; }
      .alarm-row.priority-low.state-active-unack { background: #58a6ff; color: #101316; border-left-color: #1d5fa8; }
      .alarm-row.priority-info.state-active-unack { background: #83d2e6; color: #101316; border-left-color: #34899f; }
      .alarm-row.priority-status.state-active-unack { background: #7ee787; color: #101316; border-left-color: #2f8a39; }
      .alarm-row.state-pending-color { background: #202832; color: #dbe4ec; border-left-color: #687585; }
      .alarm-row.state-cleared-unack { background: #d85b9d; color: #101316; border-left-color: #8e2f63; }
      .alarm-row.state-active-ack, .alarm-row.state-cleared-ack { background: #f3f4f6; color: #1f2933; border-left-color: #9ca3af; }
      .alarm-row.state-shelved, .alarm-row.state-disabled, .alarm-row.state-normal { background: #252c33; color: #aebdcc; border-left-color: #596675; }
      .badge { text-transform: uppercase; font-size: 12px; font-weight: 700; }
      .flash { animation: flashRow 1s step-end infinite; }
      @keyframes flashRow { 50% { filter: brightness(1.25); } }
      .empty, .error { color: #9fb1c1; padding: 18px; }
      .error { margin: 12px 18px; color: #ffd5d5; background: #5b1c1c; border: 1px solid #a83737; }
      .rules, .settings { padding: 12px 18px 18px; }
      .suggested-rules { margin-bottom: 12px; padding: 10px; border: 1px solid #2e3944; background: #151b21; }
      .suggested-rules h2 { margin: 0 0 8px; font-size: 15px; font-weight: 700; letter-spacing: 0; color: #e6edf3; }
      .suggested-rules-controls { display: flex; gap: 8px; align-items: end; flex-wrap: wrap; }
      .suggested-rules label { display: grid; gap: 4px; color: #b8c7d4; font-size: 12px; }
      .suggested-rules input { min-width: 90px; width: 110px; }
      .bulk-actions, .bulk-summary { margin-top: 8px; color: #b8c7d4; font-size: 13px; }
      .bulk-actions { margin-bottom: 10px; }
      .suggested-preview { margin-top: 8px; padding: 0; }
      .row-select { min-width: 0; width: 16px; height: 16px; padding: 0; }
      .notice { margin-top: 8px; color: #dbeafe; font-size: 13px; }
      .rule-form { margin-bottom: 12px; }
      .settings dl { display: grid; grid-template-columns: max-content minmax(120px, 1fr); gap: 10px 18px; max-width: 560px; }
      .settings dt { color: #9fb1c1; }
      .settings dd { margin: 0; }
      .resizable-column { position: relative; min-width: 72px; padding-right: 16px; }
      .col-resizer { position: absolute; top: 0; right: 0; width: 8px; height: 100%; cursor: col-resize; touch-action: none; user-select: none; }
      .col-resizer:hover { background: rgba(255, 255, 255, .18); }
      @media (max-width: 720px) {
        .topbar { align-items: flex-start; flex-direction: column; }
        .menu-button { display: inline-flex; align-items: center; justify-content: center; }
        input { min-width: 0; width: 100%; }
        .actions, .toolbar, .rule-form { width: 100%; }
        button, select { flex: 1 1 auto; }
      }
    `;
  }
}

if (!customElements.get("industrial-alarm-panel")) {
  customElements.define("industrial-alarm-panel", IndustrialAlarmPanel);
}
