"""Minimal stubs so helpers.py can be imported without a full HA install."""
import sys
import types


def _make_stub(*names):
    """Create a chain of stub modules: 'a.b.c' → a, a.b, a.b.c all registered."""
    root = names[0].split(".")[0]
    if root not in sys.modules:
        sys.modules[root] = types.ModuleType(root)
    for name in names:
        parts = name.split(".")
        for i in range(1, len(parts) + 1):
            full = ".".join(parts[:i])
            if full not in sys.modules:
                mod = types.ModuleType(full)
                sys.modules[full] = mod
                parent = ".".join(parts[:i - 1])
                if parent in sys.modules:
                    setattr(sys.modules[parent], parts[i - 1], mod)


# Stub out every homeassistant sub-module the integration touches
_stubs = [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.helpers",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.event",
    "homeassistant.helpers.restore_state",
    "homeassistant.helpers.selector",
    "homeassistant.util",
    "homeassistant.util.dt",
    "voluptuous",
]
for _s in _stubs:
    _make_stub(_s)

# Provide just enough real attributes that the integration modules can import cleanly
import enum

_ha = sys.modules["homeassistant"]
_ha.core = sys.modules["homeassistant.core"]

_ce = sys.modules["homeassistant.config_entries"]
_ce.ConfigEntry = object
_ce.ConfigFlow = object

_sensor = sys.modules["homeassistant.components.sensor"]
_sensor.SensorEntity = object
_sensor.SensorStateClass = enum.Enum("SensorStateClass", ["MEASUREMENT"])
_sensor.DOMAIN = "sensor"

_helpers = sys.modules["homeassistant.helpers"]
_helpers.selector = sys.modules["homeassistant.helpers.selector"]

_sel = sys.modules["homeassistant.helpers.selector"]
for _attr in (
    "EntitySelector", "EntitySelectorConfig", "TextSelector",
    "NumberSelector", "NumberSelectorConfig", "NumberSelectorMode",
):
    setattr(_sel, _attr, object)

_ep = sys.modules["homeassistant.helpers.entity_platform"]
_ep.AddEntitiesCallback = object

_ev = sys.modules["homeassistant.helpers.event"]
_ev.async_track_state_change_event = None
_ev.async_call_later = None

_vol = sys.modules["voluptuous"]
_vol.Schema = lambda x, **kw: x
_vol.Required = lambda x, **kw: x
_vol.Optional = lambda x, **kw: x
_vol.All = lambda *a, **kw: a[0]
_vol.Coerce = lambda t: t
_vol.Range = lambda **kw: None
