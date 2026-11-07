"""Switches of a KEF speaker (settings and EQ profile)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory

from pykefcontrol import Feature, Settings, Source, SpeakerModel

from .setting_entity import (
    KefSettingEntity,
    KefSettingEntityDescription,
    eq_v2,
    exists,
    is_model,
    supports,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import KefConfigEntry

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KefSwitchEntityDescription(KefSettingEntityDescription, SwitchEntityDescription):
    """Switch bound to a boolean setting or EQ field (``inverted``: a "disable")."""

    inverted: bool = False
    entity_category: EntityCategory | None = EntityCategory.CONFIG


SWITCHES: tuple[KefSwitchEntityDescription, ...] = (
    KefSwitchEntityDescription(
        key="desk_mode", translation_key="desk_mode", eq_field="desk_mode"
    ),
    KefSwitchEntityDescription(
        key="wall_mode", translation_key="wall_mode", eq_field="wall_mode"
    ),
    KefSwitchEntityDescription(
        key="phase_correction",
        translation_key="phase_correction",
        eq_field="phase_correction",
    ),
    KefSwitchEntityDescription(
        key="high_pass_filter",
        translation_key="high_pass_filter",
        eq_field="high_pass_mode",
    ),
    KefSwitchEntityDescription(
        key="subwoofer_output",
        translation_key="subwoofer_output",
        eq_field="subwoofer_out",
        exists_fn=eq_v2,
    ),
    KefSwitchEntityDescription(
        key="dialogue_mode",
        translation_key="dialogue_mode",
        setting=Settings.DIALOGUE_MODE,
        # Also reported by the LS50 Wireless II: effect on stereo speakers unknown.
        enabled_default_fn=is_model(SpeakerModel.XIO),
        entity_category=None,
    ),
    KefSwitchEntityDescription(
        key="startup_tone",
        translation_key="startup_tone",
        setting=Settings.STARTUP_TONE,
        supported_fn=supports(Feature.STARTUP_TONE),
    ),
    KefSwitchEntityDescription(
        key="front_led",
        translation_key="front_led",
        setting=Settings.DISABLE_FRONT_LED,
        inverted=True,
    ),
    KefSwitchEntityDescription(
        key="front_standby_led",
        translation_key="front_standby_led",
        setting=Settings.DISABLE_FRONT_STANDBY_LED,
        inverted=True,
        supported_fn=supports(Feature.STANDBY_FRONT_LED),
        entity_registry_enabled_default=False,
    ),
    KefSwitchEntityDescription(
        key="top_panel_led",
        translation_key="top_panel_led",
        setting=Settings.TOP_PANEL_LED,
        supported_fn=supports(Feature.TOP_PANEL_LED),
        entity_registry_enabled_default=False,
    ),
    KefSwitchEntityDescription(
        key="top_panel_standby_led",
        translation_key="top_panel_standby_led",
        setting=Settings.TOP_PANEL_STANDBY_LED,
        supported_fn=supports(Feature.TOP_PANEL_LED),
        entity_registry_enabled_default=False,
    ),
    KefSwitchEntityDescription(
        key="top_panel_lock",
        translation_key="top_panel_lock",
        setting=Settings.DISABLE_TOP_PANEL,
        supported_fn=supports(Feature.TOP_PANEL_LOCK),
    ),
    KefSwitchEntityDescription(
        key="auto_switch_tv",
        translation_key="auto_switch_tv",
        setting=Settings.AUTO_SWITCH_TO_TV,
        supported_fn=lambda caps: (
            caps.supports(Feature.AUTO_SWITCH_TV) and Source.TV in caps.sources
        ),
    ),
    KefSwitchEntityDescription(
        key="usb_charging",
        translation_key="usb_charging",
        setting=Settings.USB_CHARGING,
        supported_fn=supports(Feature.USB_CHARGING),
    ),
    KefSwitchEntityDescription(
        key="volume_limit",
        translation_key="volume_limit",
        setting=Settings.VOLUME_LIMIT,
    ),
    KefSwitchEntityDescription(
        key="subwoofer_always_on",
        translation_key="subwoofer_always_on",
        setting=Settings.SUBWOOFER_FORCE_ON,
        supported_fn=supports(Feature.SUBWOOFER_FORCE_ON),
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KefConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches of a speaker."""
    coordinator = entry.runtime_data
    async_add_entities(
        KefSwitch(coordinator, desc) for desc in SWITCHES if exists(coordinator, desc)
    )


class KefSwitch(KefSettingEntity, SwitchEntity):
    """A boolean setting or EQ field."""

    entity_description: KefSwitchEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """State of the switch."""
        if (value := self._value) is None:
            return None
        return bool(value) != self.entity_description.inverted

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await self._async_write(not self.entity_description.inverted)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await self._async_write(self.entity_description.inverted)
