"""Diagnostics of the KEF Connector integration."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from enum import Enum
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import KefConfigEntry

TO_REDACT = {
    CONF_HOST,
    "host",
    "mac_address",
    "serial_number",
    "ssid",
    "bssid",
    "ip",
    "ip_address",
    "unique_id",
    # Bluetooth address of the speaker (bluetooth:state) and KEF account / multiroom
    # member ids found in the player data.
    "address",
    "kefId",
    "memberId",
    "systemMemberId",
}


def _jsonable(value: Any) -> Any:
    """Turn pykefcontrol dataclasses into JSON-friendly data."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _jsonable(getattr(value, f.name))
            for f in dataclasses.fields(value)
            if f.name != "raw"
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, set | frozenset):  # sorted: stable output
        return sorted((_jsonable(v) for v in value), key=str)
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KefConfigEntry
) -> dict[str, Any]:
    """Return diagnostics of a config entry."""
    coordinator = entry.runtime_data
    state = coordinator.data
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
                "unique_id": entry.unique_id,
            },
            "device_info": _jsonable(coordinator.device_info),
            "capabilities": _jsonable(coordinator.capabilities),
            "transport": {"secure": coordinator.client.is_secure},
            "eq_version": coordinator.eq_version,
            "extra_paths": list(coordinator.extra_paths),
            "available": coordinator.last_update_success,
            "state": _jsonable(state) if state else None,
            "player_raw": _jsonable(dict(state.player.raw))
            if state and state.player
            else None,
            "eq_profile": _jsonable(coordinator.eq_profile) if state else None,
        },
        TO_REDACT,
    )
