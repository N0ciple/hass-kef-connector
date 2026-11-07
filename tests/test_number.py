"""Tests of the numbers of KEF Connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_MODE,
    ATTR_STEP,
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
    NumberMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
    Platform,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import snapshot_platform

from custom_components.kef_connector.const import DOMAIN
from pykefcontrol import KefApiError, KefConnectionError, Settings, paths
from pykefcontrol.eq import DEFAULT_RANGES

from .common import (
    EQ_PATH,
    entity_id,
    entity_keys,
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

EQ_NUMBERS = [
    "treble",
    "balance",
    "desk_mode_attenuation",
    "wall_mode_attenuation",
    "subwoofer_gain",
    "subwoofer_low_pass_frequency",
    "high_pass_frequency",
]
# Ranges advertised by the LS50 Wireless II: (min, max, step).
SPEAKER_RANGES = {
    "treble": (-3, 3, 0.25),
    "balance": (-30, 30, 1),
    "desk_mode_attenuation": (-10, 0, 0.5),
    "wall_mode_attenuation": (-10, 0, 0.5),
    "subwoofer_gain": (-10, 10, 1),
    "subwoofer_low_pass_frequency": (40, 250, 2.5),
    "high_pass_frequency": (50, 120, 2.5),
}
FIELDS = {
    "treble": "treble",
    "balance": "balance",
    "desk_mode_attenuation": "desk_mode_setting",
    "wall_mode_attenuation": "wall_mode_setting",
    "subwoofer_gain": "subwoofer_gain",
    "subwoofer_low_pass_frequency": "sub_out_low_pass_freq",
    "high_pass_frequency": "high_pass_freq",
}


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the numbers only."""
    return [Platform.NUMBER]


async def _set(hass: HomeAssistant, key: str, value: float) -> None:
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id(hass, NUMBER_DOMAIN, key), ATTR_VALUE: value},
        blocking=True,
    )


def _attributes(hass: HomeAssistant, key: str) -> dict[str, Any]:
    state = hass.states.get(entity_id(hass, NUMBER_DOMAIN, key))
    assert state is not None
    return dict(state.attributes)


def _range(hass: HomeAssistant, key: str) -> tuple[float, float, float]:
    attributes = _attributes(hass, key)
    return (attributes[ATTR_MIN], attributes[ATTR_MAX], attributes[ATTR_STEP])


def _state(hass: HomeAssistant, key: str) -> str:
    state = hass.states.get(entity_id(hass, NUMBER_DOMAIN, key))
    assert state is not None
    return state.state


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Snapshot of the numbers of the LS50 Wireless II."""
    await snapshot_platform(hass, entity_registry, snapshot, init_settings.entry_id)


async def test_entity_set(hass: HomeAssistant, init_settings: MockConfigEntry) -> None:
    """LS50 Wireless II: numbers, enabled by default or not, and categories."""
    entries = entity_keys(hass, init_settings)
    assert {
        key: (entry.disabled_by is None, entry.entity_category)
        for key, entry in entries.items()
    } == {
        **dict.fromkeys(EQ_NUMBERS, (True, EntityCategory.CONFIG)),
        "maximum_volume": (True, EntityCategory.CONFIG),
        "volume_step": (False, EntityCategory.CONFIG),
    }


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_states(hass: HomeAssistant, init_settings: MockConfigEntry) -> None:
    """Values come from the EQ profile and the settings."""
    assert {key: _state(hass, key) for key in [*EQ_NUMBERS, "maximum_volume"]} == {
        "treble": "1.0",
        "balance": "0.0",
        "desk_mode_attenuation": "-3.0",
        "wall_mode_attenuation": "-2.5",
        "subwoofer_gain": "0.0",
        "subwoofer_low_pass_frequency": "45.0",
        "high_pass_frequency": "70.0",
        "maximum_volume": "70.0",
    }
    assert _state(hass, "volume_step") == "3.0"
    assert _attributes(hass, "treble")[ATTR_UNIT_OF_MEASUREMENT] == "dB"
    assert _attributes(hass, "high_pass_frequency")[ATTR_UNIT_OF_MEASUREMENT] == "Hz"
    assert _attributes(hass, "maximum_volume")[ATTR_UNIT_OF_MEASUREMENT] == "%"
    assert ATTR_UNIT_OF_MEASUREMENT not in _attributes(hass, "balance")


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_ranges_from_speaker(
    hass: HomeAssistant, init_settings: MockConfigEntry
) -> None:
    """EQ ranges come from the speaker's descriptors; settings have fixed ones."""
    assert {key: _range(hass, key) for key in EQ_NUMBERS} == SPEAKER_RANGES
    assert _range(hass, "maximum_volume") == (0, 100, 1)
    assert _range(hass, "volume_step") == (1, 10, 1)
    assert _attributes(hass, "treble")[ATTR_MODE] == NumberMode.SLIDER
    assert _attributes(hass, "volume_step")[ATTR_MODE] == NumberMode.BOX


