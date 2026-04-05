# Home Assistant Energy Package

Reusable Home Assistant package to monitor household loads, warn when consumption is too high, and automatically disconnect manageable loads when an overload persists.

This is a package, not a single Home Assistant blueprint. It is meant to live under `packages/energy/` in your Home Assistant config and be adapted with labels and helpers instead of hardcoded entity IDs.

## In Simple Terms

This package watches the loads you care about.

If your house goes above the limit:

- it tries to understand which devices or areas are involved
- it warns you
- it waits a bit
- it checks again
- if needed, it turns off only the loads you marked as manageable

The simple setup flow is:

1. create the labels
2. assign them to your devices
3. copy the package
4. restart Home Assistant
5. optionally add the token and run the Python sync if you want smarter dynamic thresholds

Because the helpers are built into the package, you do not need to create them manually.

## Quick Start

- assign `EnergyMainPower` to your main house power sensor or device
- assign `EnergyAdvisory` to the devices you want to monitor
- assign `EnergyManageable` to the loads that are safe to turn off automatically
- optionally assign `EnergyNotify` if you want voice announcements
- copy the whole `packages/energy/` folder into your HA config
- restart Home Assistant

At that point the YAML core already works.

If you also add `ha_api_token` and run `script.sync_energy_thresholds`, the package becomes smarter because active-load detection uses recorder history instead of the default `20W` fallback threshold.

## Real Examples

Example setup:

- monitored only: microwave, oven
- manageable: kettle smart plug, dishwasher smart plug
- main power source: whole-house power sensor labeled `EnergyMainPower`

Scenario 1: above threshold, only advisory loads are active

- Microwave and oven are both active.
- Nothing safe to turn off is active.
- The package warns without trying to shed anything.
- Example message:
  `High consumption detected. Critical context: Kitchen. No automatic plan is sufficient: it is better to reduce load in Kitchen.`

Scenario 2: above threshold, one manageable load can be shed

- Microwave, oven, and kettle are active.
- The kettle is labeled `EnergyManageable`.
- The package warns first and gives you time to react.
- Example message:
  `High consumption detected. Critical context: Kitchen. If usage stays high, Kettle will be turned off in one minute.`

Scenario 3: even turning something off would not be enough

- Oven, microwave, and dishwasher are active, but the overload is too large.
- Turning off the dishwasher alone would still leave the house above the limit.
- The package warns, but does not do a useless shutdown.
- Example message:
  `Consumption is still high. Even turning off Dishwasher would remain above the limit: it is better to reduce load in Kitchen.`

Scenario 4: the package turns something off and the house comes back in range

- The kettle is still active after the grace period.
- The package turns it off.
- Total load returns below the contract limit.
- Example message:
  `Household load returned below the limit. Turned off Kettle.`

## Detailed Reference

- Discovers monitored devices via labels.
- Separates advisory-only devices from manageable loads that can actually be turned off.
- Groups advisory context by Home Assistant area when available, with a generic fallback when no area is assigned.
- Builds dynamic local thresholds from 60 days of recorder history.
- Detects overload against a contract limit.
- Warns first, waits, recalculates, and turns off loads only if the overload is still real and the plan is still valid.
- Supports dry run and debug inspection.
- Keeps voice notifications optional.

## Core Behavior

This package exists mainly for two things:

- give useful warnings about which loads or areas are contributing to a contract overload
- automatically shed manageable loads when that is the only sensible way to get back under the limit

The important path is:

1. discover devices through labels
2. determine active loads through dynamic per-device thresholds
3. identify the main overloaded contexts using labels plus areas
4. announce the issue
5. wait for a configurable grace period
6. recalculate
7. turn off only the manageable loads that still make sense to disconnect

## Package Layout

This package is effectively split into three layers:

- YAML core
  This is the main package. It handles overload detection, area-based advisory context, announcements, grace period, re-check, dry run, debug, and automatic load shedding.
- Python threshold sync
  This is not for dashboards. It computes dynamic per-device thresholds from recorder history and publishes `sensor.energy_threshold_*` entities used by the YAML logic.
- Dashboard
  The dashboard is optional. It only visualizes the sensors and scripts exposed by the package.

Without the Python sync, the package still works, but with a conservative fallback threshold of `20W` per device. That means the alerting and shedding flow still works, but active-load detection is less accurate and may produce more false positives.

## Required Labels

- `EnergyMainPower`
  Assign this to exactly one sensor entity or one device exposing exactly one main power sensor. The source sensor can have any name. The package creates a canonical sensor called `sensor.energy_total_power` and uses that internally.
- `EnergyAdvisory`
  Devices monitored for context and advice.
- `EnergyManageable`
  Devices that can also be turned off automatically. The current generic core expects exactly one power sensor and exactly one switch entity per device.

## Optional Labels

- `EnergyNotify`
  Devices exposing `media_player.*` entities for voice announcements. If `notify.alexa_media` is not installed, the package only logs the messages.

## Built-In Helpers

- `input_number.energy_contract_limit_w`
- `input_number.energy_warning_delay_seconds`

