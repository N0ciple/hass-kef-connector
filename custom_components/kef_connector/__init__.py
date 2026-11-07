"""The KEF Connector integration."""

from __future__ import annotations

import logging

from homeassistant.components.media_player.const import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pykefcontrol import (
    Capabilities,
    Feature,
    KefApiError,
    KefAsyncClient,
    KefConnectionError,
    KefError,
    KefProtocolError,
    KefUnsupportedError,
)

from .binary_sensor import BINARY_SENSORS
from .button import BUTTONS
from .const import DOMAIN, LEGACY_UNIQUE_ID_PREFIX, MEDIA_PLAYER_UNIQUE_ID_PREFIX
from .coordinator import KefConfigEntry, KefCoordinator
from .entity import KefEntityDescription, device_info, followed_paths
from .number import NUMBERS
from .select import SELECTS
from .switch import SWITCHES

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]

# Entity descriptions of every platform (e.g. ``*select.SELECTS``): the settings
# they declare are followed by the coordinator's watch loop, which starts before
# the platforms are set up.
ENTITY_DESCRIPTIONS: tuple[KefEntityDescription, ...] = (
    *BINARY_SENSORS,
    *BUTTONS,
    *NUMBERS,
    *SELECTS,
    *SWITCHES,
)


async def async_setup_entry(hass: HomeAssistant, entry: KefConfigEntry) -> bool:
    """Set up a KEF speaker from a config entry."""
    host: str = entry.data[CONF_HOST]
    client = KefAsyncClient(host, session=async_get_clientsession(hass))
    entry.async_on_unload(client.aclose)
    try:
        info = await client.get_device_info()
        capabilities = await client.get_capabilities()
        eq_version = await _async_eq_version(client, capabilities)
    except KefConnectionError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": host},
        ) from err
    except KefError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="setup_failed",
            translation_placeholders={"host": host, "error": str(err)},
        ) from err
    if info.mac_address and dr.format_mac(info.mac_address) != entry.unique_id:
        # Another device answers at this address: wait for zeroconf to update it.
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="wrong_device",
            translation_placeholders={"host": host},
        )

    coordinator = KefCoordinator(
        hass,
        entry,
        client=client,
        device_info=info,
        capabilities=capabilities,
        eq_version=eq_version,
        extra_paths=followed_paths(ENTITY_DESCRIPTIONS, capabilities),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _async_migrate_registry(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start_watch()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KefConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: KefConfigEntry) -> bool:
    """Migrate an old config entry (none yet: 1.1 is the first version)."""
    return entry.version == 1  # False: downgrade from a future version


async def _async_eq_version(
    client: KefAsyncClient, capabilities: Capabilities
) -> int | None:
    """EQ profile format of the speaker, ``None`` if it has no EQ profile."""
    if not capabilities.supports(Feature.EQ_PROFILE):
        return None
    try:
        return await client.get_eq_version()
    except KefApiError, KefProtocolError, KefUnsupportedError:
        return None


@callback
def _async_migrate_registry(
    hass: HomeAssistant, entry: KefConfigEntry, coordinator: KefCoordinator
) -> None:
    """Adopt the media player entity of the 0.x YAML platform.

    Its unique id is kept, so it keeps its entity id and user settings; it is
    attached to the device and the config entry here, before the platform loads.
    """
    mac = dr.format_mac(entry.unique_id or "")
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, **device_info(coordinator)
    )
    unique_id = f"{MEDIA_PLAYER_UNIQUE_ID_PREFIX}_{mac}"
    entity_id = ent_reg.async_get_entity_id(MEDIA_PLAYER_DOMAIN, DOMAIN, unique_id)
    if entity_id is None:
        # Before 0.4: "KEFLS50W2_<mac>".
        for entity in list(ent_reg.entities.values()):
            prefix, _, legacy_mac = entity.unique_id.partition("_")
            if (
                entity.platform == DOMAIN
                and entity.domain == MEDIA_PLAYER_DOMAIN
                and prefix == LEGACY_UNIQUE_ID_PREFIX
                and dr.format_mac(legacy_mac) == mac
            ):
                _LOGGER.info("Migrating unique id of %s", entity.entity_id)
                ent_reg.async_update_entity(entity.entity_id, new_unique_id=unique_id)
                entity_id = entity.entity_id
                break
    if entity_id is None or (legacy := ent_reg.async_get(entity_id)) is None:
        return
    if legacy.config_entry_id is not None:
        return  # already adopted, or belongs to another entry
    _LOGGER.info("Adopting %s from the YAML configuration", entity_id)
    if legacy.area_id and legacy.name is None and device.area_id is None:
        # The media player is the device's main entity (no name of its own): its
        # area belongs to the device, otherwise HA raises a repair issue.
        dev_reg.async_update_device(device.id, area_id=legacy.area_id)
        ent_reg.async_update_entity(
            entity_id,
            area_id=None,
            config_entry_id=entry.entry_id,
            device_id=device.id,
        )
    else:
        ent_reg.async_update_entity(
            entity_id, config_entry_id=entry.entry_id, device_id=device.id
        )
