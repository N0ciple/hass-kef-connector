"""Numbers of a KEF speaker (settings and EQ profile)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfFrequency

from pykefcontrol import Settings

from .setting_entity import KefSettingEntity, KefSettingEntityDescription, exists

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import KefConfigEntry, KefCoordinator

PARALLEL_UPDATES = 1

DECIBEL = "dB"


@dataclass(frozen=True, kw_only=True)
class KefNumberEntityDescription(KefSettingEntityDescription, NumberEntityDescription):
    """Number bound to a numeric setting or EQ field.

    EQ fields take their range from the speaker's EQ descriptors (or the app's
    defaults); ``convert`` turns the value into the type the speaker expects
    (``round``: Home Assistant does not enforce the step).
    """

    convert: Callable[[float], float] = float
    mode: NumberMode = NumberMode.SLIDER
    entity_category: EntityCategory | None = EntityCategory.CONFIG


def _eq_db(key: str, field: str) -> KefNumberEntityDescription:
    return KefNumberEntityDescription(
        key=key, translation_key=key, eq_field=field, native_unit_of_measurement=DECIBEL
    )


def _eq_hz(key: str, field: str) -> KefNumberEntityDescription:
    return KefNumberEntityDescription(
        key=key,
        translation_key=key,
        eq_field=field,
        device_class=NumberDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
    )


NUMBERS: tuple[KefNumberEntityDescription, ...] = (
    _eq_db("treble", "treble"),
    KefNumberEntityDescription(
        key="balance", translation_key="balance", eq_field="balance", convert=round
    ),
    _eq_db("desk_mode_attenuation", "desk_mode_setting"),
    _eq_db("wall_mode_attenuation", "wall_mode_setting"),
    _eq_db("subwoofer_gain", "subwoofer_gain"),
    _eq_hz("subwoofer_low_pass_frequency", "sub_out_low_pass_freq"),
    _eq_hz("high_pass_frequency", "high_pass_freq"),
    KefNumberEntityDescription(
        key="maximum_volume",
        translation_key="maximum_volume",
        setting=Settings.MAXIMUM_VOLUME,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        convert=round,
    ),
    KefNumberEntityDescription(
        key="volume_step",
        translation_key="volume_step",
        setting=Settings.VOLUME_STEP,
        native_min_value=1,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.BOX,
        convert=round,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KefConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the numbers of a speaker."""
    coordinator = entry.runtime_data
    async_add_entities(
        KefNumber(coordinator, desc) for desc in NUMBERS if exists(coordinator, desc)
    )


class KefNumber(KefSettingEntity, NumberEntity):
    """A numeric setting or EQ field."""

    entity_description: KefNumberEntityDescription

    def __init__(
        self, coordinator: KefCoordinator, description: KefNumberEntityDescription
    ) -> None:
        """Initialize the number with the range this speaker accepts."""
        super().__init__(coordinator, description)
        if description.eq_field is not None and (
            spec := coordinator.eq_ranges.get(description.eq_field)
        ):
            self._attr_native_min_value = spec.minimum
            self._attr_native_max_value = spec.maximum
            self._attr_native_step = spec.step

    @property
    @override
    def native_value(self) -> float | None:
        """Current value."""
        value = self._value
        return None if value is None else float(value)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Change the value."""
        await self._async_write(self.entity_description.convert(value))
