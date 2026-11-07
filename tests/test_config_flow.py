"""Tests of the config flow of KEF Connector."""

from __future__ import annotations

from ipaddress import ip_address
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.config_entries import (
    SOURCE_IMPORT,
    SOURCE_USER,
    SOURCE_ZEROCONF,
    ConfigEntryState,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kef_connector.const import (
    CONF_MAX_VOLUME,
    CONF_VOLUME_STEP,
    DOMAIN,
)
from pykefcontrol import KefConnectionError, KefProtocolError, SpeakerModel

from .common import device_info
from .const import (
    FIRMWARE,
    HOST,
    HOST_IPV6_GLOBAL,
    HOST_IPV6_LINK_LOCAL,
    MAC,
    NAME,
    SERIAL,
    SERVICE_NAME,
    UNIQUE_ID,
)

if TYPE_CHECKING:
    from unittest.mock import AsyncMock, MagicMock

    from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.usefixtures("mock_setup_entry")

OLD_HOST = "192.168.1.20"

TXT_RECORDS = {
    "name": NAME,
    "mac": MAC,
    "model": "SP4025",
    "modelName": "LS50 Wireless II",
    "manufacturer": "KEF",
    "serialNumber": SERIAL,
    "serialNumberSlave": "",
    "version": FIRMWARE,
    "kefId": "b1d0c6d2-8e3f-4f7a-9a52-3c1f0e6d4b21",
    "groupId": "N/A",
    "groupName": "N/A",
    "groupRole": "N/A",
}


def zeroconf_info(
    addresses: list[str] | None = None, properties: dict[str, Any] | None = None
) -> ZeroconfServiceInfo:
    """Discovery of the LS50 Wireless II."""
    if addresses is None:
        addresses = [HOST, HOST_IPV6_LINK_LOCAL, HOST_IPV6_GLOBAL]
    ips = [ip_address(a) for a in addresses]
    return ZeroconfServiceInfo(
        ip_address=ips[0] if ips else ip_address(HOST),
        ip_addresses=ips,
        port=80,
        hostname="841715000001.local.",
        type="_kef-info._tcp.local.",
        name=SERVICE_NAME,
        properties=TXT_RECORDS if properties is None else properties,
    )


# --- user ---------------------------------------------------------------------


async def test_user(
    hass: HomeAssistant, mock_kef_client: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """A speaker is set up from its address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: f" {HOST} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_HOST: HOST}
    assert result["options"] == {}
    assert result["result"].unique_id == UNIQUE_ID
    mock_kef_client.aclose.assert_awaited_once()
    mock_setup_entry.assert_awaited_once()


async def test_user_title_from_model(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """A speaker without a name is named after its model."""
    mock_kef_client.get_device_info.return_value = device_info(name=None)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LS50 Wireless II"


@pytest.mark.parametrize(
    ("side_effect", "info", "error"),
    [
        (KefConnectionError("timeout"), None, "cannot_connect"),
        (KefProtocolError("not KEF"), None, "not_kef"),
        (RuntimeError("boom"), None, "unknown"),
        (None, device_info(mac_address=None), "not_kef"),
    ],
)
async def test_user_errors(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    side_effect: Exception | None,
    info: Any,
    error: str,
) -> None:
    """Errors are shown, and the user can retry."""
    good_info = mock_kef_client.get_device_info.return_value
    mock_kef_client.get_device_info.side_effect = side_effect
    if info is not None:
        mock_kef_client.get_device_info.return_value = info
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}
    mock_kef_client.aclose.assert_awaited_once()

    mock_kef_client.get_device_info.side_effect = None
    mock_kef_client.get_device_info.return_value = good_info
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME


async def test_user_unreachable_host(
    hass: HomeAssistant, mock_kef_client_class: MagicMock
) -> None:
    """Nothing answers at the address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: "192.168.1.99"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_already_configured(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """A configured speaker is not added twice; its address is updated."""
    entry = MockConfigEntry(
        domain=DOMAIN, title=NAME, unique_id=UNIQUE_ID, data={CONF_HOST: OLD_HOST}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == {CONF_HOST: HOST}


# --- zeroconf -----------------------------------------------------------------


async def test_zeroconf(
    hass: HomeAssistant, mock_kef_client: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """A discovered speaker is set up once confirmed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {
        "name": NAME,
        "model": "LS50 Wireless II",
        "host": HOST,
    }
    # The MAC address is in the TXT records: no connection needed yet.
    mock_kef_client.get_device_info.assert_not_called()
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["unique_id"] == UNIQUE_ID
    assert flows[0]["context"]["title_placeholders"] == {"name": NAME}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_HOST: HOST}
    assert result["result"].unique_id == UNIQUE_ID
    mock_setup_entry.assert_awaited_once()


async def test_zeroconf_prefers_ipv4(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """The IPv4 address is used even when IPv6 addresses come first."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=zeroconf_info([HOST_IPV6_GLOBAL, HOST_IPV6_LINK_LOCAL, HOST]),
    )
    assert result["description_placeholders"]["host"] == HOST
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST}


async def test_zeroconf_ipv6_only(
    hass: HomeAssistant, mock_kef_client_class: MagicMock
) -> None:
    """A speaker with IPv6 addresses only is offered at its IPv6 address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=zeroconf_info([HOST_IPV6_GLOBAL]),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"]["host"] == HOST_IPV6_GLOBAL


async def test_zeroconf_no_address(hass: HomeAssistant) -> None:
    """A discovery without address is ignored."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info([])
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_zeroconf_without_mac(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """Without MAC address in the TXT records, the speaker is asked."""
    mock_kef_client.get_device_info.return_value = device_info(name="Bureau")
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=zeroconf_info(properties={"model": "SP4025"}),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"]["name"] == "Bureau"
    mock_kef_client.get_device_info.assert_awaited_once()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bureau"
    assert result["result"].unique_id == UNIQUE_ID


async def test_zeroconf_name_from_service(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """Without name in the TXT records, the service name is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=zeroconf_info(properties={"mac": MAC, "model": "SP4025"}),
    )
    assert result["description_placeholders"]["name"] == "841715000001@LS50WII"


@pytest.mark.parametrize(
    ("side_effect", "info", "reason"),
    [
        (KefConnectionError("timeout"), None, "cannot_connect"),
        (KefProtocolError("not KEF"), None, "cannot_connect"),
        (None, device_info(mac_address=None), "not_kef"),
    ],
)
async def test_zeroconf_without_mac_errors(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    side_effect: Exception | None,
    info: Any,
    reason: str,
) -> None:
    """The discovery is aborted when the speaker cannot tell its MAC address."""
    mock_kef_client.get_device_info.side_effect = side_effect
    if info is not None:
        mock_kef_client.get_device_info.return_value = info
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=zeroconf_info(properties={}),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


async def test_zeroconf_already_configured(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """A configured speaker discovered at a new address gets it."""
    entry = MockConfigEntry(
        domain=DOMAIN, title=NAME, unique_id=UNIQUE_ID, data={CONF_HOST: OLD_HOST}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == {CONF_HOST: HOST}


async def test_zeroconf_already_in_progress(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """A speaker is offered once."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


async def test_discovery_confirm_error(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """Errors at confirmation are shown, and the user can retry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    mock_kef_client.get_device_info.side_effect = KefConnectionError("timeout")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["errors"] == {"base": "cannot_connect"}

    mock_kef_client.get_device_info.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_while_zeroconf_in_progress(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """The user flow is aborted when the speaker is already being discovered."""
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


# --- reconfigure --------------------------------------------------------------


async def test_reconfigure(
    hass: HomeAssistant, mock_kef_client: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """The address of the speaker can be changed."""
    entry = MockConfigEntry(
        domain=DOMAIN, title=NAME, unique_id=UNIQUE_ID, data={CONF_HOST: OLD_HOST}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    schema = result["data_schema"].schema
    key = next(k for k in schema if k == CONF_HOST)
    assert key.description == {"suggested_value": OLD_HOST}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_HOST: HOST}
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_reconfigure_other_speaker(
    hass: HomeAssistant, second_kef_client: MagicMock
) -> None:
    """The address of another speaker is refused."""
    entry = MockConfigEntry(
        domain=DOMAIN, title=NAME, unique_id=UNIQUE_ID, data={CONF_HOST: HOST}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: second_kef_client.host}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert entry.data == {CONF_HOST: HOST}


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """Errors are shown, and the user can retry."""
    entry = MockConfigEntry(
        domain=DOMAIN, title=NAME, unique_id=UNIQUE_ID, data={CONF_HOST: OLD_HOST}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_HOST: HOST}


# --- import -------------------------------------------------------------------


async def test_import(hass: HomeAssistant, mock_kef_client: MagicMock) -> None:
    """The YAML configuration is imported with its name and options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_HOST: HOST,
            CONF_NAME: "Living room KEF",
            "maximum_volume": 0.6,
            "volume_step": 0.05,
            "speaker_model": "LS50",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living room KEF"
    assert result["data"] == {CONF_HOST: HOST}
    assert result["options"] == {CONF_MAX_VOLUME: 60, CONF_VOLUME_STEP: 5}
    assert result["result"].unique_id == UNIQUE_ID


@pytest.mark.parametrize(
    ("import_data", "options"),
    [
        (
            {CONF_NAME: "DEFAULT_KEFSPEAKER"},
            {CONF_MAX_VOLUME: 100, CONF_VOLUME_STEP: 3},
        ),
        ({}, {CONF_MAX_VOLUME: 100, CONF_VOLUME_STEP: 3}),
        (
            {"maximum_volume": 0.004, "volume_step": 0.5},
            {CONF_MAX_VOLUME: 1, CONF_VOLUME_STEP: 10},
        ),
    ],
)
async def test_import_defaults(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    import_data: dict[str, Any],
    options: dict[str, int],
) -> None:
    """Without a name, the speaker name is used; options are kept in range."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_HOST: HOST, **import_data},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["options"] == options


@pytest.mark.parametrize(
    ("side_effect", "info", "reason"),
    [
        (KefConnectionError("timeout"), None, "cannot_connect"),
        (KefProtocolError("not KEF"), None, "not_kef"),
        (RuntimeError("boom"), None, "unknown"),
        (None, device_info(mac_address=None), "not_kef"),
    ],
)
async def test_import_errors(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    side_effect: Exception | None,
    info: Any,
    reason: str,
) -> None:
    """The import is aborted when the speaker cannot be read."""
    mock_kef_client.get_device_info.side_effect = side_effect
    if info is not None:
        mock_kef_client.get_device_info.return_value = info
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_import_already_configured_with_options(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """Options set in the UI are not replaced by the YAML ones."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        unique_id=UNIQUE_ID,
        data={CONF_HOST: HOST},
        options={CONF_MAX_VOLUME: 80, CONF_VOLUME_STEP: 2},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_HOST: HOST, "maximum_volume": 0.6, "volume_step": 0.05},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.options == {CONF_MAX_VOLUME: 80, CONF_VOLUME_STEP: 2}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_import_already_configured_without_options(
    hass: HomeAssistant, mock_kef_client: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """A speaker set up from the UI first gets the YAML options."""
    entry = MockConfigEntry(
        domain=DOMAIN, title=NAME, unique_id=UNIQUE_ID, data={CONF_HOST: HOST}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert mock_setup_entry.await_count == 1

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_HOST: HOST, "maximum_volume": 0.6, "volume_step": 0.05},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.options == {CONF_MAX_VOLUME: 60, CONF_VOLUME_STEP: 5}
    await hass.async_block_till_done()
    assert mock_setup_entry.await_count == 2  # reloaded with the options
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_import_while_zeroconf_in_progress(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """The import wins over a pending discovery of the same speaker."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == UNIQUE_ID
    # The discovery flow is aborted: the speaker is configured.
    assert hass.config_entries.flow.async_progress() == []


# --- options ------------------------------------------------------------------


async def test_options(
    hass: HomeAssistant, mock_kef_client: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """The maximum volume and the volume step are options (integers)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        unique_id=UNIQUE_ID,
        data={CONF_HOST: HOST},
        options={CONF_MAX_VOLUME: 60, CONF_VOLUME_STEP: 5},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    schema = result["data_schema"].schema
    suggested = {str(k): k.description for k in schema}
    assert suggested == {
        CONF_MAX_VOLUME: {"suggested_value": 60},
        CONF_VOLUME_STEP: {"suggested_value": 5},
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MAX_VOLUME: 75.0, CONF_VOLUME_STEP: 2.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_MAX_VOLUME: 75, CONF_VOLUME_STEP: 2}
    assert all(type(v) is int for v in entry.options.values())
    await hass.async_block_till_done()
    assert mock_setup_entry.await_count == 2  # reloaded


async def test_model_in_discovery_unknown(
    hass: HomeAssistant, mock_kef_client_class: MagicMock
) -> None:
    """An unknown model is shown with its product code."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=zeroconf_info(properties={"mac": MAC, "model": "SP9999"}),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"]["model"] == str(SpeakerModel("SP9999"))
