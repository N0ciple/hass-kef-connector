"""Tests of the selects of KEF Connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
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
    BassExtension,
    CableMode,
    EqProfile,
    FavouriteButtonFunction,
    KefApiError,
    KefConnectionError,
    MasterChannelMode,
    Settings,
    SoundProfile,
    SpeakerModel,
    StandbyMode,
    SubwooferPreset,
    WakeUpSource,
    paths,
)
from pykefcontrol.eq import EqDescriptor

from .common import (
    EQ_DESCRIPTORS_LS50WII,
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

LS50WII_SELECTS = {
    # key: (enabled by default, entity category)
    "bass_extension": (True, EntityCategory.CONFIG),
    "subwoofer_preset": (True, EntityCategory.CONFIG),
    "standby_delay": (True, EntityCategory.CONFIG),
    "wake_up_source": (True, EntityCategory.CONFIG),
    "cable_mode": (False, EntityCategory.CONFIG),
    "master_channel": (False, EntityCategory.CONFIG),
    "favourite_button": (False, EntityCategory.CONFIG),
}
ALL_PRESETS = [
    "custom",
    "other",
    "kc62",
    "kf92",
    "kube8b",
    "kube10b",
    "kube12b",
    "kube15mie",
    "t2",
]
FAVOURITE_COMMON = [
    "next_source",
    "enable_bluetooth_pairing",
    "set_subwoofer_out",
    "set_volume",
    "set_maximum_volume",
    "set_master_channel_mode",
]


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the selects only."""
    return [Platform.SELECT]


async def _select(hass: HomeAssistant, key: str, option: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id(hass, SELECT_DOMAIN, key), ATTR_OPTION: option},
        blocking=True,
    )


def _state(hass: HomeAssistant, key: str) -> str:
    state = hass.states.get(entity_id(hass, SELECT_DOMAIN, key))
    assert state is not None
    return state.state


def _options(hass: HomeAssistant, key: str) -> list[str]:
    state = hass.states.get(entity_id(hass, SELECT_DOMAIN, key))
    assert state is not None
    return list(state.attributes[ATTR_OPTIONS])


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Snapshot of the selects of the LS50 Wireless II."""
    await snapshot_platform(hass, entity_registry, snapshot, init_settings.entry_id)


async def test_entity_set(hass: HomeAssistant, init_settings: MockConfigEntry) -> None:
    """LS50 Wireless II: selects, enabled by default or not, and categories."""
    entries = entity_keys(hass, init_settings)
    assert {
        key: (entry.disabled_by is None, entry.entity_category)
        for key, entry in entries.items()
    } == LS50WII_SELECTS


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_states_and_options(
    hass: HomeAssistant, init_settings: MockConfigEntry
) -> None:
    """Options are translation keys of the values this speaker accepts."""
    assert {key: _state(hass, key) for key in LS50WII_SELECTS} == {
        "bass_extension": "less",
        "subwoofer_preset": "kc62",
        "standby_delay": "standby_30mins",
        "wake_up_source": "optical",
        "cable_mode": "wireless",
        "master_channel": "left",
        "favourite_button": "next_source",
    }
    assert _options(hass, "bass_extension") == ["standard", "extra", "less"]
    assert _options(hass, "subwoofer_preset") == ALL_PRESETS
    assert _options(hass, "standby_delay") == [
        "standby_20mins",
        "standby_30mins",
        "standby_60mins",
        "standby_none",
    ]
    # No USB input on the LS50 Wireless II.
    assert _options(hass, "wake_up_source") == [
        "wakeup_default",
        "bluetooth",
        "tv",
        "optical",
        "coaxial",
        "analog",
    ]
    assert _options(hass, "cable_mode") == ["wired", "wireless"]
    assert _options(hass, "master_channel") == ["left", "right", "leftright"]
    # No USB input, no dialogue mode; "unknown" is never offered.
    assert sorted(_options(hass, "favourite_button")) == sorted(
        [*FAVOURITE_COMMON, "set_cable_mode", "set_disable_top_panel"]
    )


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("key", "option", "setting", "value"),
    [
        (
            "standby_delay",
            "standby_60mins",
            Settings.STANDBY_MODE,
            StandbyMode.MINUTES_60,
        ),
        ("standby_delay", "standby_none", Settings.STANDBY_MODE, StandbyMode.NEVER),
        ("wake_up_source", "tv", Settings.WAKE_UP_SOURCE, WakeUpSource.TV),
        (
            "wake_up_source",
            "wakeup_default",
            Settings.WAKE_UP_SOURCE,
            WakeUpSource.DEFAULT,
        ),
        ("cable_mode", "wired", Settings.CABLE_MODE, CableMode.WIRED),
        (
            "master_channel",
            "leftright",
            Settings.MASTER_CHANNEL_MODE,
            MasterChannelMode.LEFT_RIGHT,
        ),
        (
            "favourite_button",
            "set_disable_top_panel",
            Settings.FAVOURITE_BUTTON,
            FavouriteButtonFunction.SET_DISABLE_TOP_PANEL,
        ),
        (
            "favourite_button",
            "enable_bluetooth_pairing",
            Settings.FAVOURITE_BUTTON,
            FavouriteButtonFunction.ENABLE_BLUETOOTH_PAIRING,
        ),
    ],
)
async def test_setting_writes(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    key: str,
    option: str,
    setting: Any,
    value: Any,
) -> None:
    """Options are written as the speaker's values (camelCase included)."""
    await _select(hass, key, option)
    settings_client.set_setting.assert_awaited_once_with(setting, value)
    sent = settings_client.set_setting.await_args.args[1]
    assert type(sent) is type(value)
    settings_client.update_eq_profile.assert_not_called()


