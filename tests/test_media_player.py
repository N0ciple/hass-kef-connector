"""Tests of the media player of KEF Connector."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    ATTR_MEDIA_ALBUM_ARTIST,
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_DURATION,
    ATTR_MEDIA_EXTRA,
    ATTR_MEDIA_POSITION,
    ATTR_MEDIA_POSITION_UPDATED_AT,
    ATTR_MEDIA_REPEAT,
    ATTR_MEDIA_SEEK_POSITION,
    ATTR_MEDIA_SHUFFLE,
    ATTR_MEDIA_TITLE,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    DOMAIN as MP_DOMAIN,
    SERVICE_PLAY_MEDIA,
    SERVICE_SELECT_SOURCE,
    BrowseMedia,
    MediaClass,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.components.media_source import PlayMedia
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    CONF_HOST,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PLAY_PAUSE,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_MEDIA_SEEK,
    SERVICE_MEDIA_STOP,
    SERVICE_REPEAT_SET,
    SERVICE_SHUFFLE_SET,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_DOWN,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
    STATE_UNAVAILABLE,
    Platform,
)
from homeassistant.core_config import async_process_ha_core_config
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)

from custom_components.kef_connector.const import (
    CONF_MAX_VOLUME,
    CONF_VOLUME_STEP,
    DOMAIN,
)
from custom_components.kef_connector.coordinator import WATCH_RESTART_DELAY
from pykefcontrol import (
    KefApiError,
    KefConnectionError,
    PlaybackState,
    PlayerState,
    PlayMode,
    Source,
    SpeakerStatus,
)

from .common import WatchController, player_state, setup_integration, speaker_state
from .const import ENTITY_ID, HOST, NAME, PLAYER_DATA, POSITION_UPDATED_AT, UNIQUE_ID

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.typing import WebSocketGenerator
    from syrupy.assertion import SnapshotAssertion

BASE_FEATURES = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.BROWSE_MEDIA
)
TRANSPORT_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
)
ALL_FEATURES = (
    BASE_FEATURES
    | TRANSPORT_FEATURES
    | MediaPlayerEntityFeature.SEEK
    | MediaPlayerEntityFeature.SHUFFLE_SET
    | MediaPlayerEntityFeature.REPEAT_SET
)
SHUFFLE, SHUFFLE_ATTR = SERVICE_SHUFFLE_SET, ATTR_MEDIA_SHUFFLE
REPEAT, REPEAT_ATTR = SERVICE_REPEAT_SET, ATTR_MEDIA_REPEAT


async def _call(hass: HomeAssistant, service: str, **data: Any) -> None:
    await hass.services.async_call(
        MP_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID, **data}, blocking=True
    )


@pytest.fixture
async def limited_entry(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> MockConfigEntry:
    """Speaker with a maximum volume of 50 % and a volume step of 5 %."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        unique_id=UNIQUE_ID,
        data={CONF_HOST: HOST},
        options={CONF_MAX_VOLUME: 50, CONF_VOLUME_STEP: 5},
    )
    await setup_integration(hass, entry)
    return entry


