"""Binary sensors of a KEF speaker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from pykefcontrol import BluetoothState, Setting, Source, ValueType, paths

from .setting_entity import (
    KefSettingEntity,
    KefSettingEntityDescription,
    exists,
    has_source,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import KefConfigEntry

PARALLEL_UPDATES = 0

# Pushed by the speaker like the settings (the app subscribes to it too).
BLUETOOTH_STATE: Setting[dict[str, Any]] = Setting(
    paths.BLUETOOTH_STATE, ValueType.BLUETOOTH_STATE, dict, writable=False
)


@dataclass(frozen=True, kw_only=True)
class KefBinarySensorEntityDescription(
    KefSettingEntityDescription, BinarySensorEntityDescription
):
    """Binary sensor computed from a followed value."""

    is_on_fn: Callable[[Any], bool]


BINARY_SENSORS: tuple[KefBinarySensorEntityDescription, ...] = (
    KefBinarySensorEntityDescription(
        key="bluetooth_connected",
        translation_key="bluetooth_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        setting=BLUETOOTH_STATE,
        supported_fn=has_source(Source.BLUETOOTH),
        is_on_fn=lambda value: BluetoothState.from_api(value).connected,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KefConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors of a speaker."""
    coordinator = entry.runtime_data
    async_add_entities(
        KefBinarySensor(coordinator, desc)
        for desc in BINARY_SENSORS
        if exists(coordinator, desc)
    )


class KefBinarySensor(KefSettingEntity, BinarySensorEntity):
    """A state reported by the speaker."""

    entity_description: KefBinarySensorEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """State of the sensor."""
        value = self._value
        return None if value is None else self.entity_description.is_on_fn(value)