async def test_ranges_default(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """Without descriptors, the EQ ranges are the app's defaults."""
    settings_client.get_eq_descriptors.side_effect = KefApiError(404, "Not found")
    settings_client.get_eq_ranges.return_value = dict(DEFAULT_RANGES)
    await setup_integration(hass, mock_config_entry)
    for key in EQ_NUMBERS:
        default = DEFAULT_RANGES[FIELDS[key]]
        assert _range(hass, key) == (default.minimum, default.maximum, default.step)
    assert _range(hass, "high_pass_frequency") == (50, 120, 5)


async def test_range_unknown(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """An EQ field without known range keeps the default range of numbers."""
    settings_client.get_eq_ranges.return_value = {
        k: v for k, v in DEFAULT_RANGES.items() if k != "balance"
    }
    await setup_integration(hass, mock_config_entry)
    assert _range(hass, "balance") == (0, 100, 1)


@pytest.mark.parametrize(
    ("key", "value", "changes"),
    [
        ("treble", 1.25, {"treble": 1.25}),
        ("balance", -5, {"balance": -5}),
        ("desk_mode_attenuation", -4.5, {"desk_mode_setting": -4.5}),
        ("wall_mode_attenuation", 0, {"wall_mode_setting": 0.0}),
        ("subwoofer_gain", 3, {"subwoofer_gain": 3.0}),
        ("subwoofer_low_pass_frequency", 47.5, {"sub_out_low_pass_freq": 47.5}),
        ("high_pass_frequency", 62.5, {"high_pass_freq": 62.5}),
    ],
)
async def test_eq_writes(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    key: str,
    value: float,
    changes: dict[str, Any],
) -> None:
    """EQ numbers change their field of the EQ profile, with the right type."""
    await _set(hass, key, value)
    settings_client.update_eq_profile.assert_awaited_once_with(**changes)
    sent = settings_client.update_eq_profile.await_args.kwargs
    assert {k: type(v) for k, v in sent.items()} == {
        k: type(v) for k, v in changes.items()
    }
    settings_client.set_setting.assert_not_called()


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("key", "value", "setting", "sent"),
    [
        ("maximum_volume", 60, Settings.MAXIMUM_VOLUME, 60),
        ("maximum_volume", 59.6, Settings.MAXIMUM_VOLUME, 60),
        ("volume_step", 5, Settings.VOLUME_STEP, 5),
    ],
)
async def test_setting_writes(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    key: str,
    value: float,
    setting: Any,
    sent: int,
) -> None:
    """Integer settings are written as rounded integers."""
    await _set(hass, key, value)
    settings_client.set_setting.assert_awaited_once_with(setting, sent)
    assert type(settings_client.set_setting.await_args.args[1]) is int


async def test_balance_rounded(
    hass: HomeAssistant, init_settings: MockConfigEntry, settings_client: MagicMock
) -> None:
    """The balance (integer steps) is rounded, not truncated."""
    await _set(hass, "balance", -2.7)
    settings_client.update_eq_profile.assert_awaited_once_with(balance=-3)


async def test_out_of_range(
    hass: HomeAssistant, init_settings: MockConfigEntry, settings_client: MagicMock
) -> None:
    """Values outside the speaker's range are refused by Home Assistant."""
    with pytest.raises(ServiceValidationError):
        await _set(hass, "treble", 4)
    settings_client.update_eq_profile.assert_not_called()


async def test_push_updates(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Pushed settings and EQ profile update the numbers."""
    await mock_watch.push(
        hass,
        settings_state(
            {Settings.MAXIMUM_VOLUME.path: 85},
            eq={"trebleAmount": -0.75, "subOutLPFreq": 47.5},
        ),
    )
    assert _state(hass, "maximum_volume") == "85.0"
    assert _state(hass, "treble") == "-0.75"
    assert _state(hass, "subwoofer_low_pass_frequency") == "47.5"


async def test_unknown_values(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Missing values give an unknown state (desk mode setting can be null)."""
    await mock_watch.push(
        hass,
        settings_state(
            {Settings.MAXIMUM_VOLUME.path: None}, eq={"deskModeSetting": None}
        ),
    )
    assert _state(hass, "maximum_volume") == STATE_UNKNOWN
    assert _state(hass, "desk_mode_attenuation") == STATE_UNKNOWN
    await mock_watch.push(hass, settings_state({EQ_PATH: None}))
    assert _state(hass, "treble") == STATE_UNKNOWN


async def test_unavailable(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Numbers are unavailable while the speaker is unreachable."""
    await mock_watch.push(hass, None)
    assert _state(hass, "treble") == STATE_UNAVAILABLE
    assert _state(hass, "maximum_volume") == STATE_UNAVAILABLE
    await mock_watch.push(hass, settings_state())
    assert _state(hass, "treble") == "1.0"


@pytest.mark.parametrize(
    ("exception", "error", "translation_key"),
    [
        (KefConnectionError("timeout"), HomeAssistantError, "communication_error"),
        (KefApiError(500, "Internal error"), HomeAssistantError, "command_failed"),
        (ValueError("off the grid"), ServiceValidationError, "invalid_value"),
    ],
)
@pytest.mark.parametrize(
    ("key", "value", "method"),
    [("treble", 1.1, "update_eq_profile"), ("maximum_volume", 60, "set_setting")],
)
async def test_errors(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    key: str,
    value: float,
    method: str,
    exception: Exception,
    error: type[HomeAssistantError],
    translation_key: str,
) -> None:
    """Client errors (e.g. EQ value off the speaker's grid) are translated."""
    getattr(settings_client, method).side_effect = exception
    with pytest.raises(error) as err:
        await _set(hass, key, value)
    assert type(err.value) is error
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
    assert err.value.translation_placeholders == {"error": str(exception)}


async def test_no_eq_profile(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """No EQ number on a speaker without EQ profile."""
    settings_client.get_eq_version.return_value = None
    await setup_integration(hass, mock_config_entry)
    assert set(entity_keys(hass, mock_config_entry)) == {
        "maximum_volume",
        "volume_step",
    }


async def test_eq_v1(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """EQ v1: values converted from indices, default ranges."""
    settings_client.get_eq_version.return_value = 1
    speaker_values[paths.EQ_PROFILE] = EQ_PROFILE_V1
    settings_client.get_eq_ranges.return_value = dict(DEFAULT_RANGES)
    await setup_integration(hass, mock_config_entry)
    settings_client.get_eq_descriptors.assert_not_called()
    assert set(EQ_NUMBERS) <= set(entity_keys(hass, mock_config_entry))
    assert _state(hass, "balance") == "0.0"
    assert _range(hass, "high_pass_frequency") == (50, 120, 5)


async def test_settings_not_returned(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """No number for a setting the speaker does not return."""
    del speaker_values[Settings.MAXIMUM_VOLUME.path]
    await setup_integration(hass, mock_config_entry)
    keys = entity_keys(hass, mock_config_entry)
    assert "maximum_volume" not in keys
    assert "volume_step" in keys