async def test_bass_extension_write(
    hass: HomeAssistant, init_settings: MockConfigEntry, settings_client: MagicMock
) -> None:
    """The bass extension is a field of the EQ profile."""
    await _select(hass, "bass_extension", "extra")
    settings_client.update_eq_profile.assert_awaited_once_with(
        bass_extension=BassExtension.EXTRA
    )


async def test_invalid_option(
    hass: HomeAssistant, init_settings: MockConfigEntry, settings_client: MagicMock
) -> None:
    """Options the speaker does not have are refused by Home Assistant."""
    with pytest.raises(ServiceValidationError):
        await _select(hass, "wake_up_source", "usb")
    settings_client.set_setting.assert_not_called()


@pytest.mark.parametrize(
    ("option", "eq", "changes"),
    [
        # No subwoofer: only the low-pass frequency of the KC62 -> KF92 changes.
        (
            "kf92",
            {},
            {
                "sub_out_low_pass_freq": 50,
                "subwoofer_preset": SubwooferPreset.KF92,
            },
        ),
        # Custom: only the preset (the subwoofer output follows the count).
        ("custom", {}, {"subwoofer_preset": SubwooferPreset.CUSTOM}),
        # One subwoofer: high-pass filter on, gain of the preset, output on.
        (
            "kube8b",
            {"subwooferCount": 1},
            {
                "high_pass_mode": True,
                "sub_out_low_pass_freq": 60,
                "subwoofer_gain": 3.0,
                "subwoofer_preset": SubwooferPreset.KUBE_8B,
                "subwoofer_out": True,
            },
        ),
    ],
)
async def test_subwoofer_preset(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    mock_watch: WatchController,
    option: str,
    eq: dict[str, Any],
    changes: dict[str, Any],
) -> None:
    """A preset sets the crossover and gain of the subwoofer like the app."""
    await mock_watch.push(hass, settings_state(eq=eq))
    await _select(hass, "subwoofer_preset", option)
    settings_client.update_eq_profile.assert_awaited_once_with(**changes)


async def test_subwoofer_preset_unknown_profile(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    mock_watch: WatchController,
) -> None:
    """The preset is applied to the speaker's profile when it is not known."""
    await mock_watch.push(hass, settings_state({EQ_PATH: None}))
    assert _state(hass, "subwoofer_preset") == STATE_UNKNOWN
    settings_client.get_eq_profile.return_value = EqProfile(
        subwoofer_count=1, sub_out_low_pass_freq=80, high_pass_freq=95
    )
    await _select(hass, "subwoofer_preset", "kc62")
    settings_client.update_eq_profile.assert_awaited_once_with(
        high_pass_mode=True,
        high_pass_freq=70,
        sub_out_low_pass_freq=45,
        subwoofer_preset=SubwooferPreset.KC62,
    )


