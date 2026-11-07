"""Buttons of a KEF speaker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.components.button.const import ButtonDeviceClass
from homeassistant.const import EntityCategory

from pykefcontrol import Source

from .entity import KefEntity
from .setting_entity import KefSettingEntityDescription, exists, has_source

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from pykefcontrol import KefAsyncClient

    from .coordinator import KefConfigEntry

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KefButtonEntityDescription(KefSettingEntityDescription, ButtonEntityDescription):
    """Button calling a client method."""

    press_fn: Callable[[KefAsyncClient], Awaitable[Any]]


BUTTONS: tuple[KefButtonEntityDescription, ...] = (
    KefButtonEntityDescription(
        key="restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.reboot(),
    ),
    KefButtonEntityDescription(
        key="bluetooth_pairing",
        translation_key="bluetooth_pairing",
        supported_fn=has_source(Source.BLUETOOTH),
        press_fn=lambda client: client.bluetooth_pairing(),
    ),
    KefButtonEntityDescription(
        key="bluetooth_disconnect",
        translation_key="bluetooth_disconnect",
        supported_fn=has_source(Source.BLUETOOTH),
        press_fn=lambda client: client.bluetooth_disconnect(),
        entity_registry_enabled_default=False,
    ),
    KefButtonEntityDescription(
        key="reset_dsp",
        translation_key="reset_dsp",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda coordinator: coordinator.eq_profile is not None,
        press_fn=lambda client: client.reset_eq_profile(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KefConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons of a speaker."""
    coordinator = entry.runtime_data
    async_add_entities(
        KefButton(coordinator, desc) for desc in BUTTONS if exists(coordinator, desc)
    )


class KefButton(KefEntity, ButtonEntity):
    """An action of the speaker."""

    entity_description: KefButtonEntityDescription

    @override
    async def async_press(self) -> None:
        """Run the action."""
        await self.coordinator.async_call(
            self.entity_description.press_fn, self.coordinator.client
        )
