# Contributing

Thanks for helping improve Industrial Alarm Panel.

## Before You Open A PR

1. Search existing issues and pull requests.
2. Keep the change focused on one bug, feature, or documentation improvement.
3. Add or update tests when behavior changes.
4. Update `README.md` or `INSTALLATION.md` when the user-facing workflow changes.

## Local Checks

Run the lightweight checks before opening a pull request:

```bash
python3 -m unittest discover -s tests -v
node --check custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js
```

If you have a Home Assistant development environment available, also run the integration in a real Home Assistant instance and verify setup, services, and the `/industrial-alarms` panel.

## Pull Request Expectations

- Explain what changed and why.
- Include screenshots for panel or visual changes.
- Include the Home Assistant version used for manual validation.
- Do not include unrelated formatting or generated-file churn.

## Support Scope

GitHub issues are for reproducible bugs, feature requests, and documentation gaps. Installation questions should include the exact HACS/install step that failed and relevant Home Assistant log lines.
