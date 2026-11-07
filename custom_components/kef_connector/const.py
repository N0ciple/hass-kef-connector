"""Constants for the KEF Connector integration."""

from typing import Final

DOMAIN: Final = "kef_connector"

# Options (percent of the speaker volume).
CONF_MAX_VOLUME: Final = "max_volume"
CONF_VOLUME_STEP: Final = "volume_step"
DEFAULT_MAX_VOLUME: Final = 100
DEFAULT_VOLUME_STEP: Final = 3
MAX_VOLUME_RANGE: Final = (1, 100)
VOLUME_STEP_RANGE: Final = (1, 10)

# Unique id of the media player, unchanged since 0.x (entity registry adoption).
MEDIA_PLAYER_UNIQUE_ID_PREFIX: Final = "KEF_SPEAKER"
LEGACY_UNIQUE_ID_PREFIX: Final = "KEFLS50W2"

# Legacy YAML platform (0.x), imported into a config entry.
LEGACY_CONF_MAX_VOLUME: Final = "maximum_volume"
LEGACY_CONF_VOLUME_STEP: Final = "volume_step"
LEGACY_CONF_SPEAKER_MODEL: Final = "speaker_model"
LEGACY_DEFAULT_NAME: Final = "DEFAULT_KEFSPEAKER"
LEGACY_DEFAULT_MAX_VOLUME: Final = 1.0
LEGACY_DEFAULT_VOLUME_STEP: Final = 0.03
LEGACY_DEFAULT_SPEAKER_MODEL: Final = "default"


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    return max(bounds[0], min(bounds[1], value))


def legacy_options(maximum_volume: float, volume_step: float) -> dict[str, int]:
    """Convert the 0.x YAML options (fractions of 1) to options in percent."""
    return {
        CONF_MAX_VOLUME: _clamp(round(maximum_volume * 100), MAX_VOLUME_RANGE),
        CONF_VOLUME_STEP: _clamp(round(volume_step * 100), VOLUME_STEP_RANGE),
    }
