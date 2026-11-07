"""Selects of a KEF speaker (settings and EQ profile)."""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory

from pykefcontrol import (
    BassExtension,
    CableMode,
    FavouriteButtonFunction as Fav,
    Feature,
    MasterChannelMode,
    Settings,
    SoundProfile,
    Source,
    SpeakerModel,
    StandbyMode,
    SubwooferPreset,
    WakeUpSource,
)
from pykefcontrol.eq import apply_subwoofer_preset

from .setting_entity import (
    KefSettingEntity,
    KefSettingEntityDescription,
    eq_v2,
    exists,
    supports,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from pykefcontrol import Capabilities
    from pykefcontrol.enums import KefEnum

    from .coordinator import KefConfigEntry, KefCoordinator

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KefSelectEntityDescription(KefSettingEntityDescription, SelectEntityDescription):
    """Select bound to an enum setting or EQ field.

    The options are the known values of ``enum``, restricted to the choices of the
    speaker's EQ ``descriptor`` if it advertises them, and to ``option_fn``.
    """

    enum: type[KefEnum]
    descriptor: str | None = None
    option_fn: Callable[[Capabilities, str], bool] = lambda _caps, _option: True
    select_fn: Callable[[KefCoordinator, str], Awaitable[None]] | None = None
    entity_category: EntityCategory | None = EntityCategory.CONFIG


async def _async_select_subwoofer_preset(
    coordinator: KefCoordinator, option: str
) -> None:
    """Apply a subwoofer preset like the app (crossover and gain)."""
    if (profile := coordinator.eq_profile) is None:  # unknown right now: read it
        profile = await coordinator.async_call(coordinator.client.get_eq_profile)
    model = str(coordinator.capabilities.model)
    new = apply_subwoofer_preset(profile, SubwooferPreset(option), model)
    changes = {
        f.name: getattr(new, f.name)
        for f in dataclasses.fields(new)
        if getattr(new, f.name) != getattr(profile, f.name)
    }
    await coordinator.async_update_eq_profile(**changes)


def _option(value: str) -> str:
    """Translation key of a value (``nextSource`` -> ``next_source``)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value).lower()


def _wake_up_option(caps: Capabilities, option: str) -> bool:
    return option == WakeUpSource.DEFAULT or Source(option) in caps.sources


def _favourite_option(caps: Capabilities, option: str) -> bool:
    match option:
        case Fav.SET_USB_SOURCE:
            return Source.USB in caps.sources
        case Fav.ENABLE_BLUETOOTH_PAIRING:
            return Source.BLUETOOTH in caps.sources
        case Fav.SET_DIALOGUE_MODE:
            return caps.model == SpeakerModel.XIO
        case Fav.SET_CABLE_MODE:
            return caps.supports(Feature.CABLE_MODE)
        case Fav.SET_DISABLE_TOP_PANEL:
            return caps.supports(Feature.TOP_PANEL_LOCK)
    return option != Fav.UNKNOWN


SELECTS: tuple[KefSelectEntityDescription, ...] = (
    KefSelectEntityDescription(
        key="bass_extension",
        translation_key="bass_extension",
        eq_field="bass_extension",
        enum=BassExtension,
        descriptor="bassExtension",
    ),
    KefSelectEntityDescription(
        key="subwoofer_preset",
        translation_key="subwoofer_preset",
        eq_field="subwoofer_preset",
        enum=SubwooferPreset,
        descriptor="subwooferPreset",
        select_fn=_async_select_subwoofer_preset,
    ),
    KefSelectEntityDescription(
        key="sound_profile",
        translation_key="sound_profile",
        eq_field="sound_profile",
        enum=SoundProfile,
        descriptor="soundProfile",
        exists_fn=lambda coordinator: (
            eq_v2(coordinator)
            and (
                coordinator.capabilities.model == SpeakerModel.XIO
                or "soundProfile" in coordinator.eq_descriptors
            )
        ),
        entity_category=None,
    ),
    KefSelectEntityDescription(
        key="standby_delay",
        translation_key="standby_delay",
        setting=Settings.STANDBY_MODE,
        enum=StandbyMode,
    ),
    KefSelectEntityDescription(
        key="wake_up_source",
        translation_key="wake_up_source",
        setting=Settings.WAKE_UP_SOURCE,
        enum=WakeUpSource,
        option_fn=_wake_up_option,
    ),
    KefSelectEntityDescription(
        key="cable_mode",
        translation_key="cable_mode",
        setting=Settings.CABLE_MODE,
        enum=CableMode,
        supported_fn=supports(Feature.CABLE_MODE),
        entity_registry_enabled_default=False,
    ),
    KefSelectEntityDescription(
        key="master_channel",
        translation_key="master_channel",
        setting=Settings.MASTER_CHANNEL_MODE,
        enum=MasterChannelMode,
        entity_registry_enabled_default=False,
    ),
    KefSelectEntityDescription(
        key="favourite_button",
        translation_key="favourite_button",
        setting=Settings.FAVOURITE_BUTTON,
        enum=Fav,
        option_fn=_favourite_option,
        supported_fn=supports(Feature.ADVANCED_REMOTE_CONTROL),
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KefConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects of a speaker."""
    coordinator = entry.runtime_data
    async_add_entities(
        KefSelect(coordinator, desc) for desc in SELECTS if exists(coordinator, desc)
    )


class KefSelect(KefSettingEntity, SelectEntity):
    """An enum setting or EQ field."""

    entity_description: KefSelectEntityDescription

    def __init__(
        self, coordinator: KefCoordinator, description: KefSelectEntityDescription
    ) -> None:
        """Initialize the select with the options this speaker accepts."""
        super().__init__(coordinator, description)
        caps = coordinator.capabilities
        choices = None
        if description.descriptor is not None:
            row = coordinator.eq_descriptors.get(description.descriptor)
            choices = row.choices if row is not None and row.choices else None
        # Option (translation key) -> value sent to the speaker.
        self._values: dict[str, KefEnum] = {
            _option(member): member
            for member in description.enum
            if (choices is None or member in choices)
            and description.option_fn(caps, member)
        }
        self._attr_options = list(self._values)

    @property
    @override
    def current_option(self) -> str | None:
        """Current value (``None`` if unknown to this integration)."""
        value = self._value
        return None if value is None else _option(value)

    @override
    async def async_select_option(self, option: str) -> None:
        """Change the value."""
        value = self._values[option]
        if (select_fn := self.entity_description.select_fn) is not None:
            await select_fn(self.coordinator, value)
        else:
            await self._async_write(value)
