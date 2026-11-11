"""Media player of a KEF speaker."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any, override

import voluptuous as vol
from homeassistant.components import media_source
from homeassistant.components.media_player import (
    PLATFORM_SCHEMA as MEDIA_PLAYER_PLATFORM_SCHEMA,
    MediaPlayerEntity,
)
from homeassistant.components.media_player.browse_media import (
    BrowseMedia,
    async_process_play_media_url,
)
from homeassistant.components.media_player.const import (
    ATTR_MEDIA_EXTRA,
    MediaPlayerDeviceClass,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, issue_registry as ir

from pykefcontrol import PlaybackState, PlayMode, Source, Track

from .const import (
    CONF_MAX_VOLUME,
    CONF_VOLUME_STEP,
    DEFAULT_MAX_VOLUME,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
    LEGACY_CONF_MAX_VOLUME,
    LEGACY_CONF_SPEAKER_MODEL,
    LEGACY_CONF_VOLUME_STEP,
    LEGACY_DEFAULT_MAX_VOLUME,
    LEGACY_DEFAULT_NAME,
    LEGACY_DEFAULT_SPEAKER_MODEL,
    LEGACY_DEFAULT_VOLUME_STEP,
    MEDIA_PLAYER_UNIQUE_ID_PREFIX,
)
from .coordinator import kef_errors
from .entity import KefEntity, kef_command

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import (
        AddConfigEntryEntitiesCallback,
        AddEntitiesCallback,
    )
    from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

    from .coordinator import KefConfigEntry, KefCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# Legacy 0.x YAML platform: only imported into a config entry.
PLATFORM_SCHEMA = MEDIA_PLAYER_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=LEGACY_DEFAULT_NAME): cv.string,
        vol.Optional(
            LEGACY_CONF_MAX_VOLUME, default=LEGACY_DEFAULT_MAX_VOLUME
        ): cv.small_float,
        vol.Optional(
            LEGACY_CONF_VOLUME_STEP, default=LEGACY_DEFAULT_VOLUME_STEP
        ): cv.small_float,
        vol.Optional(
            LEGACY_CONF_SPEAKER_MODEL, default=LEGACY_DEFAULT_SPEAKER_MODEL
        ): cv.string,
    }
)
IMPORT_FAILURE_REASONS = ("cannot_connect", "not_kef", "unknown")

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
# When the player does not tell which controls are allowed.
DEFAULT_TRANSPORT_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
)
# Sources played by the speaker's own player (others are physical inputs).
PLAYER_SOURCES = {Source.WIFI, Source.BLUETOOTH}
PLAYBACK_STATES = {
    PlaybackState.PLAYING: MediaPlayerState.PLAYING,
    PlaybackState.PAUSED: MediaPlayerState.PAUSED,
    PlaybackState.TRANSITIONING: MediaPlayerState.BUFFERING,
}
PLAYABLE_MEDIA_TYPES = {MediaType.MUSIC, MediaType.URL}


def _host_hash(host: str) -> str:
    """Short, stable id of a host for issue ids (diagnostics list issue ids)."""
    return hashlib.sha256(host.encode()).hexdigest()[:12]


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import the 0.x YAML configuration into a config entry.

    No entity is added here: the media player belongs to the config entry.
    """
    host: str = config[CONF_HOST]
    suffix = _host_hash(host)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=dict(config)
    )
    reason = result.get("reason")
    placeholders = {"host": host, "name": config[CONF_NAME]}
    if result["type"] is FlowResultType.ABORT and reason != "already_configured":
        if reason not in IMPORT_FAILURE_REASONS:
            reason = "unknown"
        _LOGGER.warning(
            "Could not import the YAML configuration of the KEF speaker at %s: %s",
            host,
            reason,
        )
        ir.async_delete_issue(hass, DOMAIN, f"deprecated_yaml_{suffix}")
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"deprecated_yaml_import_issue_{reason}_{suffix}",
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"deprecated_yaml_import_issue_{reason}",
            translation_placeholders=placeholders,
        )
        return
    _LOGGER.warning(
        "The YAML configuration of the KEF speaker at %s has been imported into "
        "a config entry: remove it from configuration.yaml",
        host,
    )
    for failure in IMPORT_FAILURE_REASONS:
        ir.async_delete_issue(
            hass, DOMAIN, f"deprecated_yaml_import_issue_{failure}_{suffix}"
        )
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"deprecated_yaml_{suffix}",
        is_fixable=False,
        issue_domain=DOMAIN,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
        translation_placeholders=placeholders,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KefConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the media player of a speaker."""
    async_add_entities([KefMediaPlayer(entry.runtime_data)])


class KefMediaPlayer(KefEntity, MediaPlayerEntity):
    """The speaker as a media player."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_translation_key = "speaker"
    _attr_media_content_type = MediaType.MUSIC
    _attr_media_image_remotely_accessible = False

    def __init__(self, coordinator: KefCoordinator) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)
        # Unchanged since 0.x, so that the YAML entity is adopted.
        self._attr_unique_id = f"{MEDIA_PLAYER_UNIQUE_ID_PREFIX}_{self.mac}"
        self._attr_source_list = [str(s) for s in coordinator.capabilities.sources]
        options = coordinator.config_entry.options
        self._max_volume: int = options.get(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME)
        self._step: int = options.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP)
        self._attr_volume_step = self._step / 100

    @property
    def _on_player(self) -> bool:
        """Whether the speaker is on and plays from its own player."""
        data = self.coordinator.data
        return data.is_on and data.source in PLAYER_SOURCES

    @property
    def _track(self) -> Track | None:
        return self.coordinator.data.track if self.coordinator.data.is_on else None

    @property
    @override
    def state(self) -> MediaPlayerState:
        """State of the speaker (off in standby: it can be woken up)."""
        data = self.coordinator.data
        if not data.is_on:
            return MediaPlayerState.OFF
        if not self._on_player:
            return MediaPlayerState.ON
        if data.playback_state is None:
            return MediaPlayerState.IDLE
        return PLAYBACK_STATES.get(data.playback_state, MediaPlayerState.IDLE)

    @property
    @override
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Features, depending on what the current source allows."""
        features = BASE_FEATURES
        if not self._on_player:
            return features
        player = self.coordinator.data.player
        if player is None or "controls" not in player.raw:
            return features | DEFAULT_TRANSPORT_FEATURES
        controls = player.controls
        features |= MediaPlayerEntityFeature.STOP
        if controls.pause:
            features |= MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE
        if controls.next:
            features |= MediaPlayerEntityFeature.NEXT_TRACK
        if controls.previous:
            features |= MediaPlayerEntityFeature.PREVIOUS_TRACK
        if controls.seek:
            features |= MediaPlayerEntityFeature.SEEK
        if any(mode.shuffle for mode in controls.play_modes):
            features |= MediaPlayerEntityFeature.SHUFFLE_SET
        if any(mode.repeat != "off" for mode in controls.play_modes):
            features |= MediaPlayerEntityFeature.REPEAT_SET
        return features

    @property
    @override
    def source(self) -> str | None:
        """Current input."""
        source = self.coordinator.data.source
        return None if source in (None, Source.STANDBY) else str(source)

    @property
    @override
    def volume_level(self) -> float | None:
        """Volume (0..1 of the speaker's range)."""
        volume = self.coordinator.data.volume
        return None if volume is None else volume / 100

    @property
    @override
    def is_volume_muted(self) -> bool | None:
        """Mute state."""
        return self.coordinator.data.muted

    @property
    @override
    def shuffle(self) -> bool | None:
        """Shuffle state."""
        mode = self.coordinator.data.play_mode
        return None if mode is None else mode.shuffle

    @property
    @override
    def repeat(self) -> RepeatMode | None:
        """Repeat mode."""
        mode = self.coordinator.data.play_mode
        return None if mode is None else RepeatMode(mode.repeat)

    @property
    @override
    def media_title(self) -> str | None:
        """Title of the current track."""
        return self._track.title if self._track else None

    @property
    @override
    def media_artist(self) -> str | None:
        """Artist of the current track."""
        return self._track.artist if self._track else None

    @property
    @override
    def media_album_name(self) -> str | None:
        """Album of the current track."""
        return self._track.album if self._track else None

    @property
    @override
    def media_album_artist(self) -> str | None:
        """Album artist of the current track."""
        return self._track.album_artist if self._track else None

    @property
    @override
    def media_image_url(self) -> str | None:
        """Cover of the current track."""
        return self._track.cover_url if self._track else None

    @property
    @override
    def media_duration(self) -> int | None:
        """Duration of the current track, in seconds."""
        if not self._on_player or not self._track or not self._track.duration_ms:
            return None
        return self._track.duration_ms // 1000

    @property
    @override
    def media_position(self) -> int | None:
        """Position in the current track, in seconds."""
        position = self.coordinator.data.position_ms
        if not self._on_player or position is None or position < 0:
            return None
        return position // 1000

    @property
    @override
    def media_position_updated_at(self) -> datetime | None:
        """When the position was read."""
        if self.media_position is None:
            return None
        return self.coordinator.data.position_updated_at

    @kef_command
    @override
    async def async_turn_on(self) -> None:
        """Wake the speaker up on its last source."""
        await self.coordinator.client.power_on()

    @kef_command
    @override
    async def async_turn_off(self) -> None:
        """Put the speaker in standby."""
        await self.coordinator.client.power_off()

    @kef_command
    @override
    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume, capped at the maximum volume option."""
        await self.coordinator.client.set_volume(
            round(min(volume * 100, self._max_volume))
        )

    @override
    async def async_volume_up(self) -> None:
        """Raise the volume by the volume step, up to the maximum volume."""
        await self._async_step_volume(self._step)

    @override
    async def async_volume_down(self) -> None:
        """Lower the volume by the volume step."""
        await self._async_step_volume(-self._step)

    @kef_command
    async def _async_step_volume(self, step: int) -> None:
        client = self.coordinator.client
        current = self.coordinator.data.volume
        if current is None:
            current = await client.get_volume()
        target = current + step
        if step > 0:  # never raise above the cap, never lower when stepping up
            target = max(current, min(target, self._max_volume))
        await client.set_volume(max(0, min(100, target)))

    @kef_command
    @override
    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute."""
        await self.coordinator.client.set_mute(mute)

    @kef_command
    @override
    async def async_select_source(self, source: str) -> None:
        """Select an input (wakes the speaker up)."""
        if source not in (self.source_list or ()):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_source",
                translation_placeholders={"source": source},
            )
        await self.coordinator.client.set_source(source)

    @kef_command
    @override
    async def async_media_play(self) -> None:
        """Resume playback."""
        await self.coordinator.client.play()

    @kef_command
    @override
    async def async_media_pause(self) -> None:
        """Pause playback."""
        await self.coordinator.client.pause()

    @kef_command
    @override
    async def async_media_play_pause(self) -> None:
        """Toggle play / pause."""
        await self.coordinator.client.play_pause()

    @kef_command
    @override
    async def async_media_stop(self) -> None:
        """Stop playback."""
        await self.coordinator.client.stop()

    @kef_command
    @override
    async def async_media_next_track(self) -> None:
        """Next track."""
        await self.coordinator.client.next_track()

    @kef_command
    @override
    async def async_media_previous_track(self) -> None:
        """Previous track."""
        await self.coordinator.client.previous_track()

    @kef_command
    @override
    async def async_media_seek(self, position: float) -> None:
        """Seek to ``position`` seconds."""
        await self.coordinator.client.seek(round(position * 1000))

    @kef_command
    @override
    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Enable or disable shuffle."""
        mode = self.coordinator.data.play_mode or PlayMode.NORMAL
        await self.coordinator.client.set_play_mode(
            PlayMode.from_flags(shuffle=shuffle, repeat=mode.repeat)
        )

    @kef_command
    @override
    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set the repeat mode."""
        mode = self.coordinator.data.play_mode or PlayMode.NORMAL
        await self.coordinator.client.set_play_mode(
            PlayMode.from_flags(shuffle=mode.shuffle, repeat=str(repeat))
        )

    @override
    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play an audio URL or media source item (experimental)."""
        mime_type = "audio/unknown"
        if media_source.is_media_source_id(media_id):
            item = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            media_id, mime_type = item.url, item.mime_type
        elif media_type not in PLAYABLE_MEDIA_TYPES and not str(media_type).startswith(
            "audio/"
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_media_type",
                translation_placeholders={"media_type": str(media_type)},
            )
        title = (kwargs.get(ATTR_MEDIA_EXTRA) or {}).get("title")
        with kef_errors():
            await self.coordinator.client.play_url(
                async_process_play_media_url(self.hass, media_id),
                title=title,
                mime_type=mime_type,
            )

    @override
    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse the audio media sources."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )
