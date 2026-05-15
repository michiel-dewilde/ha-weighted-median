# Weighted Median Filter

A Home Assistant custom integration that adds a **helper sensor** computing the **time-weighted median** of any numerical source entity over a configurable sliding time window.

## What it does

Given a source sensor (e.g. a temperature probe) that changes value over time, this helper maintains an in-memory history of those changes and continuously exposes the **p50 (median)** of that history, weighted by how long each value was held.

Unlike a simple average, the median is robust to outliers: a brief spike to an extreme value contributes weight only proportional to the time it was actually measured.

## Why "time-weighted"?

Each historical reading contributes to the median in proportion to the duration it was the current value within the window. A value held for 30 minutes counts three times as much as one held for 10 minutes.

**Example** — 1-hour window, source values during that hour:

| Value | Duration |
|-------|----------|
| 18 °C | 20 min   |
| 22 °C | 35 min   |
| 30 °C | 5 min    |

Sorted by value, cumulative time: 20 min → 55 min → 60 min. The 50% mark (30 min) falls in the 22 °C bucket → **median = 22 °C**.

## Installation

1. Copy the `custom_components/weighted_median/` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for **Weighted Median Filter**.

## Configuration

| Field | Description | Default |
|-------|-------------|---------|
| Name | Friendly name for the new sensor | — |
| Source entity | The sensor whose values are filtered | — |
| Window duration | Sliding window length in seconds (60 – 604800) | 3600 |

After creation the helper appears as a regular sensor entity and can be used in dashboards, automations, and templates.

## Behaviour

### History

The integration reacts to state changes of the source entity in real time — it does **not** query the recorder database. History is kept in memory only and is reset when Home Assistant restarts.

On startup the current state of the source is used as a seed value (treated as if it has been the value for the entire window), so the sensor reports a meaningful value immediately.

### Non-numerical states

States such as `unavailable`, `unknown`, or any non-numeric string are silently excluded from the calculation. Their time is not counted toward the window total.

- As long as at least one numerical reading exists within the window, the sensor reports a value.
- If **all** data in the window is non-numerical (or the window is empty), the sensor becomes `unavailable`.

### Event-driven scheduling

The sensor never polls. It is woken up by two kinds of events:

1. **Source state change** — a new reading is appended to history, the median is recomputed, and the next scheduled wakeup is set.
2. **Scheduled wakeup** — fired at the earliest future moment where the median *would* change if the source stayed constant. The sensor recomputes and reschedules.

The scheduled wakeup time is the minimum of:

- **Oldest segment exits** — the oldest reading in the window slides out as the window advances. This changes the pool of weighted values.
- **p50 shifts analytically** — as the oldest segment loses weight and the newest segment gains weight at 1 s/s, the cumulative weighted distribution shifts continuously. The exact crossing time where p50 moves to the next value bucket is solved in closed form.
- **Rate-change point** — if the oldest segment is still entirely inside the window (not yet clipped), it will start losing weight in the future. The time of this transition is also a candidate, since the dynamics change there.

This means the sensor is as reactive as possible: it updates the instant the weighted median changes, rather than on a fixed poll interval.

## How the algorithm works

### Segments

History is stored as a list of `(timestamp, value)` pairs, each meaning "the source had *value* from this timestamp until the next entry." The most recent entry extends to *now*.

When computing the median for window `[now - W, now]`, each entry is clipped to the window. Entries with non-numerical values are excluded, and the remaining `(value, duration)` pairs are sorted by value. The cumulative sum is walked until it reaches 50% of the total numerical duration — the value at that point is the median.

### Next-change prediction

As time advances (source constant):
- The **oldest** segment's effective start is dragged forward by the advancing window boundary → its weight decreases at exactly 1 s/s (when it is clipped).
- The **newest** segment's effective end advances with *now* → its weight increases at exactly 1 s/s.
- All interior segments have fixed weight.

This makes the weight dynamics **linear in time**, so the exact moment the sorted-cumulative-sum crosses the 50% threshold can be solved analytically as a simple linear equation.

## Files

```
custom_components/weighted_median/
├── __init__.py         — integration setup
├── manifest.json       — HA metadata
├── const.py            — constants
├── config_flow.py      — UI config flow
├── helpers.py          — pure algorithm (no HA imports)
├── sensor.py           — SensorEntity, HA event wiring
└── translations/
    └── en.json         — UI strings

tests/
├── conftest.py         — HA module stubs for pure-Python testing
└── test_helpers.py     — 34 unit tests covering the algorithm
```

Run tests with:

```bash
py -m pytest tests/
```
