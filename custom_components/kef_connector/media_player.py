"""Media player platform for KEF Connector integration."""
from __future__ import annotations

import asyncio
import functools
import logging

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
    STATE_PAUSED,
    STATE_PLAYING,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .const import (
    CONF_MAX_VOLUME,
    CONF_SPEAKER_MODEL,
    CONF_VOLUME_STEP,
    DEFAULT_MAX_VOLUME,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
    MANUFACTURER,
    MODEL_NAMES,
    SOURCES,
    UNIQUE_ID_PREFIX,
)
from .coordinator import KefCoordinator

_LOGGER = logging.getLogger(__name__)


# Decorator to delay the update of home assistant UI
# since the speaker does not update immediately its internal state
def delay_update(delay):
    """Delay the update of home assistant UI."""

    def inner_function(function):
        @functools.wraps(function)
        async def wrapper(self, *args, **kwargs):
            # Execute the function
            output = await function(self, *args, **kwargs)
            # Sleep the set delay
            await asyncio.sleep(delay)
            # Trigger an update
            await self.coordinator.async_request_refresh()
            return output

        return wrapper

    return inner_function


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KEF Connector media player from config entry."""
    coordinator: KefCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get config
    name = entry.data[CONF_NAME]
    host = entry.data[CONF_HOST]
    speaker_model = entry.data.get(CONF_SPEAKER_MODEL, "LSXII").upper()

    # Get options with defaults
    max_volume = entry.options.get(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME)
    volume_step = entry.options.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP)

    # Get sources for this model
    sources = SOURCES.get(speaker_model, SOURCES["LSXII"])

    # Get unique_id from coordinator speaker
    mac_address = format_mac(await coordinator.speaker.mac_address)
    unique_id = f"{UNIQUE_ID_PREFIX}_{mac_address}"

    # Create entity
    entity = KefSpeaker(
        coordinator=coordinator,
        name=name,
        unique_id=unique_id,
        speaker_model=speaker_model,
        sources=sources,
        max_volume=max_volume,
        volume_step=volume_step,
        host=host,
    )

    async_add_entities([entity])


class KefSpeaker(CoordinatorEntity, MediaPlayerEntity):
    """Media player implementation for KEF Speakers."""

    def __init__(
        self,
        coordinator: KefCoordinator,
        name: str,
        unique_id: str,
        speaker_model: str,
        sources: list[str],
        max_volume: float,
        volume_step: float,
        host: str,
    ) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)

        # Store config
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._speaker_model = speaker_model
        self._sources = sources
        self._max_volume = max_volume
        self._volume_step = volume_step * 100  # Convert to 0-100 range

        # State tracking
        self._previous_source = "wifi"

        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, unique_id)},
            "name": name,
            "manufacturer": MANUFACTURER,
            "model": MODEL_NAMES.get(speaker_model, f"KEF {speaker_model}"),
            "connections": {("ip", host)},
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def state(self):
        """Return the state of the device."""
        if not self.available:
            return None

        data = self.coordinator.data

        if data["status"] == "standby":
            return STATE_OFF
        elif data["source"] in ["wifi", "bluetooth"]:
            if data["is_playing"]:
                return STATE_PLAYING
            elif data["media_title"] is not None:
                return STATE_PAUSED
            else:
                return STATE_IDLE
        else:
            return STATE_ON

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        if not self.available:
            return None
        return self.coordinator.data["volume"] / 100

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        if not self.available:
            return None
        return self.coordinator.data["volume"] == 0

    @property
    def source(self):
        """Name of the current input source."""
        if not self.available:
            return None
        source = self.coordinator.data["source"]
        # Store valid sources as previous source
        if source in self._sources:
            self._previous_source = source
        return source

    @property
    def source_list(self):
        """List of available input sources."""
        return self._sources

    @property
    def icon(self):
        """Return the device's icon."""
        return "mdi:speaker-wireless"

    @property
    def media_image_url(self) -> str | None:
        """Image url of current playing media."""
        if not self.available:
            return None

        # No album art for non-streaming sources (TV, Optical, etc.)
        source = self.coordinator.data.get("source")
        if source in ["tv", "optical", "analog", "coaxial", "usb"]:
            return None

        return self.coordinator.data.get("media_image_url")

    @property
    def media_artist(self):
        """Artist of current playing media, music track only."""
        if not self.available:
            return None
        return self.coordinator.data.get("media_artist")

    @property
    def media_album_name(self):
        """Album name of current playing media, music track only."""
        if not self.available:
            return None
        return self.coordinator.data.get("media_album")

    @property
    def media_title(self):
        """Title of current playing media."""
        if not self.available:
            return None

        title = self.coordinator.data.get("media_title")
        source = self.coordinator.data.get("source")
        audio_codec = self.coordinator.data.get("audio_codec")

        # Append codec to title for TV/HDMI sources
        if source in ["tv", "optical", "analog", "coaxial", "usb"] and audio_codec:
            # Format channel count (2→"2.0", 6→"5.1", 8→"5.1.2")
            stream_channels = self.coordinator.data.get("stream_channels")
            channel_format = None
            if stream_channels is not None and stream_channels > 0:
                channel_map = {2: "2.0", 6: "5.1", 8: "5.1.2"}
                channel_format = channel_map.get(stream_channels, str(stream_channels))

            # Split codec to get only the codec part (before " - ")
            codec_name = audio_codec.split(" - ")[0] if " - " in audio_codec else audio_codec

            # Strip "Dolby " prefix from PCM (but NOT from "Dolby Digital" or "Dolby Digital Plus")
            if codec_name == "Dolby PCM":
                codec_name = "PCM"

            # Build codec string with channel format
            codec_display = codec_name
            if channel_format:
                codec_display = f"{codec_name} {channel_format}"

            if title:
                return f"{title} - {codec_display}"
            return codec_display

        return title

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        if not self.available:
            return None

        source = self.coordinator.data.get("source")
        # Return "music" for streaming sources to enable artist/album display
        if source in ["wifi", "bluetooth"]:
            return "music"
        # Return "channel" for TV/HDMI sources
        elif source in ["tv", "optical", "analog", "coaxial", "usb"]:
            return "channel"
        return None

    @property
    def media_position(self):
        """Position of current playing media in seconds."""
        if not self.available:
            return None
        song_position = self.coordinator.data.get("song_position")
        return int(song_position / 1000) if song_position is not None else None

    @property
    def media_duration(self):
        """Duration of current playing media in seconds."""
        if not self.available:
            return None
        song_length = self.coordinator.data.get("song_length")
        return int(song_length / 1000) if song_length is not None else None

    @property
    def media_position_updated_at(self):
        """When was the position of the current playing media valid.

        Returns value from homeassistant.util.dt.utcnow().
        """
        if not self.available:
            return None
        # Return current time if playing, None otherwise
        if self.state == STATE_PLAYING:
            return dt_util.utcnow()
        return None

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        if not self.available:
            return {}

        attrs = {}

        # Split codec and virtualizer with channel format
        if self.coordinator.data.get("audio_codec"):
            codec_full = self.coordinator.data["audio_codec"]

            # Split codec and virtualizer
            codec_name = codec_full.split(" - ")[0] if " - " in codec_full else codec_full
            virtualizer_name = codec_full.split(" - ")[1] if " - " in codec_full else "Direct"

            # Strip "Dolby " prefix from PCM (but NOT from "Dolby Digital" or "Dolby Digital Plus")
            if codec_name == "Dolby PCM":
                codec_name = "PCM"

            # Helper to format channel count
            def format_channels(count):
                channel_map = {2: "2.0", 6: "5.1", 8: "5.1.2"}
                return channel_map.get(count, str(count)) if count is not None else None

            # Add codec with source channel format
            stream_channels = self.coordinator.data.get("stream_channels")
            if stream_channels is not None and stream_channels > 0:
                channel_format = format_channels(stream_channels)
                attrs["audio_codec"] = f"{codec_name} {channel_format}" if channel_format else codec_name
            else:
                # Fallback: just codec name without channel count
                attrs["audio_codec"] = codec_name

            # Add virtualizer with channel format
            # For Direct mode: use INPUT channels (stream_channels), fallback to OUTPUT channels
            # For virtualizer modes: use fixed 8 channels (5.1.2) since API returns garbage
            if virtualizer_name == "Direct":
                # Direct mode - use input channels, fallback to output if input unknown
                channels = stream_channels
                if channels is None or channels == 0:
                    # Fallback to playback channels (e.g., Dolby Atmos with unknown input)
                    channels = self.coordinator.data.get("audio_channels")
            else:
                # Virtualizer active - hardcode to 8 (5.1.2) for XIO
                channels = 8

            if channels is not None and channels > 0:
                channel_format = format_channels(channels)
                attrs["audio_virtualizer"] = f"{virtualizer_name} {channel_format}" if channel_format else virtualizer_name
            else:
                # Fallback: just virtualizer name without channel count
                attrs["audio_virtualizer"] = virtualizer_name

        # Sample rate
        if self.coordinator.data.get("sample_rate"):
            attrs["audio_sample_rate"] = self.coordinator.data["sample_rate"]

        # Raw codec (unparsed)
        if self.coordinator.data.get("audio_codec_raw"):
            attrs["audio_codec_raw"] = self.coordinator.data["audio_codec_raw"]

        # Streaming service ID (e.g., "airplay", "spotify")
        if self.coordinator.data.get("streaming_service"):
            attrs["streaming_service"] = self.coordinator.data["streaming_service"]

        # WiFi BSSID (access point MAC address)
        if self.coordinator.data.get("wifi_bssid"):
            attrs["wifi_bssid"] = self.coordinator.data["wifi_bssid"]

        return attrs

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        support_kef = (
            MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.SELECT_SOURCE
        )

        return support_kef

    @delay_update(5)
    async def async_turn_on(self):
        """Turn the media player on."""
        await self.coordinator.speaker.set_source(self._previous_source)

    @delay_update(5)
    async def async_turn_off(self):
        """Turn the media player off."""
        await self.coordinator.speaker.shutdown()

    async def async_volume_up(self):
        """Volume up the media player."""
        current_volume = await self.coordinator.speaker.volume
        await self.coordinator.speaker.set_volume(current_volume + self._volume_step)
        await self.coordinator.async_request_refresh()

    async def async_volume_down(self):
        """Volume down the media player."""
        current_volume = await self.coordinator.speaker.volume
        await self.coordinator.speaker.set_volume(current_volume - self._volume_step)
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        # make sure volume is not louder than max_volume
        # multiply by 100 to be in range of what KefAsyncConnector expects
        volume = int(min(volume, self._max_volume) * 100)
        await self.coordinator.speaker.set_volume(volume)
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        if mute:
            await self.coordinator.speaker.mute()
        else:
            await self.coordinator.speaker.unmute()
        await self.coordinator.async_request_refresh()

    @delay_update(0.5)
    async def async_select_source(self, source):
        """Select input source."""
        await self.coordinator.speaker.set_source(source)

    @delay_update(0.25)
    async def async_media_play(self):
        """Send play command."""
        await self.coordinator.speaker.toggle_play_pause()

    @delay_update(0.25)
    async def async_media_pause(self):
        """Send pause command."""
        await self.coordinator.speaker.toggle_play_pause()

    @delay_update(0.25)
    async def async_media_play_pause(self):
        """Toggle play pause."""
        await self.coordinator.speaker.toggle_play_pause()

    @delay_update(1.5)
    async def async_media_next_track(self):
        """Send next track command."""
        await self.coordinator.speaker.next_track()

    @delay_update(1.5)
    async def async_media_previous_track(self):
        """Send previous track command."""
        await self.coordinator.speaker.previous_track()
