"""Push coordinator of the KEF Connector integration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import aclosing, contextmanager
from typing import TYPE_CHECKING, Any, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pykefcontrol import (
    Capabilities,
    DeviceInfo,
    EqProfile,
    KefAsyncClient,
    KefConnectionError,
    KefError,
    Setting,
    SpeakerState,
    ValueType,
    paths,
)
from pykefcontrol.eq import DEFAULT_RANGES, EqDescriptor, EqRange, parse_eq_profile

from .const import DOMAIN

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping

_LOGGER = logging.getLogger(__name__)

# Delay before restarting the watch after an unexpected (non-KEF) error.
WATCH_RESTART_DELAY = 30

type KefConfigEntry = ConfigEntry[KefCoordinator]


@contextmanager
def kef_errors() -> Iterator[None]:
    """Turn pykefcontrol errors into translated Home Assistant errors."""
    try:
        yield
    except KefConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="communication_error",
            translation_placeholders={"error": str(err)},
        ) from err
    except KefError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    except (ValueError, TypeError) as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_value",
            translation_placeholders={"error": str(err)},
        ) from err


class KefCoordinator(DataUpdateCoordinator[SpeakerState]):
    """Follow the state of one speaker with its event queue (no polling).

    ``extra_paths`` (EQ profile, settings shown as entities) are read with the
    state and followed by the same watch loop; their decoded values are in
    ``data.extra``.
    """

    config_entry: KefConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: KefConfigEntry,
        *,
        client: KefAsyncClient,
        device_info: DeviceInfo,
        capabilities: Capabilities,
        eq_version: int | None,
        extra_paths: Iterable[str] = (),
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            always_update=False,
        )
        self.client = client
        self.device_info = device_info
        self.capabilities = capabilities
        self.eq_version = eq_version
        self.eq_path: str | None = None
        if eq_version is not None:
            self.eq_path = paths.EQ_PROFILE if eq_version == 1 else paths.EQ_PROFILE_V2
        followed = [self.eq_path] if self.eq_path else []
        self.extra_paths: tuple[str, ...] = tuple(
            dict.fromkeys([*followed, *extra_paths])
        )
        # Read once at setup: allowed range of each numeric EQ field, and the
        # choices of the EQ settings (EQ v2 descriptors, for the selects).
        self.eq_ranges: Mapping[str, EqRange] = DEFAULT_RANGES
        self.eq_descriptors: dict[str, EqDescriptor] = {}

    @override
    async def _async_setup(self) -> None:
        """Read what the speaker allows for each EQ setting."""
        if self.eq_version is None:
            return
        # The speaker's ranges merged over the app's defaults (errors: defaults).
        self.eq_ranges = await self.client.get_eq_ranges()
        if self.eq_version != 2:
            return
        try:
            self.eq_descriptors = await self.client.get_eq_descriptors()
        except KefError as err:
            _LOGGER.debug("No EQ descriptors from %s: %s", self.client.host, err)

    @override
    async def _async_update_data(self) -> SpeakerState:
        """Read the whole state (first refresh only: then the watch loop pushes)."""
        try:
            state = await self.client.get_state(self.extra_paths)
        except KefError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return state

    @callback
    def async_start_watch(self) -> None:
        """Start following the speaker; the task is cancelled on unload."""
        self.config_entry.async_create_background_task(
            self.hass, self._async_watch(), f"{DOMAIN} watch {self.client.host}"
        )

    async def _async_watch(self) -> None:
        """Follow the speaker; restart the watch if it fails unexpectedly."""
        while True:
            try:
                await self._async_follow()
            except Exception:
                _LOGGER.exception("Error while following %s", self.client.host)
                self.async_set_update_error(
                    UpdateFailed(
                        translation_domain=DOMAIN,
                        translation_key="speaker_unavailable",
                        translation_placeholders={"host": self.client.host},
                    )
                )
                await asyncio.sleep(WATCH_RESTART_DELAY)
            else:
                return  # the watch ends only when the client is closed

    async def _async_follow(self) -> None:
        # aclosing: end the long-poll at once if handling a state raises.
        async with aclosing(self.client.watch(extra_paths=self.extra_paths)) as states:
            async for state in states:
                self._async_handle_state(state)

    @callback
    def _async_handle_state(self, state: SpeakerState | None) -> None:
        if state is None:
            self.async_set_update_error(
                UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="speaker_unavailable",
                    translation_placeholders={"host": self.client.host},
                )
            )
            return
        if not self.last_update_success:
            _LOGGER.info("Connection to %s restored", self.client.host)
        self.async_set_updated_data(state)

    # --- parsed values -----------------------------------------------------------

    def has_value(self, path: str) -> bool:
        """Tell whether the speaker exposes ``path`` (it was read successfully)."""
        return self.data.extra.get(path) is not None

    @property
    def eq_profile(self) -> EqProfile | None:
        """Current EQ profile, if the speaker has one."""
        if self.eq_path is None or (raw := self.data.extra.get(self.eq_path)) is None:
            return None
        if self.eq_version == 1:  # extra holds the decoded payload: restore its type
            raw = {"type": ValueType.EQ_PROFILE.value, ValueType.EQ_PROFILE.value: raw}
        try:
            return parse_eq_profile(raw)
        except KefError:
            return None

    def setting[T](self, setting: Setting[T]) -> T | None:
        """Decoded value of a followed setting (``None`` if unknown)."""
        if (raw := self.data.extra.get(setting.path)) is None:
            return None
        try:
            return setting.decode(raw)
        except KefError, ValueError:
            return None

    # --- writes ------------------------------------------------------------------

    async def async_call[R](
        self, func: Callable[..., Awaitable[R]], *args: Any, **kwargs: Any
    ) -> R:
        """Call a client method, raising translated errors."""
        with kef_errors():
            return await func(*args, **kwargs)

    async def async_set_setting[T](self, setting: Setting[T], value: T) -> None:
        """Write a setting (the new value comes back through the watch loop)."""
        await self.async_call(self.client.set_setting, setting, value)

    async def async_update_eq_profile(self, **changes: Any) -> None:
        """Change some EQ profile fields (waits until the speaker applied them)."""
        await self.async_call(self.client.update_eq_profile, **changes)
