from __future__ import annotations
import asyncio
import logging
from datetime import timedelta
import functools

from pykefcontrol.kef_connector import KefAsyncConnector
import voluptuous as vol

import homeassistant.util.dt as hass_dt
import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.aiohttp_client as hass_aiohttp
from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_PLAY,
    SUPPORT_PAUSE,
    SUPPORT_NEXT_TRACK,
    SUPPORT_PREVIOUS_TRACK,
    SUPPORT_SELECT_SOURCE,
    MediaPlayerEntity,
)

from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    STATE_ON,
    STATE_OFF,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_PLAYING,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.entity_component import EntityComponent

_LOGGER = logging.getLogger(__name__)

CONF_MAX_VOLUME = "maximum_volume"
CONF_VOLUME_STEP = "volume_step"

DEFAULT_NAME = "DEFAULT_KEFLS50W2"
DEFAULT_MAX_VOLUME = 1
DEFAULT_VOLUME_STEP = 0.03

SCAN_INTERVAL = timedelta(seconds=10)


DOMAIN = "kef_connector"

SOURCES = ["wifi", "bluetooth", "tv", "optical", "coaxial", "analog"]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_MAX_VOLUME, default=DEFAULT_MAX_VOLUME): cv.small_float,
        vol.Optional(CONF_VOLUME_STEP, default=DEFAULT_VOLUME_STEP): cv.small_float,
    }
)

# Create new class from KefAsyncConnector to override the
# resurect_session method, so that i uses the function
# async_get_clientsession
class KefHassAsyncConnector(KefAsyncConnector):
    def __init__(self, host, session=None, hass=None):
        super().__init__(host, session=session)
        self.hass = hass

    async def resurect_session(self):
        if self._session is None:
            self._session = hass_aiohttp.async_get_clientsession(self.hass)


