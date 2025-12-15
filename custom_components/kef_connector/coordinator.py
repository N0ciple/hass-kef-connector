"""DataUpdateCoordinator for KEF Connector."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from pykefcontrol.kef_connector import KefAsyncConnector

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class KefCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching KEF speaker data."""

    def __init__(
        self,
        hass: HomeAssistant,
        speaker: KefAsyncConnector,
        name: str,
        scan_interval: int,
        offline_retry_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        self.speaker = speaker
        self.name = name
        self.normal_interval = timedelta(seconds=scan_interval)
        self.offline_interval = timedelta(seconds=offline_retry_interval)
        self._is_offline = False
        self._error_logged = False
        self._consecutive_failures = 0
        self._failure_threshold = 3  # Number of consecutive failures before switching to offline mode
        self._last_successful_data: dict[str, Any] | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{name}",
            update_interval=self.normal_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from KEF speaker.

        Returns dict with all speaker state information.
        Raises UpdateFailed if speaker is unreachable.
        """
        try:
            # Get all speaker state in one update cycle
            volume = await self.speaker.volume
            status = await self.speaker.status
            source = await self.speaker.source
            is_playing = (
                await self.speaker.is_playing
                if source in ["wifi", "bluetooth"]
                else False
            )

            # Get media info (may return empty dict if nothing playing)
            media_info = await self.speaker.get_song_information()

            # Get song playback info if playing
            song_length = None
            song_position = None
            if is_playing:
                song_length = await self.speaker.song_length
                song_position = await self.speaker.song_status

            # Get codec info (available on models with HDMI/TV inputs)
            codec_info = await self.speaker.get_audio_codec_information()

            # Get WiFi signal strength
            wifi_info = await self.speaker.get_wifi_information()

            # Speaker is online - reset offline state
            if self._is_offline:
                _LOGGER.info(
                    "KEF speaker '%s' is back online",
                    self.name,
                )
                self._is_offline = False
                self._error_logged = False
                # Return to normal polling interval
                self.update_interval = self.normal_interval

            # Reset failure counter on successful update
            self._consecutive_failures = 0

            # Cache successful data for use during transient failures
            data = {
                "volume": volume,
                "status": status,
                "source": source,
                "is_playing": is_playing,
                "media_title": media_info.get("title"),
                "media_artist": media_info.get("artist"),
                "media_album": media_info.get("album"),
                "media_album_artist": media_info.get("album_artist"),
                "media_image_url": media_info.get("cover_url"),
                "song_length": song_length,
                "song_position": song_position,
                # Codec information (may be None on some sources/models)
                "audio_codec": codec_info.get("codec"),
                "audio_codec_raw": codec_info.get("codec"),
                "sample_rate": codec_info.get("sampleFrequency"),
                "stream_channels": codec_info.get("streamChannels"),
                "audio_channels": codec_info.get("nrAudioChannels"),
                "streaming_service": codec_info.get("serviceID"),
                # WiFi information
                "wifi_signal_strength": wifi_info.get("signalLevel"),
                "wifi_ssid": wifi_info.get("ssid"),
                "wifi_frequency": wifi_info.get("frequency"),
                "wifi_bssid": wifi_info.get("bssid"),
            }
            self._last_successful_data = data
            return data

        except Exception as err:
            # Increment consecutive failure counter
            self._consecutive_failures += 1

            # Check if we've reached the threshold for marking as offline
            if self._consecutive_failures >= self._failure_threshold:
                # Now consider the speaker truly offline
                if not self._is_offline:
                    # First time marking as offline - log warning and switch to slow polling
                    _LOGGER.warning(
                        "KEF speaker '%s' is offline or unreachable after %d consecutive failures: %s. "
                        "Will retry every %d seconds until it comes back online",
                        self.name,
                        self._consecutive_failures,
                        err,
                        self.offline_interval.total_seconds(),
                    )
                    self._is_offline = True
                    self._error_logged = True
                    # Switch to slower retry interval
                    self.update_interval = self.offline_interval

                # Raise UpdateFailed to mark entity as unavailable
                raise UpdateFailed(f"Error communicating with KEF speaker: {err}") from err

            else:
                # Still within tolerance - log as debug and return cached data
                _LOGGER.debug(
                    "KEF speaker '%s' connection attempt %d/%d failed: %s. "
                    "Using cached data and retrying at normal interval",
                    self.name,
                    self._consecutive_failures,
                    self._failure_threshold,
                    err,
                )

                # If we have cached data, return it to keep entity available
                if self._last_successful_data is not None:
                    return self._last_successful_data

                # No cached data yet (first poll ever failed) - have to mark unavailable
                raise UpdateFailed(f"Initial connection failed (attempt {self._consecutive_failures}/{self._failure_threshold}): {err}") from err

    def update_intervals(self, scan_interval: int, offline_retry_interval: int) -> None:
        """Update the polling intervals from options."""
        self.normal_interval = timedelta(seconds=scan_interval)
        self.offline_interval = timedelta(seconds=offline_retry_interval)

        # Update current interval based on current state
        if self._is_offline:
            self.update_interval = self.offline_interval
        else:
            self.update_interval = self.normal_interval
