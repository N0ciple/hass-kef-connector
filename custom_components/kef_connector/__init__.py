"""The KEF Connector integration."""
from __future__ import annotations

import logging

from pykefcontrol.kef_connector import KefAsyncConnector

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_MAX_VOLUME,
    CONF_OFFLINE_RETRY_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_SPEAKER_MODEL,
    CONF_VOLUME_STEP,
    DEFAULT_MAX_VOLUME,
    DEFAULT_OFFLINE_RETRY_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
)
from .coordinator import KefCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SENSOR]


class KefHassAsyncConnector(KefAsyncConnector):
    """KefAsyncConnector with Home Assistant session management."""

    def __init__(
        self,
        host: str,
        session=None,
        hass: HomeAssistant | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize the KefAsyncConnector."""
        super().__init__(host, session=session, model=model)
        self.hass = hass

    async def resurect_session(self):
        """Resurect the session if it is closed."""
        if self._session is None:
            self._session = aiohttp_client.async_get_clientsession(self.hass)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KEF Connector from a config entry."""
    host = entry.data[CONF_HOST]
    name = entry.data[CONF_NAME]

    # Get options with defaults
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    offline_retry_interval = entry.options.get(
        CONF_OFFLINE_RETRY_INTERVAL, DEFAULT_OFFLINE_RETRY_INTERVAL
    )

    # Create aiohttp session
    session = aiohttp_client.async_get_clientsession(hass)

    speaker_model = entry.data.get(CONF_SPEAKER_MODEL, "LSX2").upper()

    # Create KEF speaker connector
    speaker = KefHassAsyncConnector(host, session=session, hass=hass, model=speaker_model)

    # Create coordinator
    coordinator = KefCoordinator(
        hass,
        speaker,
        name,
        scan_interval,
        offline_retry_interval,
        speaker_model=speaker_model,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Get coordinator
    coordinator: KefCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Update intervals
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    offline_retry_interval = entry.options.get(
        CONF_OFFLINE_RETRY_INTERVAL, DEFAULT_OFFLINE_RETRY_INTERVAL
    )
    coordinator.update_intervals(scan_interval, offline_retry_interval)

    # Request coordinator refresh with new interval
    await coordinator.async_request_refresh()
