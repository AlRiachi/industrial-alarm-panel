# Industrial Alarm Panel

Industrial Alarm Panel is a Home Assistant custom integration that provides a DCS-style alarm annunciator for industrial, energy, and equipment monitoring.

It creates Home Assistant entities, exposes services and a websocket API, persists alarm rules and runtime state, stores alarm history in SQLite, and serves a dedicated sidebar panel at `/industrial-alarms`.

Current release: `v1.0.5`

## Installation

1. Add this repository as a HACS custom repository with category `Integration`:

   ```text
   https://github.com/AlRiachi/industrial-alarm-panel
   ```

2. Install **Industrial Alarm Panel** from HACS.
3. Restart Home Assistant.
4. Go to **Settings > Devices & services > Add integration** and search for **Industrial Alarm Panel**.

The repository follows HACS integration layout rules: all runtime files are under `custom_components/industrial_alarm_panel`, with a root `hacs.json` and one integration directory under `custom_components`.

See [INSTALLATION.md](INSTALLATION.md) for manual installation, media-player sound setup, and a test rule.

## Entities

Global entities include:

- `sensor.industrial_alarm_active_count`
- `sensor.industrial_alarm_unacknowledged_count`
- `sensor.industrial_alarm_critical_count`
- `sensor.industrial_alarm_high_count`
- `sensor.industrial_alarm_last_alarm`
- `sensor.industrial_alarm_last_event`
- `binary_sensor.industrial_alarm_any_active`
- `binary_sensor.industrial_alarm_any_unacknowledged`
- `binary_sensor.industrial_alarm_horn_active`
- `switch.industrial_alarm_sound_enabled`
- `button.industrial_alarm_acknowledge_all`
- `button.industrial_alarm_silence_horn`
- `button.industrial_alarm_unsilence_horn`
- `button.industrial_alarm_test_sound`
- `select.industrial_alarm_filter_priority`
- `number.industrial_alarm_history_retention_days`

Every stored rule also gets a binary alarm sensor and action buttons after the integration reloads.

## Rule Example

Create a rule from Developer Tools > Services:

```yaml
service: industrial_alarm_panel.create_rule
data:
  rule:
    id: inverter_high_temp
    entity_id: sensor.inverter_temperature
    name: Inverter High Temperature
    tag: INV-TEMP-HH
    area: Solar Inverter
    system: PV
    condition: above
    threshold: 75
    deadband: 2
    priority: critical
    requires_ack: true
    audible: true
    delay_on_seconds: 5
    delay_off_seconds: 10
    instructions: Check inverter ventilation, fans, ambient temperature, and loading.
```

Supported conditions are `above`, `below`, `equal`, `not_equal`, `contains`, `is_on`, `is_off`, `state_changed`, `unavailable`, `unavailable_for`, `unknown_for`, and `manual`.

## Services

The integration registers:

- `industrial_alarm_panel.acknowledge_alarm`
- `industrial_alarm_panel.acknowledge_all`
- `industrial_alarm_panel.silence_horn`
- `industrial_alarm_panel.unsilence_horn`
- `industrial_alarm_panel.shelve_alarm`
- `industrial_alarm_panel.unshelve_alarm`
- `industrial_alarm_panel.disable_alarm`
- `industrial_alarm_panel.enable_alarm`
- `industrial_alarm_panel.create_rule`
- `industrial_alarm_panel.update_rule`
- `industrial_alarm_panel.delete_rule`
- `industrial_alarm_panel.test_sound`
- `industrial_alarm_panel.export_history`

Silence only stops horn output. Acknowledgement changes the alarm lifecycle state.

## Sound

Browser sound is generated in the panel with Web Audio after the operator clicks **Enable Alarm Sound**. Media-player output uses Home Assistant `media_player.play_media` with files expected at:

```text
/config/www/industrial_alarm_panel/sounds/
```

Default filenames are `critical.mp3`, `high.mp3`, `medium.mp3`, `low.mp3`, and `info.mp3`.

## Storage

Rules are stored in Home Assistant storage with key `industrial_alarm_panel.rules`.
Runtime alarm states are stored with key `industrial_alarm_panel.state`.
History is stored in `/config/industrial_alarm_panel_history.db`.

## Development

Runtime dependencies are provided by Home Assistant. The root `requirements.txt` documents that there are no extra runtime Python packages.

Run the pure core tests without Home Assistant installed:

```bash
python3 -m unittest discover -s tests -v
```

For full Home Assistant integration tests, install `requirements_test.txt` in a virtual environment and run pytest.
