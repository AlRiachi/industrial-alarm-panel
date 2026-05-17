export const DOMAIN = "industrial_alarm_panel";

export const commands = {
  listAlarms: `${DOMAIN}/list_alarms`,
  listHistory: `${DOMAIN}/list_history`,
  listRules: `${DOMAIN}/list_rules`,
  createRule: `${DOMAIN}/create_rule`,
  listSuggestedRules: `${DOMAIN}/list_suggested_rules`,
  createSuggestedRules: `${DOMAIN}/create_suggested_rules`,
  deleteRules: `${DOMAIN}/delete_rules`,
  updateRule: `${DOMAIN}/update_rule`,
  deleteRule: `${DOMAIN}/delete_rule`,
  acknowledge: `${DOMAIN}/acknowledge`,
  acknowledgeAll: `${DOMAIN}/acknowledge_all`,
  silence: `${DOMAIN}/silence`,
  shelve: `${DOMAIN}/shelve`,
  testSound: `${DOMAIN}/test_sound`,
  exportHistory: `${DOMAIN}/export_history`,
};
