"""Tests of the switches of KEF Connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
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
    Settings,
    Source,
    SpeakerModel,
    paths,
)

from .common import (
    EQ_PATH,
    entity_id,
    entity_keys,
    set_model,
    settings_state,
    setup_integration,
)
from .const import EQ_PROFILE_V1

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from syrupy.assertion import SnapshotAssertion

    from .common import WatchController

LS50WII_SWITCHES = {
    # key: (enabled by default, entity category)
    "desk_mode": (True, EntityCategory.CONFIG),
    "wall_mode": (True, EntityCategory.CONFIG),
    "phase_correction": (True, EntityCategory.CONFIG),
    "high_pass_filter": (True, EntityCategory.CONFIG),
    "subwoofer_output": (True, EntityCategory.CONFIG),
    "startup_tone": (True, EntityCategory.CONFIG),
    "front_led": (True, EntityCategory.CONFIG),
    "top_panel_lock": (True, EntityCategory.CONFIG),
    "auto_switch_tv": (True, EntityCategory.CONFIG),
    "volume_limit": (True, EntityCategory.CONFIG),
    "subwoofer_always_on": (False, EntityCategory.CONFIG),
    "dialogue_mode": (False, None),  # reported, effect on stereo speakers unknown
}


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the switches only."""
    return [Platform.SWITCH]


async def _call(hass: HomeAssistant, service: str, key: str) -> None:
    await hass.services.async_call(
        SWITCH_DOMAIN,
        service,
        {ATTR_ENTITY_ID: entity_id(hass, SWITCH_DOMAIN, key)},
        blocking=True,
    )


def _state(hass: HomeAssistant, key: str) -> str:
    state = hass.states.get(entity_id(hass, SWITCH_DOMAIN, key))
    assert state is not None
    return state.state


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Snapshot of the switches of the LS50 Wireless II."""
    await snapshot_platform(hass, entity_registry, snapshot, init_settings.entry_id)


async def test_entity_set(hass: HomeAssistant, init_settings: MockConfigEntry) -> None:
    """LS50 Wireless II: switches, enabled by default or not, and categories."""
    entries = entity_keys(hass, init_settings)
    assert {
        key: (entry.disabled_by is None, entry.entity_category)
        for key, entry in entries.items()
    } == LS50WII_SWITCHES


async def test_states(hass: HomeAssistant, init_settings: MockConfigEntry) -> None:
    """States come from the EQ profile and the settings (some inverted)."""
    enabled = [key for key, (default, _) in LS50WII_SWITCHES.items() if default]
    assert {key: _state(hass, key) for key in enabled} == {
        "desk_mode": STATE_OFF,
        "wall_mode": STATE_ON,
        "phase_correction": STATE_ON,
        "high_pass_filter": STATE_OFF,
        "subwoofer_output": STATE_OFF,
        "startup_tone": STATE_ON,
        "front_led": STATE_ON,  # disableFrontLED False
        "top_panel_lock": STATE_OFF,
        "auto_switch_tv": STATE_ON,
        "volume_limit": STATE_ON,
    }


@pytest.mark.parametrize(
    ("key", "field"),
    [
        ("desk_mode", "desk_mode"),
        ("wall_mode", "wall_mode"),
        ("phase_correction", "phase_correction"),
        ("high_pass_filter", "high_pass_mode"),
        ("subwoofer_output", "subwoofer_out"),
    ],
)
async def test_eq_writes(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    key: str,
    field: str,
) -> None:
    """EQ switches change their field of the EQ profile."""
    await _call(hass, SERVICE_TURN_ON, key)
    settings_client.update_eq_profile.assert_awaited_once_with(**{field: True})
    settings_client.update_eq_profile.reset_mock()
    await _call(hass, SERVICE_TURN_OFF, key)
    settings_client.update_eq_profile.assert_awaited_once_with(**{field: False})
    settings_client.set_setting.assert_not_called()


@pytest.mark.parametrize(
    ("key", "setting", "on_value"),
    [
        ("startup_tone", Settings.STARTUP_TONE, True),
        ("front_led", Settings.DISABLE_FRONT_LED, False),
        ("top_panel_lock", Settings.DISABLE_TOP_PANEL, True),
        ("auto_switch_tv", Settings.AUTO_SWITCH_TO_TV, True),
        ("volume_limit", Settings.VOLUME_LIMIT, True),
    ],
)
async def test_setting_writes(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    key: str,
    setting: Any,
    on_value: bool,
) -> None:
    """Setting switches write their setting ("disable" settings inverted)."""
    await _call(hass, SERVICE_TURN_ON, key)
    settings_client.set_setting.assert_awaited_once_with(setting, on_value)
    settings_client.set_setting.reset_mock()
    await _call(hass, SERVICE_TURN_OFF, key)
    settings_client.set_setting.assert_awaited_once_with(setting, not on_value)
    settings_client.update_eq_profile.assert_not_called()


async def test_push_updates(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Pushed settings and EQ profile update the switches."""
    await mock_watch.push(
        hass,
        settings_state(
            {Settings.DISABLE_FRONT_LED.path: True, Settings.STARTUP_TONE.path: False},
            eq={"deskMode": True, "wallMode": False},
        ),
    )
    assert _state(hass, "front_led") == STATE_OFF
    assert _state(hass, "startup_tone") == STATE_OFF
    assert _state(hass, "desk_mode") == STATE_ON
    assert _state(hass, "wall_mode") == STATE_OFF