# Decorator to delay the update of home assistant UI
# since the speaker does not update imediately is internal state
def delay_update(delay):
    def inner_function(function):
        @functools.wraps(function)
        async def wrapper(self, *args, **kwargs):
            # Execute the function
            output = await function(self, *args, **kwargs)
            # Sleep the set delay
            await asyncio.sleep(delay)
            # Trigger an update
            self.async_schedule_update_ha_state(True)
            return output

        return wrapper

    return inner_function


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup platform kef_connector"""

    # Get variables from configuration
    host = config[CONF_HOST]
    name = config[CONF_NAME]
    max_volume = config[CONF_MAX_VOLUME]
    volume_step = config[CONF_VOLUME_STEP]

    # set available sources
    sources = SOURCES

    # get session
    session = hass_aiohttp.async_create_clientsession(hass)

    _LOGGER.debug(
        "Setting up %s with host: %s, name: %s, sources: %s",
        DOMAIN,
        host,
        name,
        sources,
    )

    media_player = KefLS50W2(
        host, name, max_volume, volume_step, sources, session, hass
    )

    async_add_entities([media_player], update_before_add=True)

    return True


class KefLS50W2(MediaPlayerEntity):
    """
    Media player implementation for KEF LS50W2
    """

    def __init__(self, host, name, max_volume, volume_step, sources, session, hass):
        super().__init__()
        self._speaker = KefHassAsyncConnector(host, session=session, hass=hass)
        if name != "DEFAULT_KEFLS50W2":
            self._name = name
        else:
            self._name = None
        self._max_volume = max_volume
        self._volume_step = volume_step * 100
        self._sources = sources

        # Variables to update in async_update
        self._volume = None
        self._state = None
        self._muted = None
        self._source = None
        self._attr_media_artist = None
        self._attr_media_album_name = None
        self._attr_media_title = None
        self._attr_media_position = None
        self._attr_media_duration = None
        self._attr_media_position_updated_at = None
        self._attr_unique_id = None
        self._attr_media_image_url = None
        self._attr_media_image_remotely_accessible = False

    @property
    def should_poll(self):
        """Push an update after each command."""
        return True

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._volume

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._muted

    @property
    def source(self):
        """Name of the current input source."""
        return self._source

    @property
    def source_list(self):
        """List of available input sources."""
        return self._sources

    @property
    def icon(self):
        """Return the device's icon."""
        return "mdi:speaker-wireless"

    @property
    def unique_id(self):
        """Return the device unique id."""
        return self._attr_unique_id

    @property
    def media_image_url(self) -> str | None:
        """Image url of current playing media."""
        return self._attr_media_image_url

    @property
    def media_artist(self):
        """Artist of current playing media, music track only."""
        return self._attr_media_artist

    @property
    def media_album_name(self):
        return self._attr_media_album_name

    @property
    def media_title(self):
        return self._attr_media_title

    @property
    def media_position(self):
        return self._attr_media_position

    @property
    def media_position_updated_at(self):
        """When was the position of the current playing media valid.
        Returns value from homeassistant.util.dt.utcnow().
        """
        return self._attr_media_position_updated_at

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        support_kef = (
            SUPPORT_VOLUME_SET
            | SUPPORT_VOLUME_STEP
            | SUPPORT_VOLUME_MUTE
            | SUPPORT_TURN_OFF
            | SUPPORT_TURN_ON
            | SUPPORT_PREVIOUS_TRACK
            | SUPPORT_NEXT_TRACK
            | SUPPORT_PAUSE
            | SUPPORT_PLAY
            | SUPPORT_SELECT_SOURCE
        )

        return support_kef

    async def async_update(self):
        """Update latest state"""

        # Update name and unique_id if needed (the first time)
        if self.name is None:
            self._name = await self._speaker.speaker_name
        if self.unique_id is None:
            self._attr_unique_id = "KEFLS50W2_" + await self._speaker.mac_address

        # Get speaker volume (from [0,100] to [0,1])
        self._volume = await self._speaker.volume / 100

        # Get speaker state.
        # Playing/Idle is available only for bluetooth or wifi
        if await self._speaker.status == "standby":
            self._state = STATE_OFF
        elif await self._speaker.source in ["tv", "optical", "coaxial", "analog"]:
            self._state = STATE_ON
        else:
            if await self._speaker.is_playing:
                self._state = STATE_PLAYING
            elif self._attr_media_title is not None:
                self._state = STATE_PAUSED
            else:
                self._state = STATE_IDLE

        # Check if speaker is muted
        self._muted = True if self._volume == 0 else False

        # Get currently playing media info (if any)
        media_dict = await self._speaker.get_song_information()
        self._attr_media_title = media_dict["title"]
        self._attr_media_artist = media_dict["artist"]
        self._attr_media_album_name = media_dict["album"]
        self._attr_media_image_url = media_dict["cover_url"]

        # Get speaker source
        self._source = await self._speaker.source

        # Update media state if a media is playing
        if self._state == STATE_PLAYING:
            # Update media length
            self._attr_media_duration = int(await self._speaker.song_length / 1000)
            # Update media position
            self._attr_media_position = int(await self._speaker.song_status / 1000)
            # Update last media position update
            self._attr_media_position_updated_at = hass_dt.utcnow()
        else:
            # Set values to None if no media is playing
            self._attr_media_duration = None
            self._attr_media_position = None
            self._attr_media_position_updated_at = None

    @delay_update(5)
    async def async_turn_on(self):
        await self._speaker.power_on()

    @delay_update(5)
    async def async_turn_off(self):
        await self._speaker.shutdown()

    async def async_volume_up(self):
        await self._speaker.set_volume(await self._speaker.volume + self._volume_step)

    async def async_volume_down(self):
        await self._speaker.set_volume(await self._speaker.volume - self._volume_step)

    async def async_set_volume_level(self, volume):
        # make sure volume is not louder than max_volume
        # multiply by 100 to be in range of what KefAsyncConnector expects
        volume = int(min(volume, self._max_volume) * 100)
        await self._speaker.set_volume(volume)

    async def async_mute_volume(self, mute):
        if mute:
            await self._speaker.mute()
        else:
            await self._speaker.unmute()

    @delay_update(0.5)
    async def async_select_source(self, source):
        await self._speaker.set_source(source)

    @delay_update(0.25)
    async def async_media_play(self):
        await self._speaker.toggle_play_pause()

    @delay_update(0.25)
    async def async_media_pause(self):
        await self._speaker.toggle_play_pause()

    @delay_update(0.25)
    async def async_media_play_pause(self):
        """Toggle play pause"""
        await self._speaker.toggle_play_pause()

    @delay_update(1.5)
    async def async_media_next_track(self):
        await self._speaker.next_track()

    @delay_update(1.5)
    async def async_media_previous_track(self):
        await self._speaker.previous_track()
