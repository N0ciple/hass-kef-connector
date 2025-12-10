"""Config flow for KEF Connector integration."""
from __future__ import annotations

import logging
from typing import Any

from pykefcontrol.kef_connector import KefAsyncConnector
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client, selector
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
    KEF_ZEROCONF_PREFIXES,
    MAX_MAX_VOLUME,
    MAX_OFFLINE_RETRY_INTERVAL,
    MAX_SCAN_INTERVAL,
    MAX_VOLUME_STEP,
    MIN_MAX_VOLUME,
    MIN_OFFLINE_RETRY_INTERVAL,
    MIN_SCAN_INTERVAL,
    MIN_VOLUME_STEP,
)

_LOGGER = logging.getLogger(__name__)


def parse_model_from_discovery(discovery_info: zeroconf.ZeroconfServiceInfo) -> str:
    """Parse KEF speaker model from zeroconf discovery info.

    Google Cast names typically contain the model name.
    Examples: "KEF LSX2", "KEF LSX2LT", "KEF LS60", etc.
    """
    # Check the service name first (this is where Google Cast puts the device name)
    name = discovery_info.name.upper()

    # Check for known models in order of specificity (most specific first)
    if "LSX2LT" in name or "LSX II LT" in name or "LSX-II-LT" in name:
        return "LSX2LT"
    elif "LSX2" in name or "LSX II" in name or "LSX-II" in name:
        return "LSX2"
    elif "LS50W2" in name or "LS50 WIRELESS II" in name or "LS50-WIRELESS-II" in name:
        return "LS50W2"
    elif "LS60" in name:
        return "LS60"
    elif "XIO" in name:
        return "XIO"

    # Also check properties dict in case it's there
    properties = discovery_info.properties
    if properties:
        # Check for model in common property keys
        for key in ["md", "model", "device_model"]:
            if key in properties:
                model_value = properties[key].upper()
                if "LSX2LT" in model_value:
                    return "LSX2LT"
                elif "LSX2" in model_value:
                    return "LSX2"
                elif "LS50W2" in model_value:
                    return "LS50W2"
                elif "LS60" in model_value:
                    return "LS60"
                elif "XIO" in model_value:
                    return "XIO"

    # Default to LSX2 if we can't detect
    _LOGGER.debug(
        "Could not detect KEF model from discovery info (name=%s), defaulting to LSX2",
        discovery_info.name
    )
    return "LSX2"


def is_kef_speaker(discovery_info: zeroconf.ZeroconfServiceInfo) -> bool:
    """Check if discovered device is a KEF speaker based on zeroconf name.

    KEF speakers advertise with specific Google Cast name patterns.
    Returns True if the device appears to be a KEF speaker.
    """
    name_upper = discovery_info.name.upper()
    return any(name_upper.startswith(prefix) for prefix in KEF_ZEROCONF_PREFIXES)


async def validate_connection(
    hass: HomeAssistant, host: str
) -> dict[str, Any]:
    """Validate the connection to a KEF speaker.

    Returns dict with:
        - mac_address: for unique_id
        - speaker_name: for friendly name
        - speaker_model: for device info and source list
    """
    session = aiohttp_client.async_get_clientsession(hass)
    connector = KefAsyncConnector(host, session=session)

    try:
        # Get speaker information
        mac_address = await connector.mac_address
        speaker_name = await connector.speaker_name

        # Validate we got valid data
        if not mac_address or not speaker_name:
            raise ValueError("Unable to retrieve speaker information")

        # Note: speaker_model is not available from the API
        # We'll default to "LSX2" which is the most common model
        return {
            "mac_address": format_mac(mac_address),
            "speaker_name": speaker_name,
            "speaker_model": "LSX2",
        }
    except Exception as err:
        _LOGGER.error("Error connecting to KEF speaker at %s: %s", host, err)
        raise


class KefConnectorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for KEF Connector."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None
        self._detected_model: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - manual IP entry."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]

            try:
                info = await validate_connection(self.hass, host)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                # Set unique ID to prevent duplicates
                await self.async_set_unique_id(info["mac_address"])
                self._abort_if_unique_id_configured()

                # Get user-selected model and options
                speaker_model = user_input.get(CONF_SPEAKER_MODEL, "LSX2").upper()
                options = {
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    CONF_OFFLINE_RETRY_INTERVAL: user_input.get(
                        CONF_OFFLINE_RETRY_INTERVAL, DEFAULT_OFFLINE_RETRY_INTERVAL
                    ),
                    CONF_VOLUME_STEP: user_input.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP),
                    CONF_MAX_VOLUME: user_input.get(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME),
                }

                return self.async_create_entry(
                    title=info["speaker_name"],
                    data={
                        CONF_HOST: host,
                        CONF_NAME: info["speaker_name"],
                        CONF_SPEAKER_MODEL: speaker_model,
                    },
                    options=options,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_SPEAKER_MODEL, default="LSX2"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["LSX2", "LSX2LT", "LS50W2", "LS60", "XIO"],
                        translation_key="speaker_model",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=DEFAULT_SCAN_INTERVAL,
                ): vol.All(vol.Coerce(int), vol.Range(
                    min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL
                )),
                vol.Required(
                    CONF_OFFLINE_RETRY_INTERVAL,
                    default=DEFAULT_OFFLINE_RETRY_INTERVAL,
                ): vol.All(vol.Coerce(int), vol.Range(
                    min=MIN_OFFLINE_RETRY_INTERVAL, max=MAX_OFFLINE_RETRY_INTERVAL
                )),
                vol.Required(
                    CONF_VOLUME_STEP,
                    default=DEFAULT_VOLUME_STEP,
                ): vol.All(vol.Coerce(float), vol.Range(
                    min=MIN_VOLUME_STEP, max=MAX_VOLUME_STEP
                )),
                vol.Required(
                    CONF_MAX_VOLUME,
                    default=DEFAULT_MAX_VOLUME,
                ): vol.All(vol.Coerce(float), vol.Range(
                    min=MIN_MAX_VOLUME, max=MAX_MAX_VOLUME
                )),
            }),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle zeroconf discovery."""
        host = discovery_info.host

        # Filter: Only process KEF speakers
        if not is_kef_speaker(discovery_info):
            _LOGGER.debug(
                "Ignoring non-KEF Google Cast device '%s' at %s",
                discovery_info.name,
                host
            )
            return self.async_abort(reason="not_kef_device")

        # Try to get speaker info
        try:
            info = await validate_connection(self.hass, host)
        except Exception:
            return self.async_abort(reason="cannot_connect")

        # Set unique ID and abort if already configured
        await self.async_set_unique_id(info["mac_address"])
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        # Parse model from discovery info (Google Cast name)
        self._detected_model = parse_model_from_discovery(discovery_info)
        _LOGGER.info(
            "Detected KEF model '%s' for speaker '%s' from zeroconf discovery",
            self._detected_model,
            info["speaker_name"]
        )

        # Store discovered info for confirmation step
        self._discovered_host = host
        self._discovered_name = info["speaker_name"]

        # Set suggested name in context for the UI
        self.context["title_placeholders"] = {
            "name": info["speaker_name"],
        }

        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            # User confirmed, get full speaker info
            try:
                info = await validate_connection(self.hass, self._discovered_host)
            except Exception:
                return self.async_abort(reason="cannot_connect")

            # Use the user-selected model
            speaker_model = user_input.get(CONF_SPEAKER_MODEL, "LSX2").upper()

            # Extract options for initial setup
            options = {
                CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                CONF_OFFLINE_RETRY_INTERVAL: user_input.get(
                    CONF_OFFLINE_RETRY_INTERVAL, DEFAULT_OFFLINE_RETRY_INTERVAL
                ),
                CONF_VOLUME_STEP: user_input.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP),
                CONF_MAX_VOLUME: user_input.get(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME),
            }

            return self.async_create_entry(
                title=info["speaker_name"],
                data={
                    CONF_HOST: self._discovered_host,
                    CONF_NAME: info["speaker_name"],
                    CONF_SPEAKER_MODEL: speaker_model,
                },
                options=options,
            )

        # Show form with speaker model selection (using detected model as default)
        detected_model = self._detected_model or "LSX2"
        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_SPEAKER_MODEL, default=detected_model): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["LSX2", "LSX2LT", "LS50W2", "LS60", "XIO"],
                        translation_key="speaker_model",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=DEFAULT_SCAN_INTERVAL,
                ): vol.All(vol.Coerce(int), vol.Range(
                    min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL
                )),
                vol.Required(
                    CONF_OFFLINE_RETRY_INTERVAL,
                    default=DEFAULT_OFFLINE_RETRY_INTERVAL,
                ): vol.All(vol.Coerce(int), vol.Range(
                    min=MIN_OFFLINE_RETRY_INTERVAL, max=MAX_OFFLINE_RETRY_INTERVAL
                )),
                vol.Required(
                    CONF_VOLUME_STEP,
                    default=DEFAULT_VOLUME_STEP,
                ): vol.All(vol.Coerce(float), vol.Range(
                    min=MIN_VOLUME_STEP, max=MAX_VOLUME_STEP
                )),
                vol.Required(
                    CONF_MAX_VOLUME,
                    default=DEFAULT_MAX_VOLUME,
                ): vol.All(vol.Coerce(float), vol.Range(
                    min=MIN_MAX_VOLUME, max=MAX_MAX_VOLUME
                )),
            }),
            description_placeholders={
                "name": self._discovered_name,
                "host": self._discovered_host,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> KefConnectorOptionsFlow:
        """Get the options flow for this handler."""
        return KefConnectorOptionsFlow(config_entry)


class KefConnectorOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for KEF Connector."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        # config_entry is set by the flow manager as a property
        # We just need to accept it as a parameter

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(
                    min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL
                )),
                vol.Required(
                    CONF_OFFLINE_RETRY_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_OFFLINE_RETRY_INTERVAL, DEFAULT_OFFLINE_RETRY_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(
                    min=MIN_OFFLINE_RETRY_INTERVAL, max=MAX_OFFLINE_RETRY_INTERVAL
                )),
                vol.Required(
                    CONF_VOLUME_STEP,
                    default=self.config_entry.options.get(
                        CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(
                    min=MIN_VOLUME_STEP, max=MAX_VOLUME_STEP
                )),
                vol.Required(
                    CONF_MAX_VOLUME,
                    default=self.config_entry.options.get(
                        CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(
                    min=MIN_MAX_VOLUME, max=MAX_MAX_VOLUME
                )),
            }),
        )
