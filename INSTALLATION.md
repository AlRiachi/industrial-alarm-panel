# Installation

This repository is a HACS custom integration for Home Assistant.

## HACS Installation

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=AlRiachi&repository=industrial-alarm-panel&category=integration)

1. Open Home Assistant.
2. Go to **HACS > Integrations**.
3. Open the menu in the top right and choose **Custom repositories**.
4. Add this repository URL:

   ```text
   https://github.com/AlRiachi/industrial-alarm-panel
   ```

5. Select category **Integration**.
6. Install **Industrial Alarm Panel**.
7. Restart Home Assistant.
8. Go to **Settings > Devices & services > Add integration**.
9. Search for **Industrial Alarm Panel** and complete the setup flow.

After setup, the sidebar panel is available at:

```text
/industrial-alarms
```

After every HACS update, restart Home Assistant. If the panel was already open in your browser, hard refresh it with `Ctrl+Shift+R`.

## Manual Installation

1. Copy this directory into your Home Assistant config directory:

   ```text
   custom_components/industrial_alarm_panel
   ```

2. Restart Home Assistant.
3. Add the integration from **Settings > Devices & services > Add integration**.

Manual installation is useful for local testing. HACS is preferred for normal use and upgrades.

## Optional Media Player Sound Files

For media-player alarm sound, place MP3 files here:

```text
/config/www/industrial_alarm_panel/sounds/
```

Recommended filenames:

```text
critical.mp3
high.mp3
medium.mp3
low.mp3
info.mp3
```

Browser sound works without these files after the operator clicks **Enable Alarm Sound** in the alarm panel.

## Create A Test Rule

Use **Developer Tools > Services**:

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
    instructions: Check inverter ventilation and fans.
```

For production rules, prefer stable `entity_id` references and create separate rules for high and low numeric limits. For example, grid voltage needs one `below` rule and one `above` rule.

## Development Requirements

Runtime requirements are declared in `custom_components/industrial_alarm_panel/manifest.json`.
The root `requirements.txt` is intentionally empty except for comments because Home Assistant provides the runtime environment.

For tests and local development:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements_test.txt
pytest
```
