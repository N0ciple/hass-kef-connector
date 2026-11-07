"""Tests of the buttons of KEF Connector."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
    Platform,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import snapshot_platform

from custom_components.kef_connector.const import DOMAIN
from pykefcontrol import (
    KefApiError,
    KefConnectionError,
    KefUnsupportedError,
    Source,
    SpeakerModel,
)

from .common import (
    EQ_PATH,
    entity_id,
    entity_keys,
    set_model,
    settings_state,
    setup_integration,
)

if TYPE_CHECKING:
    from typing import Any
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from syrupy.assertion import SnapshotAssertion

    from .common import WatchController


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the buttons only."""
    return [Platform.BUTTON]


async def _press(hass: HomeAssistant, key: str) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: entity_id(hass, BUTTON_DOMAIN, key)},
        blocking=True,
    )


def _state(hass: HomeAssistant, key: str) -> str:
    state = hass.states.get(entity_id(hass, BUTTON_DOMAIN, key))
    assert state is not None
    return state.state


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Snapshot of the buttons of the LS50 Wireless II."""
    await snapshot_platform(hass, entity_registry, snapshot, init_settings.entry_id)


async def test_entity_set(hass: HomeAssistant, init_settings: MockConfigEntry) -> None:
    """LS50 Wireless II: buttons, enabled by default or not, and categories."""
    entries = entity_keys(hass, init_settings)
    assert {
        key: (entry.disabled_by is None, entry.entity_category)
        for key, entry in entries.items()
    } == {
        "restart": (True, EntityCategory.CONFIG),
        "bluetooth_pairing": (True, None),
        "bluetooth_disconnect": (False, None),
        "reset_dsp": (True, EntityCategory.CONFIG),
    }
    assert _state(hass, "restart") == STATE_UNKNOWN


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("key", "method"),
    [
        ("restart", "reboot"),
        ("bluetooth_pairing", "bluetooth_pairing"),
        ("bluetooth_disconnect", "bluetooth_disconnect"),
        ("reset_dsp", "reset_eq_profile"),
    ],
)
async def test_press(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    key: str,
    method: str,
) -> None:
    """Each button calls its client method."""
    await _press(hass, key)
    getattr(settings_client, method).assert_awaited_once_with()
    assert _state(hass, key) != STATE_UNKNOWN  # time of the last press


@pytest.mark.parametrize(
    ("exception", "error", "translation_key"),
    [
        (KefConnectionError("timeout"), HomeAssistantError, "communication_error"),
        (KefApiError(500, "Internal error"), HomeAssistantError, "command_failed"),
        (KefUnsupportedError("no Bluetooth"), HomeAssistantError, "command_failed"),
        (TypeError("bad call"), ServiceValidationError, "invalid_value"),
    ],
)
async def test_errors(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    exception: Exception,
    error: type[HomeAssistantError],
    translation_key: str,
) -> None:
    """Client errors are raised as translated Home Assistant errors."""
    settings_client.bluetooth_pairing.side_effect = exception
    with pytest.raises(error) as err:
        await _press(hass, "bluetooth_pairing")
    assert type(err.value) is error
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
    assert err.value.translation_placeholders == {"error": str(exception)}


async def test_unavailable(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Buttons are unavailable while the speaker is unreachable."""
    await mock_watch.push(hass, None)
    assert _state(hass, "restart") == STATE_UNAVAILABLE
    await mock_watch.push(hass, settings_state())
    assert _state(hass, "restart") == STATE_UNKNOWN


async def test_reset_dsp_stays_without_profile(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    mock_watch: WatchController,
) -> None:
    """The reset button does not need the EQ profile once created."""
    await mock_watch.push(hass, settings_state({EQ_PATH: None}))
    await _press(hass, "reset_dsp")
    settings_client.reset_eq_profile.assert_awaited_once_with()


async def test_no_eq_profile(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """No DSP reset on a speaker without (readable) EQ profile."""
    speaker_values[EQ_PATH] = None
    await setup_integration(hass, mock_config_entry)
    assert set(entity_keys(hass, mock_config_entry)) == {
        "restart",
        "bluetooth_pairing",
        "bluetooth_disconnect",
    }


async def test_no_bluetooth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """No Bluetooth button on a speaker without Bluetooth source."""
    set_model(
        settings_client,
        SpeakerModel.LS50_WIRELESS_II,
        "4.1.192",
        sources=(Source.WIFI, Source.OPTICAL),
    )
    settings_client.get_eq_version.return_value = None
    await setup_integration(hass, mock_config_entry)
    assert set(entity_keys(hass, mock_config_entry)) == {"restart"}
