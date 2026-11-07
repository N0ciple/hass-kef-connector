"""Base entity of the KEF Connector integration."""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Any, Concatenate

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from pykefcontrol.capabilities import model_info

from .const import DOMAIN
from .coordinator import KefCoordinator, kef_errors

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable

    from pykefcontrol import Capabilities, DeviceInfo as KefDeviceInfo, Setting


@dataclass(frozen=True, kw_only=True)
class KefEntityDescription(EntityDescription):
    """Description of a KEF entity and of the speaker data it follows.

    ``setting`` is followed by the coordinator's watch loop when ``supported_fn``
    accepts the speaker's capabilities (see ``ENTITY_DESCRIPTIONS`` in __init__).
    ``enabled_default_fn``, if set, replaces ``entity_registry_enabled_default``
    depending on the speaker.
    """

    setting: Setting[Any] | None = None
    supported_fn: Callable[[Capabilities], bool] = lambda _: True
    enabled_default_fn: Callable[[Capabilities], bool] | None = None


def followed_paths(
    descriptions: Iterable[KefEntityDescription], capabilities: Capabilities
) -> list[str]:
    """API paths of the settings needed by the supported descriptions."""
    return [
        d.setting.path
        for d in descriptions
        if d.setting is not None and d.supported_fn(capabilities)
    ]


def is_supported(
    coordinator: KefCoordinator, description: KefEntityDescription
) -> bool:
    """Tell whether an entity should be created for this speaker."""
    if not description.supported_fn(coordinator.capabilities):
        return False
    return description.setting is None or coordinator.has_value(
        description.setting.path
    )


def kef_command[EntityT: KefEntity, **P](
    func: Callable[Concatenate[EntityT, P], Coroutine[Any, Any, None]],
) -> Callable[Concatenate[EntityT, P], Coroutine[Any, Any, None]]:
    """Wrap an entity command to raise translated errors."""

    @wraps(func)
    async def wrapper(self: EntityT, /, *args: P.args, **kwargs: P.kwargs) -> None:
        with kef_errors():
            await func(self, *args, **kwargs)

    return wrapper


class KefEntity(CoordinatorEntity[KefCoordinator]):
    """Base KEF entity, attached to the speaker device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KefCoordinator,
        description: KefEntityDescription | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.mac = format_mac(coordinator.config_entry.unique_id or "")
        if description is not None:
            self.entity_description = description
            self._attr_unique_id = f"{self.mac}_{description.key}"
            if (enabled_fn := description.enabled_default_fn) is not None:
                self._attr_entity_registry_enabled_default = enabled_fn(
                    coordinator.capabilities
                )
        self._attr_device_info = device_info(coordinator)


def device_info(coordinator: KefCoordinator) -> DeviceInfo:
    """Device registry information of the speaker."""
    info = coordinator.device_info
    model = model_info(info.model)
    mac = format_mac(coordinator.config_entry.unique_id or "")
    return DeviceInfo(
        connections={(CONNECTION_NETWORK_MAC, mac)},
        identifiers={(DOMAIN, mac)},
        manufacturer="KEF",
        model=model.marketing_name,
        model_id=model.product_code or info.model_name,
        name=coordinator.config_entry.title,
        serial_number=info.serial_number,
        sw_version=_firmware(info),
    )


def _firmware(info: KefDeviceInfo) -> str | None:
    if (fw := info.firmware) is None:
        return None
    return f"{fw.major}.{fw.minor}.{fw.patch}" + (f".{fw.build}" if fw.build else "")