async def test_subwoofer_preset_read_error(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    mock_watch: WatchController,
) -> None:
    """Failing to read the profile for a preset raises a translated error."""
    await mock_watch.push(hass, settings_state({EQ_PATH: None}))
    settings_client.get_eq_profile.side_effect = KefConnectionError("timeout")
    with pytest.raises(HomeAssistantError) as err:
        await _select(hass, "subwoofer_preset", "kc62")
    assert err.value.translation_key == "communication_error"
    settings_client.update_eq_profile.assert_not_called()


async def test_push_updates(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Pushed settings and EQ profile update the selects."""
    await mock_watch.push(
        hass,
        settings_state(
            {Settings.STANDBY_MODE.path: "standby_none"},
            eq={"bassExtension": "extra", "subwooferPreset": "t2"},
        ),
    )
    assert _state(hass, "standby_delay") == "standby_none"
    assert _state(hass, "bass_extension") == "extra"
    assert _state(hass, "subwoofer_preset") == "t2"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_unknown_values(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Missing values and values unknown to the integration give no option."""
    await mock_watch.push(
        hass,
        settings_state(
            {
                Settings.STANDBY_MODE.path: None,
                Settings.WAKE_UP_SOURCE.path: "hdmi",
                Settings.FAVOURITE_BUTTON.path: "unknown",
            },
            eq={"bassExtension": "massive"},
        ),
    )
    assert _state(hass, "standby_delay") == STATE_UNKNOWN
    assert _state(hass, "wake_up_source") == STATE_UNKNOWN
    assert _state(hass, "favourite_button") == STATE_UNKNOWN
    assert _state(hass, "bass_extension") == STATE_UNKNOWN
    assert _state(hass, "cable_mode") == "wireless"


async def test_unavailable(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Selects are unavailable while the speaker is unreachable."""
    await mock_watch.push(hass, None)
    assert _state(hass, "bass_extension") == STATE_UNAVAILABLE
    assert _state(hass, "standby_delay") == STATE_UNAVAILABLE
    await mock_watch.push(hass, settings_state())
    assert _state(hass, "standby_delay") == "standby_30mins"


@pytest.mark.parametrize(
    ("exception", "error", "translation_key"),
    [
        (KefConnectionError("timeout"), HomeAssistantError, "communication_error"),
        (KefApiError(500, "Internal error"), HomeAssistantError, "command_failed"),
        (ValueError("bad value"), ServiceValidationError, "invalid_value"),
    ],
)
@pytest.mark.parametrize(
    ("key", "option", "method"),
    [
        ("bass_extension", "extra", "update_eq_profile"),
        ("subwoofer_preset", "kf92", "update_eq_profile"),
        ("standby_delay", "standby_20mins", "set_setting"),
    ],
)
async def test_errors(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    settings_client: MagicMock,
    key: str,
    option: str,
    method: str,
    exception: Exception,
    error: type[HomeAssistantError],
    translation_key: str,
) -> None:
    """Client errors are raised as translated Home Assistant errors."""
    getattr(settings_client, method).side_effect = exception
    with pytest.raises(error) as err:
        await _select(hass, key, option)
    assert type(err.value) is error
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
    assert err.value.translation_placeholders == {"error": str(exception)}


async def test_choices_from_descriptors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """EQ options are restricted to the choices the speaker advertises."""
    descriptors = dict(EQ_DESCRIPTORS_LS50WII)
    descriptors["bassExtension"] = EqDescriptor(
        "bassExtension", "stringList", "standard", None, ("standard", "less", "huge")
    )
    descriptors["subwooferPreset"] = EqDescriptor(
        "subwooferPreset", "stringList", "custom", None, ()
    )
    settings_client.get_eq_descriptors.return_value = descriptors
    await setup_integration(hass, mock_config_entry)
    assert _options(hass, "bass_extension") == ["standard", "less"]
    assert _options(hass, "subwoofer_preset") == ALL_PRESETS  # no choices: all


async def test_descriptors_unreadable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """Without EQ descriptors, every known value is an option."""
    settings_client.get_eq_descriptors.side_effect = KefApiError(404, "Not found")
    await setup_integration(hass, mock_config_entry)
    assert _options(hass, "bass_extension") == ["standard", "extra", "less"]
    assert "sound_profile" not in entity_keys(hass, mock_config_entry)


async def test_sound_profile_advertised(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """A speaker advertising sound profiles gets the select (main entity)."""
    descriptors = dict(EQ_DESCRIPTORS_LS50WII)
    descriptors["soundProfile"] = EqDescriptor(
        "soundProfile", "stringList", "default", None, ("default", "night")
    )
    settings_client.get_eq_descriptors.return_value = descriptors
    await setup_integration(hass, mock_config_entry)
    entries = entity_keys(hass, mock_config_entry)
    assert entries["sound_profile"].entity_category is None
    assert _options(hass, "sound_profile") == ["default", "night"]
    assert _state(hass, "sound_profile") == "default"
    await _select(hass, "sound_profile", "night")
    settings_client.update_eq_profile.assert_awaited_once_with(
        sound_profile=SoundProfile.NIGHT
    )


async def test_no_eq_profile(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """No EQ select on a speaker without EQ profile."""
    settings_client.get_eq_version.return_value = None
    await setup_integration(hass, mock_config_entry)
    assert set(entity_keys(hass, mock_config_entry)) == {
        "standby_delay",
        "wake_up_source",
        "cable_mode",
        "master_channel",
        "favourite_button",
    }


async def test_eq_v1(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """EQ v1: bass extension and preset, no sound profile (v2 field)."""
    settings_client.get_eq_version.return_value = 1
    speaker_values[paths.EQ_PROFILE] = EQ_PROFILE_V1
    await setup_integration(hass, mock_config_entry)
    keys = entity_keys(hass, mock_config_entry)
    assert {"bass_extension", "subwoofer_preset"} <= set(keys)
    assert "sound_profile" not in keys
    assert _state(hass, "bass_extension") == "standard"


async def test_settings_not_returned(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """No select for a setting the speaker does not return."""
    del speaker_values[Settings.MASTER_CHANNEL_MODE.path]
    del speaker_values[Settings.STANDBY_MODE.path]
    await setup_integration(hass, mock_config_entry)
    keys = entity_keys(hass, mock_config_entry)
    assert "master_channel" not in keys
    assert "standby_delay" not in keys
    assert "wake_up_source" in keys


async def test_feature_not_supported(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """Firmware before the advanced remote control: no favourite button."""
    set_model(settings_client, SpeakerModel.LS50_WIRELESS_II, "3.4.0")
    await setup_integration(hass, mock_config_entry)
    assert "favourite_button" not in entity_keys(hass, mock_config_entry)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_xio(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """XIO: sound profile; no cable mode; favourite dialogue mode."""
    set_model(settings_client, SpeakerModel.XIO, "1.5.152")
    await setup_integration(hass, mock_config_entry)
    keys = entity_keys(hass, mock_config_entry)
    assert "sound_profile" in keys  # even without its descriptor
    assert "cable_mode" not in keys
    assert _options(hass, "sound_profile") == [
        "default",
        "music",
        "movie",
        "night",
        "dialogue",
        "direct",
    ]
    assert _options(hass, "wake_up_source") == [
        "wakeup_default",
        "bluetooth",
        "tv",
        "optical",
    ]
    assert sorted(_options(hass, "favourite_button")) == sorted(
        [*FAVOURITE_COMMON, "set_dialogue_mode", "set_disable_top_panel"]
    )


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_lsx_ii(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """LSX II: USB as wake-up source and favourite function; no top panel."""
    set_model(settings_client, SpeakerModel.LSX_II, "3.0.139")
    await setup_integration(hass, mock_config_entry)
    assert "usb" in _options(hass, "wake_up_source")
    assert "coaxial" not in _options(hass, "wake_up_source")
    assert sorted(_options(hass, "favourite_button")) == sorted(
        [*FAVOURITE_COMMON, "set_cable_mode", "set_usb_source"]
    )
    await _select(hass, "favourite_button", "set_usb_source")
    settings_client.set_setting.assert_awaited_once_with(
        Settings.FAVOURITE_BUTTON, FavouriteButtonFunction.SET_USB_SOURCE
    )