These helpers are included directly in the package via [helpers.yaml](https://github.com/Magnum9O/HA_BluePrints/tree/main/packages/energy/helpers.yaml), so you do not need to create them manually if you install the whole package.

## Files To Install

Copy these files into your Home Assistant config under `packages/energy/`:

- [automations.yaml](https://github.com/Magnum9O/HA_BluePrints/tree/main/packages/energy/automations.yaml)
- [helpers.yaml](https://github.com/Magnum9O/HA_BluePrints/tree/main/packages/energy/helpers.yaml)
- [scripts.yaml](https://github.com/Magnum9O/HA_BluePrints/tree/main/packages/energy/scripts.yaml)
- [template.yaml](https://github.com/Magnum9O/HA_BluePrints/tree/main/packages/energy/template.yaml)
- [shell_command.yaml](https://github.com/Magnum9O/HA_BluePrints/tree/main/packages/energy/shell_command.yaml)
- [scripts/sync_energy_thresholds.py](https://github.com/Magnum9O/HA_BluePrints/tree/main/packages/energy/scripts/sync_energy_thresholds.py)

## Installation

1. Enable packages in `configuration.yaml` if you do not already use them.
2. Copy the `packages/energy/` folder into `/config/packages/energy/`.
3. Copy the built-in helpers with the rest of the package.
4. Add label `EnergyMainPower` to your main household power source.
5. Add label `EnergyAdvisory` to devices you want included in context detection.
6. Add label `EnergyManageable` only to devices that are safe to turn off automatically and expose exactly one `switch.*` entity plus one power sensor.
7. Optionally add label `EnergyNotify` to media-player devices if you use Alexa Media Player announcements.
8. Add `ha_api_token` to `secrets.yaml`.
9. Reload templates, scripts, automations, and shell commands, or restart Home Assistant.
10. Run `script.sync_energy_thresholds` once manually.

For best results, also assign those devices to Home Assistant areas. Advisory summaries are built from the area when available. If a device has no area, the package falls back to a generic `general household load` context.

## `secrets.yaml`

Required:

```yaml
ha_api_token: YOUR_LONG_LIVED_ACCESS_TOKEN
```

Optional:

```yaml
homeassistant_url: http://127.0.0.1:8123
```

## Dynamic Thresholds

`script.sync_energy_thresholds` discovers the power sensors attached to devices labeled `EnergyAdvisory` or `EnergyManageable` and publishes runtime sensors like:

- `sensor.energy_threshold_device_<device_id>`
- `sensor.energy_thresholds_last_sync`

Threshold rules:

- 60-day history window
- REST API first, SQLite fallback
- positive numeric samples only
- threshold = `clamp(p95 * 0.1, 20W, 500W)`
- fallback threshold = `20W` when history is too small

The sync also removes stale `sensor.energy_threshold_*` entities and old `core.restore_state` entries left behind by renamed or removed devices.

These dynamic thresholds are used by the package logic itself, not only by the dashboard. They help determine whether a device is actually active, which affects:

- advisory context detection
- dry-run output
- shutdown planning
- final automatic load shedding decisions

## Dry Run And Debug

- `script.debug_energy_monitoring`
  Dumps the discovered manageable loads and advisory contexts to the system log.
- `script.plan_energy_shedding`
  Calculates the best shutdown plan.
- `script.plan_energy_shedding` with `dry_run: true`
  Logs what would be turned off without acting.

## Example Dashboard

A generic Lovelace example is available at [examples/dashboard-energy.yaml](https://github.com/Magnum9O/HA_BluePrints/tree/main/packages/energy/examples/dashboard-energy.yaml).

## Known Limits

- Recorder must be enabled, otherwise dynamic thresholds fall back aggressively.
- The generic manageable-load discovery only handles devices with exactly one power sensor and exactly one `switch.*` entity.
- Multi-entity loads such as grouped HVAC systems were intentionally removed from the public core.
- Voice announcements are optional and currently only implemented for `notify.alexa_media`.
- `shell_command` plus the external Python script are required only for dynamic threshold synchronization.
- If your main power source does not expose a clean single sensor, create a helper template sensor first and label that entity with `EnergyMainPower`.
- Advisory grouping is area-based when areas are available; there are no hardcoded room names in the public version.

## What Was Removed From The Private Source

- Hardcoded air-conditioner group entities.
- Hardcoded laundry or kitchen overrides.
- Direct dependence on a home-specific total-power sensor.
- Italian helper ids from the private package.
- Direct hard dependency on `notify.alexa_media`.

## New HA Install Checklist

- Packages enabled in Home Assistant.
- Recorder enabled and storing enough history.
- `ha_api_token` set in `secrets.yaml`.
- `EnergyMainPower` label assigned to exactly one main power source.
- `EnergyAdvisory` label assigned to monitored devices.
- `EnergyManageable` label assigned only to safe switch-based loads.
- Relevant devices assigned to Home Assistant areas if you want area-based advisory messages.
- Built-in contract limit helper present and set.
- Built-in warning delay helper present and set.
- Initial `script.sync_energy_thresholds` run completed successfully.
- `sensor.energy_thresholds_last_sync` present.
- `binary_sensor.energy_contract_overload` reacts correctly.
- `script.debug_energy_monitoring` shows the expected device set.

## Recommended Repo Structure

```text
HA_BluePrints/
  README.md
  packages/
    energy/
      README.md
      CHANGELOG.md
      automations.yaml
      helpers.yaml
      scripts.yaml
      template.yaml
      shell_command.yaml
      scripts/
        sync_energy_thresholds.py
      examples/
        dashboard-energy.yaml
      FORUM_POST.md
```
