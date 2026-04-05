# Draft Forum Post

## Title

Label-driven Home Assistant energy package for overload alerts and automatic load shedding ⚡

## Body

Hi everyone,

I extracted one of the energy-management packages from my personal Home Assistant setup into a reusable package for the community.

It is not a blueprint. It is a package-based setup meant for users who already organize their config under `packages/`.

The goal is simple: mark the loads you want to watch, mark the ones that are safe to disconnect, copy the package, restart HA, and let it warn you or shed load if the contract limit stays too high.

So in simple terms:

1. create the labels 🏷️
2. assign them to your devices
3. copy the package 📦
4. restart Home Assistant 🔄
5. enjoy

If you also add a token and run the Python sync, the package becomes smarter because it learns dynamic thresholds from recorder history.

The main goal is not just showing power data. The package is built to monitor household loads, warn when the contract limit is being exceeded, and automatically disconnect manageable loads if the overload persists.

It is effectively a two-part package:

- a YAML core for alerts, advisory logic, and automatic load shedding
- an optional Python sync for dynamic thresholds based on recorder history

The Python part is not there for the dashboard. The dashboard is optional and only visualizes the entities exposed by the package.

### ✨ A Few Real Examples

Example setup:

- monitored only: microwave, oven
- manageable: kettle smart plug, dishwasher smart plug

Scenario 1: overload, but only advisory loads are active 👀

> High consumption detected. Critical context: Kitchen. No automatic plan is sufficient: it is better to reduce load in Kitchen.

Scenario 2: overload, one manageable load is active and can be shed ⚠️

> High consumption detected. Critical context: Kitchen. If usage stays high, Kettle will be turned off in one minute.

Scenario 3: even the best shutdown would not be enough 🚫

> Consumption is still high. Even turning off Dishwasher would remain above the limit: it is better to reduce load in Kitchen.

Scenario 4: the package turns something off and the house comes back under the limit ✅

> Household load returned below the limit. Turned off Kettle.

### 🔧 Main Features

- label-based discovery for monitored devices
- separation between advisory devices and manageable loads
- area-based advisory summaries when devices are assigned to Home Assistant areas
- dynamic per-device active thresholds generated from recorder history
- overload warnings plus minimum viable shutdown planning
- dry run and debug scripts
- optional voice notifications

### 🧠 How It Works

- `EnergyMainPower` identifies the main household power sensor
- `EnergyAdvisory` marks devices used for context detection
- `EnergyManageable` marks switch-based loads that can be turned off automatically
- advisory contexts are grouped by area when available, otherwise they fall back to a generic household context
- thresholds are generated from the last 60 days of history through a Python sync script
- the package first warns, then waits, recalculates, and only shuts down loads if the plan still makes sense

### 📝 Important Notes

- recorder must be enabled
- a long-lived access token is required in `secrets.yaml`
- Alexa announcements are optional, not required
- hardcoded room names and private multi-entity exceptions from my setup were removed from the public core

### 📁 Repo Structure

- package files under `packages/energy/`
- built-in helpers inside the package
- example dashboard
- public README with setup checklist

I would be interested in feedback especially from people with:

- different smart plug vendors
- non-Shelly manageable loads
- unusual recorder setups
- grouped or multi-entity loads that need an extension pattern

If useful, I can also add example override patterns for HVAC groups or other multi-entity loads.
