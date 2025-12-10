"""Constants for the KEF Connector integration."""
from __future__ import annotations

from typing import Final

# Domain
DOMAIN: Final = "kef_connector"

# Configuration keys
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_OFFLINE_RETRY_INTERVAL: Final = "offline_retry_interval"
CONF_MAX_VOLUME: Final = "maximum_volume"
CONF_VOLUME_STEP: Final = "volume_step"
CONF_SPEAKER_MODEL: Final = "speaker_model"

# Defaults
DEFAULT_SCAN_INTERVAL: Final = 10  # seconds
DEFAULT_OFFLINE_RETRY_INTERVAL: Final = 60  # seconds
DEFAULT_VOLUME_STEP: Final = 0.05
DEFAULT_MAX_VOLUME: Final = 1.0
DEFAULT_SPEAKER_MODEL: Final = "LSX2"

# Validation ranges
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300
MIN_OFFLINE_RETRY_INTERVAL: Final = 30
MAX_OFFLINE_RETRY_INTERVAL: Final = 600
MIN_VOLUME_STEP: Final = 0.01
MAX_VOLUME_STEP: Final = 0.10
MIN_MAX_VOLUME: Final = 0.1
MAX_MAX_VOLUME: Final = 1.0

# Speaker models and their available sources
SOURCES: Final = {
    "LSX2": ["wifi", "bluetooth", "tv", "optical", "analog", "usb"],
    "LSX2LT": ["wifi", "bluetooth", "tv", "optical", "usb"],
    "LS50W2": ["wifi", "bluetooth", "tv", "optical", "coaxial", "analog"],
    "LS60": ["wifi", "bluetooth", "tv", "optical", "coaxial", "analog"],
    "XIO": ["wifi", "bluetooth", "tv", "optical"],
}

# KEF speaker model prefixes for zeroconf filtering
# Order matters: check more specific patterns first (LSX-II-LT- before LSX-II-)
KEF_ZEROCONF_PREFIXES: Final = [
    "LSX-II-LT-",      # LSX2LT model
    "LSX-II-",         # LSX2 model (check after LSX-II-LT-)
    "LS50-WIRELESS-II-",  # LS50W2 model
    "LS60-",           # LS60 model
    "XIO-",            # XIO model
]

# Speaker model display names
MODEL_NAMES: Final = {
    "LSX2": "LSX II",
    "LSX2LT": "LSX II LT",
    "LS50W2": "LS50 Wireless II",
    "LS60": "LS60 Wireless",
    "XIO": "XIO",
}

# Unique ID prefix for entity registry
UNIQUE_ID_PREFIX: Final = "KEF_SPEAKER"

# Zeroconf discovery
ZEROCONF_TYPE: Final = "_http._tcp.local."

# Device info
MANUFACTURER: Final = "KEF"