async def test_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Snapshot of the media player while Spotify plays."""
    with patch(
        "homeassistant.components.media_player.secrets.token_hex",
        return_value="mock_token",
    ):
        await setup_integration(hass, mock_config_entry)
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_attributes(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Attributes of the media player while Spotify plays."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == MediaPlayerState.PLAYING
    attributes = state.attributes
    assert attributes[ATTR_MEDIA_VOLUME_LEVEL] == 0.35
    assert attributes[ATTR_MEDIA_VOLUME_MUTED] is False
    assert attributes[ATTR_INPUT_SOURCE] == "wifi"
    assert attributes[ATTR_INPUT_SOURCE_LIST] == [
        "wifi",
        "bluetooth",
        "tv",
        "optical",
        "coaxial",
        "analog",
    ]
    assert attributes[ATTR_MEDIA_TITLE] == "So What"
    assert attributes[ATTR_MEDIA_ARTIST] == "Miles Davis"
    assert attributes[ATTR_MEDIA_ALBUM_NAME] == "Kind of Blue"
    assert attributes[ATTR_MEDIA_ALBUM_ARTIST] == "Miles Davis"
    assert attributes[ATTR_MEDIA_DURATION] == 562
    assert attributes[ATTR_MEDIA_POSITION] == 61
    assert attributes[ATTR_MEDIA_POSITION_UPDATED_AT] == POSITION_UPDATED_AT
    assert attributes[ATTR_MEDIA_SHUFFLE] is False
    assert attributes[ATTR_MEDIA_REPEAT] == RepeatMode.OFF
    assert attributes[ATTR_SUPPORTED_FEATURES] == ALL_FEATURES
    assert attributes["entity_picture"].startswith(
        f"/api/media_player_proxy/{ENTITY_ID}?token="
    )
    assert attributes["device_class"] == "speaker"


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"status": SpeakerStatus.STANDBY, "source": Source.STANDBY}, "off"),
        ({"source": Source.STANDBY}, "off"),
        ({"status": SpeakerStatus.STANDBY}, "off"),
        ({}, "playing"),
        ({"player": player_state(state="paused")}, "paused"),
        ({"player": player_state(state="stopped")}, "idle"),
        ({"player": player_state(state="transitioning")}, "buffering"),
        ({"player": player_state(state="loading")}, "idle"),  # unknown state
        ({"player": None}, "idle"),
        ({"source": Source.BLUETOOTH}, "playing"),
        (
            {"source": Source.BLUETOOTH, "player": player_state(state="paused")},
            "paused",
        ),
        ({"source": Source.TV}, "on"),
        ({"source": Source.OPTICAL}, "on"),
        ({"source": Source.COAXIAL}, "on"),
        ({"source": Source.ANALOG}, "on"),
        ({"status": SpeakerStatus.POWER_ON, "source": None}, "on"),
    ],
)
async def test_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
    changes: dict[str, Any],
    expected: str,
) -> None:
    """Speaker status, source and player state give the media player state."""
    await mock_watch.push(hass, speaker_state(**changes))
    assert hass.states.get(ENTITY_ID).state == expected


async def test_standby_attributes(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
) -> None:
    """In standby the media player is off, with no media information."""
    await mock_watch.push(
        hass,
        speaker_state(status=SpeakerStatus.STANDBY, source=Source.STANDBY),
    )
    state = hass.states.get(ENTITY_ID)
    assert state.state == MediaPlayerState.OFF
    for attribute in (
        ATTR_INPUT_SOURCE,
        ATTR_MEDIA_TITLE,
        ATTR_MEDIA_ARTIST,
        ATTR_MEDIA_DURATION,
        ATTR_MEDIA_POSITION,
        ATTR_MEDIA_VOLUME_LEVEL,  # HA hides the volume of a player that is off
        "entity_picture",
    ):
        assert attribute not in state.attributes
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == BASE_FEATURES


async def test_physical_input_attributes(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
) -> None:
    """On a physical input there is no transport control nor position."""
    await mock_watch.push(hass, speaker_state(source=Source.TV))
    state = hass.states.get(ENTITY_ID)
    assert state.state == MediaPlayerState.ON
    assert state.attributes[ATTR_INPUT_SOURCE] == "tv"
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == BASE_FEATURES
    assert ATTR_MEDIA_DURATION not in state.attributes
    assert ATTR_MEDIA_POSITION not in state.attributes
    assert ATTR_MEDIA_POSITION_UPDATED_AT not in state.attributes
    # The player still holds the last track: it is shown.
    assert state.attributes[ATTR_MEDIA_TITLE] == "So What"


async def test_unknown_values(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
) -> None:
    """Unknown values are not shown."""
    await mock_watch.push(
        hass,
        speaker_state(
            volume=None,
            muted=None,
            play_mode=None,
            position_ms=-1,
            player=player_state(trackRoles={"title": "Radio"}, mediaRoles=None),
        ),
    )
    attributes = hass.states.get(ENTITY_ID).attributes
    for attribute in (
        ATTR_MEDIA_VOLUME_LEVEL,
        ATTR_MEDIA_VOLUME_MUTED,
        ATTR_MEDIA_SHUFFLE,
        ATTR_MEDIA_REPEAT,
        ATTR_MEDIA_POSITION,
        ATTR_MEDIA_POSITION_UPDATED_AT,
        ATTR_MEDIA_ARTIST,
        "entity_picture",
    ):
        assert attribute not in attributes
    assert attributes[ATTR_MEDIA_TITLE] == "Radio"
    # Duration from the player status.
    assert attributes[ATTR_MEDIA_DURATION] == 562

    await mock_watch.push(
        hass, speaker_state(player=PlayerState(state=PlaybackState.PLAYING))
    )
    attributes = hass.states.get(ENTITY_ID).attributes
    assert ATTR_MEDIA_TITLE not in attributes
    assert ATTR_MEDIA_DURATION not in attributes


@pytest.mark.parametrize(
    ("play_mode", "shuffle", "repeat"),
    [
        (PlayMode.NORMAL, False, RepeatMode.OFF),
        (PlayMode.REPEAT_ONE, False, RepeatMode.ONE),
        (PlayMode.REPEAT_ALL, False, RepeatMode.ALL),
        (PlayMode.SHUFFLE, True, RepeatMode.OFF),
        (PlayMode.SHUFFLE_REPEAT_ONE, True, RepeatMode.ONE),
        (PlayMode.SHUFFLE_REPEAT_ALL, True, RepeatMode.ALL),
    ],
)
async def test_play_mode_attributes(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
    play_mode: PlayMode,
    shuffle: bool,
    repeat: RepeatMode,
) -> None:
    """The play mode gives the shuffle and repeat attributes."""
    await mock_watch.push(hass, speaker_state(play_mode=play_mode))
    attributes = hass.states.get(ENTITY_ID).attributes
    assert attributes[ATTR_MEDIA_SHUFFLE] is shuffle
    assert attributes[ATTR_MEDIA_REPEAT] == repeat


@pytest.mark.parametrize(
    ("controls", "expected"),
    [
        (PLAYER_DATA["controls"], ALL_FEATURES),
        (
            {"pause": False, "next_": False, "previous": False, "seekTime": False},
            BASE_FEATURES | MediaPlayerEntityFeature.STOP,
        ),
        (
            {"pause": True, "playMode": {"shuffle": True, "normal": True}},
            BASE_FEATURES
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.SHUFFLE_SET,
        ),
        (
            {"next": True, "playMode": {"repeatAll": True, "normal": True}},
            BASE_FEATURES
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.REPEAT_SET,
        ),
        (None, BASE_FEATURES | TRANSPORT_FEATURES),  # controls not sent
    ],
)
async def test_supported_features(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
    controls: dict[str, Any] | None,
    expected: MediaPlayerEntityFeature,
) -> None:
    """Transport features follow the controls allowed by the player."""
    data = {k: v for k, v in PLAYER_DATA.items() if k != "controls"}
    if controls is not None:
        data["controls"] = controls
    await mock_watch.push(hass, speaker_state(player=PlayerState.from_api(data)))
    assert hass.states.get(ENTITY_ID).attributes[ATTR_SUPPORTED_FEATURES] == expected


async def test_supported_features_without_player(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
) -> None:
    """Default transport features when the player state is unknown."""
    await mock_watch.push(hass, speaker_state(player=None))
    assert (
        hass.states.get(ENTITY_ID).attributes[ATTR_SUPPORTED_FEATURES]
        == BASE_FEATURES | TRANSPORT_FEATURES
    )


@pytest.mark.parametrize(
    ("service", "data", "method", "args"),
    [
        (SERVICE_TURN_ON, {}, "power_on", ()),
        (SERVICE_TURN_OFF, {}, "power_off", ()),
        (SERVICE_VOLUME_SET, {ATTR_MEDIA_VOLUME_LEVEL: 0.42}, "set_volume", (42,)),
        (SERVICE_VOLUME_MUTE, {ATTR_MEDIA_VOLUME_MUTED: True}, "set_mute", (True,)),
        (SERVICE_VOLUME_MUTE, {ATTR_MEDIA_VOLUME_MUTED: False}, "set_mute", (False,)),
        (
            SERVICE_SELECT_SOURCE,
            {ATTR_INPUT_SOURCE: "optical"},
            "set_source",
            ("optical",),
        ),
        (SERVICE_MEDIA_PLAY, {}, "play", ()),
        (SERVICE_MEDIA_PAUSE, {}, "pause", ()),
        (SERVICE_MEDIA_PLAY_PAUSE, {}, "play_pause", ()),
        (SERVICE_MEDIA_STOP, {}, "stop", ()),
        (SERVICE_MEDIA_NEXT_TRACK, {}, "next_track", ()),
        (SERVICE_MEDIA_PREVIOUS_TRACK, {}, "previous_track", ()),
        (SERVICE_MEDIA_SEEK, {ATTR_MEDIA_SEEK_POSITION: 92.5}, "seek", (92500,)),
        (
            SERVICE_SHUFFLE_SET,
            {ATTR_MEDIA_SHUFFLE: True},
            "set_play_mode",
            (PlayMode.SHUFFLE,),
        ),
        (
            SERVICE_REPEAT_SET,
            {ATTR_MEDIA_REPEAT: RepeatMode.ALL},
            "set_play_mode",
            (PlayMode.REPEAT_ALL,),
        ),
        (SERVICE_VOLUME_UP, {}, "set_volume", (38,)),
        (SERVICE_VOLUME_DOWN, {}, "set_volume", (32,)),
    ],
)
async def test_services(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client: MagicMock,
    service: str,
    data: dict[str, Any],
    method: str,
    args: tuple[Any, ...],
) -> None:
    """Each action calls the matching client method."""
    await _call(hass, service, **data)
    getattr(mock_kef_client, method).assert_awaited_once_with(*args)


@pytest.mark.parametrize(
    ("play_mode", "service", "data", "expected"),
    [
        (
            PlayMode.REPEAT_ALL,
            SHUFFLE,
            {SHUFFLE_ATTR: True},
            PlayMode.SHUFFLE_REPEAT_ALL,
        ),
        (
            PlayMode.SHUFFLE_REPEAT_ONE,
            SHUFFLE,
            {SHUFFLE_ATTR: False},
            PlayMode.REPEAT_ONE,
        ),
        (None, SHUFFLE, {SHUFFLE_ATTR: True}, PlayMode.SHUFFLE),
        (
            PlayMode.SHUFFLE,
            REPEAT,
            {REPEAT_ATTR: RepeatMode.ONE},
            PlayMode.SHUFFLE_REPEAT_ONE,
        ),
        (
            PlayMode.SHUFFLE_REPEAT_ALL,
            REPEAT,
            {REPEAT_ATTR: RepeatMode.OFF},
            PlayMode.SHUFFLE,
        ),
        (None, REPEAT, {REPEAT_ATTR: RepeatMode.ALL}, PlayMode.REPEAT_ALL),
    ],
)
async def test_play_mode_services(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client: MagicMock,
    mock_watch: WatchController,
    play_mode: PlayMode | None,
    service: str,
    data: dict[str, Any],
    expected: PlayMode,
) -> None:
    """Shuffle and repeat are changed independently."""
    await mock_watch.push(hass, speaker_state(play_mode=play_mode))
    await _call(hass, service, **data)
    mock_kef_client.set_play_mode.assert_awaited_once_with(expected)


@pytest.mark.parametrize(
    ("volume_level", "expected"),
    [(0.3, 30), (0.5, 50), (0.8, 50), (1.0, 50), (0.0, 0)],
)
async def test_volume_set_capped(
    hass: HomeAssistant,
    limited_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    volume_level: float,
    expected: int,
) -> None:
    """The volume set from Home Assistant never exceeds the maximum volume."""
    await _call(hass, SERVICE_VOLUME_SET, **{ATTR_MEDIA_VOLUME_LEVEL: volume_level})
    mock_kef_client.set_volume.assert_awaited_once_with(expected)


@pytest.mark.parametrize(
    ("volume", "service", "expected"),
    [
        (30, SERVICE_VOLUME_UP, 35),
        (47, SERVICE_VOLUME_UP, 50),  # capped
        (50, SERVICE_VOLUME_UP, 50),
        (60, SERVICE_VOLUME_UP, 60),  # above the cap (remote): not lowered
        (30, SERVICE_VOLUME_DOWN, 25),
        (60, SERVICE_VOLUME_DOWN, 55),
        (3, SERVICE_VOLUME_DOWN, 0),
    ],
)
async def test_volume_step(
    hass: HomeAssistant,
    limited_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    mock_watch: WatchController,
    volume: int,
    service: str,
    expected: int,
) -> None:
    """Volume up and down use the volume step option, up to the maximum volume."""
    await mock_watch.push(hass, speaker_state(volume=volume))
    await _call(hass, service)
    mock_kef_client.set_volume.assert_awaited_once_with(expected)


async def test_volume_step_unknown_volume(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client: MagicMock,
    mock_watch: WatchController,
) -> None:
    """The volume is read when it is not known."""
    await mock_watch.push(hass, speaker_state(volume=None))
    mock_kef_client.get_volume.return_value = 99
    await _call(hass, SERVICE_VOLUME_UP)
    mock_kef_client.get_volume.assert_awaited_once()
    mock_kef_client.set_volume.assert_awaited_once_with(100)


async def test_select_unknown_source(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> None:
    """Sources not supported by the speaker are refused."""
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_SELECT_SOURCE, **{ATTR_INPUT_SOURCE: "usb"})
    assert err.value.translation_key == "invalid_source"
    assert err.value.translation_placeholders == {"source": "usb"}
    mock_kef_client.set_source.assert_not_called()


@pytest.mark.parametrize(
    ("exception", "error", "translation_key"),
    [
        (KefConnectionError("timeout"), HomeAssistantError, "communication_error"),
        (KefApiError(500, "Internal error"), HomeAssistantError, "command_failed"),
        (ValueError("bad volume"), ServiceValidationError, "invalid_value"),
    ],
)
@pytest.mark.parametrize(
    ("service", "data", "method"),
    [
        (SERVICE_TURN_ON, {}, "power_on"),
        (SERVICE_VOLUME_SET, {ATTR_MEDIA_VOLUME_LEVEL: 0.2}, "set_volume"),
        (SERVICE_VOLUME_UP, {}, "set_volume"),
        (SERVICE_MEDIA_PAUSE, {}, "pause"),
        (
            SERVICE_PLAY_MEDIA,
            {
                ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
                ATTR_MEDIA_CONTENT_ID: "http://radio.example/stream.mp3",
            },
            "play_url",
        ),
    ],
)
async def test_service_errors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client: MagicMock,
    service: str,
    data: dict[str, Any],
    method: str,
    exception: Exception,
    error: type[HomeAssistantError],
    translation_key: str,
) -> None:
    """Client errors are raised as translated Home Assistant errors."""
    getattr(mock_kef_client, method).side_effect = exception
    with pytest.raises(error) as err:
        await _call(hass, service, **data)
    assert type(err.value) is error
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
    assert err.value.translation_placeholders == {"error": str(exception)}


@pytest.mark.parametrize(
    ("media_type", "extra", "title", "mime_type"),
    [
        (MediaType.MUSIC, {}, None, "audio/unknown"),
        (MediaType.URL, {"title": "FIP"}, "FIP", "audio/unknown"),
        ("audio/mpeg", {"title": "FIP"}, "FIP", "audio/unknown"),
    ],
)
async def test_play_media_url(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client: MagicMock,
    media_type: str,
    extra: dict[str, Any],
    title: str | None,
    mime_type: str,
) -> None:
    """Audio URLs are played as custom radios."""
    url = "https://icecast.radiofrance.fr/fip-hifi.aac"
    await _call(
        hass,
        SERVICE_PLAY_MEDIA,
        **{
            ATTR_MEDIA_CONTENT_TYPE: media_type,
            ATTR_MEDIA_CONTENT_ID: url,
            ATTR_MEDIA_EXTRA: extra,
        },
    )
    mock_kef_client.play_url.assert_awaited_once_with(
        url, title=title, mime_type=mime_type
    )


async def test_play_media_unsupported_type(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> None:
    """Only audio can be played."""
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            SERVICE_PLAY_MEDIA,
            **{
                ATTR_MEDIA_CONTENT_TYPE: MediaType.VIDEO,
                ATTR_MEDIA_CONTENT_ID: "https://example.com/movie.mp4",
            },
        )
    assert err.value.translation_key == "unsupported_media_type"
    assert err.value.translation_placeholders == {"media_type": "video"}
    mock_kef_client.play_url.assert_not_called()


async def test_play_media_source(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> None:
    """Media source items are resolved to a URL reachable by the speaker."""
    await async_process_ha_core_config(
        hass, {"internal_url": "http://192.168.1.10:8123"}
    )
    media_id = "media-source://tts/cloud?message=Hello"
    with patch(
        "homeassistant.components.media_source.async_resolve_media",
        return_value=PlayMedia(url="/api/tts_proxy/abc123.mp3", mime_type="audio/mpeg"),
    ) as mock_resolve:
        await _call(
            hass,
            SERVICE_PLAY_MEDIA,
            **{
                ATTR_MEDIA_CONTENT_TYPE: "provider",
                ATTR_MEDIA_CONTENT_ID: media_id,
            },
        )
    mock_resolve.assert_awaited_once_with(hass, media_id, ENTITY_ID)
    mock_kef_client.play_url.assert_awaited_once_with(
        "http://192.168.1.10:8123/api/tts_proxy/abc123.mp3",
        title=None,
        mime_type="audio/mpeg",
    )


async def test_browse_media(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Media sources are browsed, keeping audio items only."""
    root = BrowseMedia(
        title="Media",
        media_class=MediaClass.DIRECTORY,
        media_content_id="media-source://media_source",
        media_content_type="",
        can_play=False,
        can_expand=True,
        children=[],
    )
    with patch(
        "homeassistant.components.media_source.async_browse_media",
        AsyncMock(return_value=root),
    ) as mock_browse:
        client = await hass_ws_client(hass)
        await client.send_json_auto_id(
            {
                "type": "media_player/browse_media",
                "entity_id": ENTITY_ID,
                "media_content_id": "media-source://media_source/local/.",
                "media_content_type": "",
            }
        )
        response = await client.receive_json()
    assert response["success"]
    assert response["result"]["title"] == "Media"
    assert mock_browse.await_args.args == (hass, "media-source://media_source/local/.")
    content_filter = mock_browse.await_args.kwargs["content_filter"]

    def item(content_type: str) -> BrowseMedia:
        return BrowseMedia(
            title="item",
            media_class=MediaClass.MUSIC,
            media_content_id="id",
            media_content_type=content_type,
            can_play=True,
            can_expand=False,
        )

    assert content_filter(item("audio/mpeg"))
    assert not content_filter(item("video/mp4"))
    assert not content_filter(item("image/jpeg"))


