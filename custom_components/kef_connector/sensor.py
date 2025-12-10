"""Sensor platform for KEF Connector integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SPEAKER_MODEL,
    DOMAIN,
    MANUFACTURER,
    MODEL_NAMES,
    UNIQUE_ID_PREFIX,
)
from .coordinator import KefCoordinator


def _format_channels(channel_count: int | None) -> str | None:
    """Convert channel count to audio format notation.

    Args:
        channel_count: Number of audio channels

    Returns:
        Formatted string like "2.0", "5.1", "5.1.2" or the count as string
    """
    if channel_count is None:
        return None

    channel_map = {
        2: "2.0",
        6: "5.1",
        8: "5.1.2",
    }
    return channel_map.get(channel_count, str(channel_count))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KEF Connector sensor entities from config entry."""
    coordinator: KefCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get device info to group sensors under the same device as media_player
    name = entry.data[CONF_NAME]
    host = entry.data[CONF_HOST]
    speaker_model = entry.data.get(CONF_SPEAKER_MODEL, "LSX2").upper()
    mac_address = format_mac(await coordinator.speaker.mac_address)
    device_unique_id = f"{UNIQUE_ID_PREFIX}_{mac_address}"

    # Build device_info that matches media_player
    device_info = {
        "identifiers": {(DOMAIN, device_unique_id)},
        "name": name,
        "manufacturer": MANUFACTURER,
        "model": MODEL_NAMES.get(speaker_model, f"KEF {speaker_model}"),
        "connections": {("ip", host)},
    }

    # Create sensor entities with shared device_info
    # Only create codec sensors for XIO model (has HDMI/TV inputs)
    entities = []

    # Codec sensors - only for XIO
    if speaker_model == "XIO":
        entities.extend([
            KefCodecSensor(coordinator, entry, name, device_info),
            KefVirtualizerSensor(coordinator, entry, name, device_info),
            KefSampleRateSensor(coordinator, entry, name, device_info),
        ])

    # WiFi sensors - all models
    entities.extend([
        KefWiFiSignalSensor(coordinator, entry, name, device_info),
        KefWiFiFrequencySensor(coordinator, entry, name, device_info),
    ])

    async_add_entities(entities)


class KefCodecSensor(CoordinatorEntity, SensorEntity):
    """Sensor for KEF audio codec (part before '-')."""

    def __init__(
        self, coordinator: KefCoordinator, entry: ConfigEntry, name: str, device_info: dict
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"{name} Audio Codec"
        self._attr_unique_id = f"{entry.entry_id}_audio_codec"
        self._attr_icon = "mdi:waveform"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str | None:
        """Return the audio codec with channel format (e.g., 'Dolby Digital Plus 5.1')."""
        if not self.coordinator.last_update_success:
            return None

        codec_full = self.coordinator.data.get("audio_codec")
        if not codec_full:
            return None

        # Split on " - " and get codec part (before '-')
        codec_name = codec_full.split(" - ")[0] if " - " in codec_full else codec_full

        # Append channel format from stream_channels (source channels)
        stream_channels = self.coordinator.data.get("stream_channels")
        if stream_channels is not None and stream_channels > 0:
            channel_format = _format_channels(stream_channels)
            if channel_format:
                return f"{codec_name} {channel_format}"

        return codec_name

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.get("audio_codec") is not None
        )


class KefVirtualizerSensor(CoordinatorEntity, SensorEntity):
    """Sensor for KEF audio virtualizer (part after '-')."""

    def __init__(
        self, coordinator: KefCoordinator, entry: ConfigEntry, name: str, device_info: dict
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"{name} Audio Virtualizer"
        self._attr_unique_id = f"{entry.entry_id}_audio_virtualizer"
        self._attr_icon = "mdi:surround-sound"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str | None:
        """Return the audio virtualizer with channel format (e.g., 'Dolby Surround 5.1.2')."""
        if not self.coordinator.last_update_success:
            return None

        codec_full = self.coordinator.data.get("audio_codec")
        if not codec_full:
            return None

        # Split on " - " and get virtualizer part (after '-'), or "Direct" if not present
        virtualizer_name = codec_full.split(" - ")[1] if " - " in codec_full else "Direct"

        # Append channel format from audio_channels (playback channels)
        audio_channels = self.coordinator.data.get("audio_channels")
        if audio_channels is not None:
            channel_format = _format_channels(audio_channels)
            if channel_format:
                return f"{virtualizer_name} {channel_format}"

        return virtualizer_name

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.get("audio_codec") is not None
        )


class KefSampleRateSensor(CoordinatorEntity, SensorEntity):
    """Sensor for KEF audio sample rate."""

    def __init__(
        self, coordinator: KefCoordinator, entry: ConfigEntry, name: str, device_info: dict
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"{name} Audio Sample Rate"
        self._attr_unique_id = f"{entry.entry_id}_sample_rate"
        self._attr_native_unit_of_measurement = "Hz"
        self._attr_icon = "mdi:sine-wave"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> int | None:
        """Return the sample rate in Hz."""
        if not self.coordinator.last_update_success:
            return None
        return self.coordinator.data.get("sample_rate")

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.get("sample_rate") is not None
        )


class KefWiFiSignalSensor(CoordinatorEntity, SensorEntity):
    """Sensor for KEF WiFi signal strength (disabled by default)."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: KefCoordinator, entry: ConfigEntry, name: str, device_info: dict
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"{name} WiFi Signal"
        self._attr_unique_id = f"{entry.entry_id}_wifi_signal"
        self._attr_native_unit_of_measurement = "dBm"
        self._attr_icon = "mdi:wifi"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> int | None:
        """Return the WiFi signal strength in dBm."""
        if not self.coordinator.last_update_success:
            return None
        return self.coordinator.data.get("wifi_signal_strength")

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.get("wifi_signal_strength") is not None
        )


class KefWiFiFrequencySensor(CoordinatorEntity, SensorEntity):
    """Sensor for KEF WiFi frequency band (disabled by default)."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: KefCoordinator, entry: ConfigEntry, name: str, device_info: dict
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"{name} WiFi Frequency"
        self._attr_unique_id = f"{entry.entry_id}_wifi_frequency"
        self._attr_icon = "mdi:wifi-settings"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str | None:
        """Return the WiFi frequency band (2.4 GHz or 5 GHz)."""
        if not self.coordinator.last_update_success:
            return None

        freq = self.coordinator.data.get("wifi_frequency")
        if freq is None:
            return None

        # Convert frequency to band display
        if freq < 3000:
            return "2.4 GHz"
        else:
            return f"{freq / 1000:.1f} GHz"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.get("wifi_frequency") is not None
        )
