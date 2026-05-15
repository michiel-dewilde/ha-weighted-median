"""Weighted Median sensor platform."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import event as ev_helper
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_SOURCE_ENTITY, CONF_WINDOW_SECONDS, DOMAIN
from .helpers import (
    compute_next_change_delta,
    compute_time_weighted_median,
    trim_history,
)

_LOGGER = logging.getLogger(__name__)

# Minimum scheduling gap to avoid busy-loops (seconds)
_MIN_SCHEDULE_DELTA = 0.1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            WeightedMedianSensor(
                hass=hass,
                entry_id=entry.entry_id,
                name=entry.data["name"],
                source_entity_id=entry.data[CONF_SOURCE_ENTITY],
                window_seconds=int(entry.data[CONF_WINDOW_SECONDS]),
            )
        ]
    )


class WeightedMedianSensor(SensorEntity):
    """A sensor that exposes the time-weighted median of a source entity."""

    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        name: str,
        source_entity_id: str,
        window_seconds: int,
    ) -> None:
        self.hass = hass
        self._attr_unique_id = entry_id
        self._attr_name = name
        self._source_entity_id = source_entity_id
        self._window_seconds = window_seconds

        # History: list of (posix_timestamp, value_or_None), ascending
        self._history: list[tuple[float, float | None]] = []
        self._cancel_scheduled: Any | None = None
        self._unsubscribe_source: Any | None = None

    # ── HA lifecycle ───────────────────────────────────────────────────────────

    async def async_added_to_hass(self) -> None:
        # Pull unit_of_measurement from source if available
        source_state = self.hass.states.get(self._source_entity_id)
        if source_state is not None:
            self._attr_native_unit_of_measurement = source_state.attributes.get(
                "unit_of_measurement"
            )
            # Seed history with the current state of the source (at now - window)
            # so the sensor is immediately useful on first load.
            now = dt_util.utcnow().timestamp()
            seed_val = _parse_value(source_state.state)
            self._history = [(now - self._window_seconds, seed_val)]

        self._unsubscribe_source = ev_helper.async_track_state_change_event(
            self.hass, [self._source_entity_id], self._on_source_change
        )

        self._refresh(dt_util.utcnow().timestamp())

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe_source:
            self._unsubscribe_source()
            self._unsubscribe_source = None
        self._cancel_pending()

    # ── Event handlers ─────────────────────────────────────────────────────────

    @callback
    def _on_source_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        ts = new_state.last_updated.timestamp()
        val = _parse_value(new_state.state)

        # Update unit_of_measurement if source provides it
        uom = new_state.attributes.get("unit_of_measurement")
        if uom and uom != self._attr_native_unit_of_measurement:
            self._attr_native_unit_of_measurement = uom

        self._history.append((ts, val))
        self._refresh(ts)

    @callback
    def _on_scheduled(self, _fire_time: Any) -> None:
        self._cancel_scheduled = None
        self._refresh(dt_util.utcnow().timestamp())

    # ── Core refresh ───────────────────────────────────────────────────────────

    @callback
    def _refresh(self, now: float) -> None:
        """Recompute state and schedule the next wakeup."""
        self._cancel_pending()

        window_start = now - self._window_seconds
        self._history = trim_history(self._history, window_start)

        median = compute_time_weighted_median(self._history, self._window_seconds, now)
        new_value = round(median, 6) if median is not None else None
        new_available = median is not None

        if new_value != self._attr_native_value or new_available != self._attr_available:
            self._attr_native_value = new_value
            self._attr_available = new_available
            self.async_write_ha_state()

        delta = compute_next_change_delta(self._history, self._window_seconds, now)
        if delta is not None and delta >= _MIN_SCHEDULE_DELTA:
            self._cancel_scheduled = ev_helper.async_call_later(
                self.hass, delta, self._on_scheduled
            )
            _LOGGER.debug(
                "%s: next recalculation in %.1f s", self.entity_id, delta
            )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _cancel_pending(self) -> None:
        if self._cancel_scheduled is not None:
            self._cancel_scheduled()
            self._cancel_scheduled = None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "source_entity": self._source_entity_id,
            "window_seconds": self._window_seconds,
            "history_entries": len(self._history),
        }


def _parse_value(state_str: str) -> float | None:
    """Convert a HA state string to float, or None if non-numerical."""
    try:
        val = float(state_str)
        import math
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except (ValueError, TypeError):
        return None