async def test_unknown_values(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """A setting or EQ profile the speaker stops returning gives an unknown state."""
    await mock_watch.push(
        hass, settings_state({Settings.DISABLE_FRONT_LED.path: None, EQ_PATH: None})
    )
    assert _state(hass, "front_led") == STATE_UNKNOWN
    assert _state(hass, "desk_mode") == STATE_UNKNOWN
    assert _state(hass, "volume_limit") == STATE_ON


async def test_unavailable(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Switches are unavailable while the speaker is unreachable."""
    await mock_watch.push(hass, None)
    assert _state(hass, "desk_mode") == STATE_UNAVAILABLE
    assert _state(hass, "front_led") == STATE_UNAVAILABLE
    await mock_watch.push(hass, settings_state())
    assert _state(hass, "front_led") == STATE_ON


@pytest.mark.parametrize(
    ("exception", "error", "translation_key"),
    [
        (KefConnectionError("timeout"), HomeAssistantError, "communication_error"),
        (KefApiError(500, "Internal error"), HomeAssistantError, "command_failed"),
        (ValueError("bad value"), ServiceValidationError, "invalid_value"),
    ],
)
@pytest.mark.parametrize(
    ("key", "method"),
    [("wall_mode", "update_eq_profile"), ("front_led", "set_setting")],
)
async def test_errors(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    key: str,
    method: str,
    exception: Exception,
    error: type[HomeAssistantError],
    translation_key: str,
) -> None:
    """Client errors are raised as translated Home Assistant errors."""
    getattr(settings_client, method).side_effect = exception
    with pytest.raises(error) as err:
        await _call(hass, SERVICE_TURN_ON, key)
    assert type(err.value) is error
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
    assert err.value.translation_placeholders == {"error": str(exception)}


async def test_setting_not_returned(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """No switch for a supported setting the speaker does not return."""
    del speaker_values[Settings.STARTUP_TONE.path]
    speaker_values[Settings.VOLUME_LIMIT.path] = "garbage"  # returned, not decodable
    await setup_integration(hass, mock_config_entry)
    keys = entity_keys(hass, mock_config_entry)
    assert "startup_tone" not in keys
    assert "front_led" in keys
    assert _state(hass, "volume_limit") == STATE_UNKNOWN


async def test_feature_not_supported(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """Old firmware: no switch for the settings it does not have."""
    set_model(settings_client, SpeakerModel.LS50_WIRELESS_II, "2.0.0")
    await setup_integration(hass, mock_config_entry)
    keys = entity_keys(hass, mock_config_entry)
    assert "auto_switch_tv" not in keys  # 3.0.100
    assert "subwoofer_always_on" not in keys  # 2.4.70
    assert "front_led" in keys
    followed = settings_client.watch_controller.calls[0]
    assert Settings.AUTO_SWITCH_TO_TV.path not in followed


async def test_auto_switch_tv_needs_tv_source(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """No "auto switch to TV" on a speaker without TV input."""
    set_model(
        settings_client,
        SpeakerModel.LS50_WIRELESS_II,
        "4.1.192",
        sources=(Source.WIFI, Source.BLUETOOTH, Source.OPTICAL),
    )
    await setup_integration(hass, mock_config_entry)
    assert "auto_switch_tv" not in entity_keys(hass, mock_config_entry)


async def test_no_eq_profile(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """No EQ switch on a speaker without EQ profile."""
    settings_client.get_eq_version.return_value = None
    await setup_integration(hass, mock_config_entry)
    assert set(entity_keys(hass, mock_config_entry)) == {
        "startup_tone",
        "front_led",
        "top_panel_lock",
        "auto_switch_tv",
        "volume_limit",
        "subwoofer_always_on",
        "dialogue_mode",
    }


async def test_eq_profile_unreadable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """No EQ switch if the EQ profile could not be read at setup."""
    speaker_values[EQ_PATH] = None
    await setup_integration(hass, mock_config_entry)
    assert "desk_mode" not in entity_keys(hass, mock_config_entry)


async def test_eq_v1(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """EQ v1 (old firmware): no subwoofer output switch (v2 field)."""
    settings_client.get_eq_version.return_value = 1
    speaker_values[paths.EQ_PROFILE] = EQ_PROFILE_V1
    await setup_integration(hass, mock_config_entry)
    keys = entity_keys(hass, mock_config_entry)
    assert "subwoofer_output" not in keys
    assert "desk_mode" in keys
    assert _state(hass, "phase_correction") == STATE_ON


async def test_xio(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """XIO: dialogue mode (main entity, enabled) and top panel LEDs; no front LED."""
    set_model(settings_client, SpeakerModel.XIO, "1.5.152")
    speaker_values[Settings.DIALOGUE_MODE.path] = True
    await setup_integration(hass, mock_config_entry)
    entries = entity_keys(hass, mock_config_entry)
    assert {"dialogue_mode", "top_panel_led", "top_panel_standby_led"} <= set(entries)
    assert "front_standby_led" not in entries
    assert "usb_charging" not in entries
    assert entries["dialogue_mode"].entity_category is None
    assert entries["dialogue_mode"].disabled_by is None
    assert entries["top_panel_led"].disabled_by is not None
    assert _state(hass, "dialogue_mode") == STATE_ON

    await _call(hass, SERVICE_TURN_OFF, "dialogue_mode")
    settings_client.set_setting.assert_awaited_once_with(Settings.DIALOGUE_MODE, False)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_lsx_ii(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """LSX II: USB charging and front standby LED (inverted); no top panel."""
    set_model(settings_client, SpeakerModel.LSX_II, "3.0.139")
    await setup_integration(hass, mock_config_entry)
    keys = entity_keys(hass, mock_config_entry)
    assert {"usb_charging", "front_standby_led"} <= set(keys)
    assert not {"top_panel_lock", "top_panel_led"} & set(keys)
    assert _state(hass, "front_standby_led") == STATE_OFF  # disabled: True
    assert _state(hass, "usb_charging") == STATE_OFF

    await _call(hass, SERVICE_TURN_ON, "front_standby_led")
    settings_client.set_setting.assert_awaited_once_with(
        Settings.DISABLE_FRONT_STANDBY_LED, False
    )


async def test_dialogue_mode_not_reported(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """No dialogue mode switch on a speaker that does not report the setting."""
    del speaker_values[Settings.DIALOGUE_MODE.path]
    await setup_integration(hass, mock_config_entry)
    assert "dialogue_mode" not in entity_keys(hass, mock_config_entry)
