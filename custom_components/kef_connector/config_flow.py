"""Config flow for the KEF Connector integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, override

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_NAME, PERCENTAGE
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from pykefcontrol import DeviceInfo, KefAsyncClient, KefError, KefProtocolError
from pykefcontrol.capabilities import model_info
from pykefcontrol.discovery import parse_service_info

from .const import (
    CONF_MAX_VOLUME,
    CONF_VOLUME_STEP,
    DEFAULT_MAX_VOLUME,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
    LEGACY_CONF_MAX_VOLUME,
    LEGACY_CONF_VOLUME_STEP,
    LEGACY_DEFAULT_MAX_VOLUME,
    LEGACY_DEFAULT_NAME,
    LEGACY_DEFAULT_VOLUME_STEP,
    MAX_VOLUME_RANGE,
    VOLUME_STEP_RANGE,
    legacy_options,
)

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema({vol.Required(CONF_HOST): TextSelector()})


def _percent_selector(bounds: tuple[int, int]) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=bounds[0],
            max=bounds[1],
            step=1,
            unit_of_measurement=PERCENTAGE,
            mode=NumberSelectorMode.SLIDER,
        )
    )


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MAX_VOLUME, default=DEFAULT_MAX_VOLUME): _percent_selector(
            MAX_VOLUME_RANGE
        ),
        vol.Required(CONF_VOLUME_STEP, default=DEFAULT_VOLUME_STEP): _percent_selector(
            VOLUME_STEP_RANGE
        ),
    }
)


def _title(info: DeviceInfo) -> str:
    return info.name or model_info(info.model).marketing_name


class KefConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for KEF speakers."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._host = ""
        self._name = ""
        self._model = ""

    @staticmethod
    @override
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KefOptionsFlow:
        """Return the options flow."""
        return KefOptionsFlow()

    async def _async_get_info(self, host: str) -> DeviceInfo:
        """Read the identity of the speaker at ``host``."""
        client = KefAsyncClient(host, session=async_get_clientsession(self.hass))
        try:
            return await client.get_device_info()
        finally:
            await client.aclose()

    async def _async_try_get_info(
        self, host: str, errors: dict[str, str]
    ) -> tuple[DeviceInfo, str] | None:
        """Read the identity and formatted MAC, filling ``errors`` on failure."""
        try:
            info = await self._async_get_info(host)
        except KefProtocolError:
            errors["base"] = "not_kef"
        except KefError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while connecting to %s", host)
            errors["base"] = "unknown"
        else:
            if info.mac_address:
                return info, format_mac(info.mac_address)
            errors["base"] = "not_kef"
        return None

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a speaker from its address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if found := await self._async_try_get_info(host, errors):
                info, mac = found
                await self.async_set_unique_id(
                    mac, raise_on_progress=self.source != SOURCE_RECONFIGURE
                )
                if self.source == SOURCE_RECONFIGURE:
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(), data_updates={CONF_HOST: host}
                    )
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=_title(info), data={CONF_HOST: host}
                )
        elif self.source == SOURCE_RECONFIGURE:
            user_input = dict(self._get_reconfigure_entry().data)
        return self.async_show_form(
            step_id="reconfigure" if self.source == SOURCE_RECONFIGURE else "user",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA,  # type: ignore[arg-type]  # probatio on HA 2026.9+
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of the speaker."""
        return await self.async_step_user(user_input)

    @override
    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a speaker discovered by zeroconf (``_kef-info._tcp``)."""
        found = parse_service_info(
            discovery_info.addresses,
            discovery_info.properties,
            name=discovery_info.name,
        )
        if found is None:
            return self.async_abort(reason="cannot_connect")
        self._host = found.host
        self._name = found.name or found.marketing_name
        self._model = found.marketing_name
        mac = found.mac_address
        if not mac:  # not in the TXT records: ask the speaker
            try:
                info = await self._async_get_info(self._host)
            except KefError:
                return self.async_abort(reason="cannot_connect")
            if not (mac := info.mac_address):
                return self.async_abort(reason="not_kef")
            self._name = _title(info)
        await self.async_set_unique_id(format_mac(mac))
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the setup of a discovered speaker."""
        errors: dict[str, str] = {}
        if user_input is not None and (
            found := await self._async_try_get_info(self._host, errors)
        ):
            return self.async_create_entry(
                title=_title(found[0]), data={CONF_HOST: self._host}
            )
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": self._name,
                "model": self._model,
                "host": self._host,
            },
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import a speaker of the 0.x YAML platform."""
        host: str = import_data[CONF_HOST]
        errors: dict[str, str] = {}
        if (found := await self._async_try_get_info(host, errors)) is None:
            return self.async_abort(reason=errors["base"])
        info, mac = found
        await self.async_set_unique_id(mac, raise_on_progress=False)
        options = legacy_options(
            import_data.get(LEGACY_CONF_MAX_VOLUME, LEGACY_DEFAULT_MAX_VOLUME),
            import_data.get(LEGACY_CONF_VOLUME_STEP, LEGACY_DEFAULT_VOLUME_STEP),
        )
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, mac)
        if entry is not None and not entry.options:
            # Set up from the UI or discovery first: keep the YAML options.
            self.hass.config_entries.async_update_entry(entry, options=options)
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        self._abort_if_unique_id_configured()
        name = import_data.get(CONF_NAME)
        return self.async_create_entry(
            title=name if name and name != LEGACY_DEFAULT_NAME else _title(info),
            data={CONF_HOST: host},
            options=options,
        )


class KefOptionsFlow(OptionsFlowWithReload):
    """Options of a KEF speaker."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={key: int(value) for key, value in user_input.items()}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA,  # type: ignore[arg-type]  # probatio on HA 2026.9+
                self.config_entry.options,
            ),
        )
