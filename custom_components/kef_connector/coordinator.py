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
            codec_info = await self._get_audio_codec_information()

            # Get WiFi signal strength
            wifi_info = await self._get_wifi_information()

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

            return {
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

        except Exception as err:
            # Speaker is offline or unreachable
            if not self._is_offline:
                # First time seeing this error - log it and switch to offline mode
                _LOGGER.warning(
                    "KEF speaker '%s' is offline or unreachable: %s. "
                    "Will retry every %d seconds until it comes back online",
                    self.name,
                    err,
                    self.offline_interval.total_seconds(),
                )
                self._is_offline = True
                self._error_logged = True
                # Switch to slower retry interval
                self.update_interval = self.offline_interval

            # Raise UpdateFailed to mark entity as unavailable
            raise UpdateFailed(f"Error communicating with KEF speaker: {err}") from err

    async def _get_audio_codec_information(self) -> dict[str, Any]:
        """Get audio codec information from player data.

        Returns dict with codec, sample rate, and channel information.
        """
        try:
            # Get player data from speaker
            player_data = await self.speaker._get_player_data()

            codec_dict = {}
            active_resource = (
                player_data.get("trackRoles", {})
                .get("mediaData", {})
                .get("activeResource", {})
            )

            if active_resource:
                codec_dict["codec"] = active_resource.get("codec")
                codec_dict["sampleFrequency"] = active_resource.get("sampleFrequency")
                codec_dict["streamSampleRate"] = active_resource.get("streamSampleRate")
                codec_dict["streamChannels"] = active_resource.get("streamChannels")
                codec_dict["nrAudioChannels"] = active_resource.get("nrAudioChannels")

            # Get streaming service ID from mediaRoles
            media_roles = player_data.get("mediaRoles", {})
            meta_data = media_roles.get("mediaData", {}).get("metaData", {})
            if meta_data:
                codec_dict["serviceID"] = meta_data.get("serviceID")

            return codec_dict
        except Exception:
            # Silently return empty dict if codec info not available
            return {}

    async def _get_wifi_information(self) -> dict[str, Any]:
        """Get WiFi information from speaker.

        Returns dict with WiFi signal strength, SSID, frequency, and BSSID.
        """
        try:
            # Get network info from speaker
            network_data = await self.speaker.get_request(
                "network:info", roles="value"
            )

            wifi_dict = {}
            network_info = (
                network_data[0].get("networkInfo", {})
                if network_data
                else {}
            )

            if network_info:
                wireless = network_info.get("wireless", {})
                if wireless:
                    wifi_dict["signalLevel"] = wireless.get("signalLevel")
                    wifi_dict["ssid"] = wireless.get("ssid")
                    wifi_dict["frequency"] = wireless.get("frequency")
                    wifi_dict["bssid"] = wireless.get("bssid")

            return wifi_dict
        except Exception:
            # Silently return empty dict if WiFi info not available
            return {}

    def update_intervals(self, scan_interval: int, offline_retry_interval: int) -> None:
        """Update the polling intervals from options."""
        self.normal_interval = timedelta(seconds=scan_interval)
        self.offline_interval = timedelta(seconds=offline_retry_interval)

        # Update current interval based on current state
        if self._is_offline:
            self.update_interval = self.offline_interval
        else:
            self.update_interval = self.normal_interval