async def test_push_updates(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
) -> None:
    """States pushed by the watch loop update the media player."""
    await mock_watch.push(
        hass, speaker_state(volume=52, muted=True, player=player_state(state="paused"))
    )
    state = hass.states.get(ENTITY_ID)
    assert state.state == MediaPlayerState.PAUSED
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == 0.52
    assert state.attributes[ATTR_MEDIA_VOLUME_MUTED] is True


async def test_unavailable_and_recovery(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
) -> None:
    """The media player is unavailable while the speaker is unreachable."""
    await mock_watch.push(hass, None)
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    await mock_watch.push(hass, None)
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    await mock_watch.push(hass, speaker_state(source=Source.TV))
    assert hass.states.get(ENTITY_ID).state == MediaPlayerState.ON
    assert len(mock_watch.calls) == 1  # same watch: the client reconnects itself


async def test_watch_error_restarts(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unexpected error makes the player unavailable, then the watch restarts."""
    await mock_watch.push(hass, RuntimeError("boom"))
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    assert f"Error while following {HOST}" in caplog.text
    assert mock_watch.active == 0

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=WATCH_RESTART_DELAY - 5)
    )
    await hass.async_block_till_done()
    assert len(mock_watch.calls) == 1

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=WATCH_RESTART_DELAY + 1)
    )
    await hass.async_block_till_done()
    assert len(mock_watch.calls) == 2
    assert mock_watch.active == 1

    await mock_watch.push(hass, speaker_state())
    assert hass.states.get(ENTITY_ID).state == MediaPlayerState.PLAYING


async def test_only_media_player(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """One media player per speaker."""
    entries = er.async_entries_for_config_entry(
        entity_registry, init_integration.entry_id
    )
    assert [(e.domain, e.unique_id) for e in entries] == [
        (Platform.MEDIA_PLAYER, f"KEF_SPEAKER_{UNIQUE_ID}")
    ]
