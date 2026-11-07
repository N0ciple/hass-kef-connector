"""Helpers of the KEF Connector tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, create_autospec

from homeassistant.helpers import entity_registry as er

from custom_components.kef_connector.const import DOMAIN
from pykefcontrol import (
    Capabilities,
    DeviceInfo,
    FirmwareVersion,
    KefAsyncClient,
    KefConnectionError,
    PlayerState,
    PlayMode,
    Settings,
    Source,
    SpeakerModel,
    SpeakerState,
    SpeakerStatus,
    paths,
)
from pykefcontrol.capabilities import get_capabilities
from pykefcontrol.eq import (
    DEFAULT_RANGES,
    EqDescriptor,
    EqRange,
    ranges_from_descriptors,
)

from .const import (
    EQ_PROFILE_LS50WII,
    EQ_PROFILE_V2,
    FIRMWARE,
    FIRMWARE_2,
    MAC,
    MAC_2,
    MODEL_NAME,
    MODEL_NAME_2,
    NAME,
    NAME_2,
    PLAYER_DATA,
    POSITION_UPDATED_AT,
    RELEASE_TEXT,
    SERIAL,
    SERIAL_2,
    UNIQUE_ID,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable, Mapping

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

EQ_PATH = "kef:eqProfile/v2"

# ``kef:dsp/editValue`` rows of the LS50 Wireless II (subset).
EQ_DESCRIPTORS = {
    "trebleAmount": EqDescriptor(
        "trebleAmount", "range", 0.0, EqRange(-3.0, 3.0, 0.25, 0.0), ()
    ),
    "balance": EqDescriptor("balance", "range", 0, EqRange(-30, 30, 1, 0), ()),
    "bassExtension": EqDescriptor(
        "bassExtension", "stringList", "standard", None, ("less", "standard", "extra")
    ),
}


def _range(
    name: str, lo: float, hi: float, step: float, default: float
) -> EqDescriptor:
    return EqDescriptor(name, "range", default, EqRange(lo, hi, step, default), ())


def _choices(name: str, default: str, *choices: str) -> EqDescriptor:
    return EqDescriptor(name, "stringList", default, None, choices)


def _boolean(name: str, default: bool) -> EqDescriptor:
    return EqDescriptor(name, "boolean", default, None, ())


# ``kef:dsp/editValue`` rows of the user's LS50 Wireless II (firmware 4.1.192).
EQ_DESCRIPTORS_LS50WII = {
    d.name: d
    for d in (
        _choices("audioPolarity", "normal", "normal", "inverted"),
        _range("balance", -30, 30, 1, 0),
        _choices("bassExtension", "standard", "standard", "extra", "less"),
        _boolean("deskMode", False),
        _range("deskModeSetting", -10, 0, 0.5, -3.0),
        _boolean("dialogueMode", False),
        _boolean("highPassMode", False),
        _range("highPassModeFreq", 50, 120, 2.5, 95),
        _boolean("phaseCorrection", True),
        _boolean("subEnableStereo", False),
        _range("subOutLPFreq", 40, 250, 2.5, 80),
        _range("subwooferCount", 0, 2, 1, 0),
        _range("subwooferGain", -10, 10, 1, 0.0),
        _boolean("subwooferOut", True),
        _choices("subwooferPolarity", "normal", "normal", "inverted"),
        _choices(
            "subwooferPreset",
            "custom",
            *("custom", "other", "kc62", "kf92", "kube8b", "kube10b", "kube12b"),
            *("kube15mie", "t2"),
        ),
        _range("trebleAmount", -3, 3, 0.25, 0.0),
        _boolean("wallMode", False),
        _range("wallModeSetting", -10, 0, 0.5, 0.0),
    )
}


def eq_ranges(descriptors: Mapping[str, EqDescriptor]) -> dict[str, EqRange]:
    """What ``get_eq_ranges`` returns for these descriptors (merged over defaults)."""
    return {**DEFAULT_RANGES, **ranges_from_descriptors(descriptors)}


EQ_RANGES = eq_ranges(EQ_DESCRIPTORS)
EQ_RANGES_LS50WII = eq_ranges(EQ_DESCRIPTORS_LS50WII)

BLUETOOTH_STATE_PATH = paths.BLUETOOTH_STATE

# Values of the followed paths (decoded, as in ``SpeakerState.extra``) on the
# user's LS50 Wireless II, plus settings of other models (never read from it).
SPEAKER_VALUES: dict[str, Any] = {
    EQ_PATH: EQ_PROFILE_LS50WII,
    Settings.STANDBY_MODE.path: "standby_30mins",
    Settings.STARTUP_TONE.path: True,
    Settings.MAXIMUM_VOLUME.path: 70,
    Settings.VOLUME_STEP.path: 3,
    Settings.VOLUME_LIMIT.path: True,
    Settings.WAKE_UP_SOURCE.path: "optical",
    Settings.DISABLE_FRONT_LED.path: False,
    Settings.DISABLE_TOP_PANEL.path: False,
    Settings.AUTO_SWITCH_TO_TV.path: True,
    Settings.SUBWOOFER_FORCE_ON.path: False,
    Settings.CABLE_MODE.path: "wireless",
    Settings.MASTER_CHANNEL_MODE.path: "left",
    Settings.FAVOURITE_BUTTON.path: "nextSource",
    BLUETOOTH_STATE_PATH: {
        "connected": False,
        "discoverable": False,
        "pairable": True,
        "discovering": False,
    },
    Settings.DIALOGUE_MODE.path: False,
    # XIO, LSX II, LS60 only.
    Settings.TOP_PANEL_LED.path: True,
    Settings.TOP_PANEL_STANDBY_LED.path: False,
    Settings.DISABLE_FRONT_STANDBY_LED.path: True,
    Settings.USB_CHARGING.path: False,
}


def settings_state(
    changes: Mapping[str, Any] | None = None, *, eq: dict[str, Any] | None = None
) -> SpeakerState:
    """State of the LS50 Wireless II with its settings (``changes`` by path).

    ``eq`` changes some fields of the EQ profile (API names).
    """
    extra = SPEAKER_VALUES | {EQ_PATH: EQ_PROFILE_LS50WII | (eq or {})}
    return speaker_state(extra=extra | dict(changes or {}))


def answer_settings(client: MagicMock, values: Mapping[str, Any]) -> None:
    """Make ``get_state`` return ``values`` for the extra paths it is asked for."""

    async def get_state(extra_paths: Iterable[str] = ()) -> SpeakerState:
        return speaker_state(extra={path: values.get(path) for path in extra_paths})

    client.get_state.side_effect = get_state


def set_model(
    client: MagicMock,
    model: SpeakerModel,
    firmware: str | None,
    *,
    sources: tuple[Source, ...] | None = None,
) -> None:
    """Make the mocked speaker another model (same identity otherwise)."""
    info = device_info(model=model, firmware=FirmwareVersion.parse(firmware or ""))
    client.get_device_info.return_value = info
    capabilities = get_capabilities(model, info.firmware)
    if sources is not None:
        capabilities = Capabilities(model, info.firmware, sources)
    client.get_capabilities.return_value = capabilities


def device_info(**changes: Any) -> DeviceInfo:
    """Identity of the LS50 Wireless II."""
    values: dict[str, Any] = {
        "name": NAME,
        "model": SpeakerModel.LS50_WIRELESS_II,
        "model_name": MODEL_NAME,
        "serial_number": SERIAL,
        "mac_address": MAC,
        "firmware": FirmwareVersion.parse(FIRMWARE),
        "firmware_version": "V27100",
        "release_text": RELEASE_TEXT,
        "hardware_version": None,
    }
    return DeviceInfo(**(values | changes))


def device_info_2(**changes: Any) -> DeviceInfo:
    """Identity of the LSX II."""
    values: dict[str, Any] = {
        "name": NAME_2,
        "model": SpeakerModel.LSX_II,
        "model_name": MODEL_NAME_2,
        "serial_number": SERIAL_2,
        "mac_address": MAC_2,
        "firmware": FirmwareVersion.parse(FIRMWARE_2),
        "firmware_version": None,
        "release_text": "LSXII_V30139",
        "hardware_version": None,
    }
    return DeviceInfo(**(values | changes))


def player_state(**changes: Any) -> PlayerState:
    """Player state parsed from the raw ``player:player/data`` payload."""
    return PlayerState.from_api(PLAYER_DATA | changes)


def speaker_state(**changes: Any) -> SpeakerState:
    """State of a speaker playing Spotify on the wifi source."""
    state = SpeakerState(
        status=SpeakerStatus.POWER_ON,
        source=Source.WIFI,
        volume=35,
        muted=False,
        play_mode=PlayMode.NORMAL,
        player=player_state(),
        position_ms=61500,
        position_updated_at=POSITION_UPDATED_AT,
        name=NAME,
        extra={EQ_PATH: dict(EQ_PROFILE_V2)},
    )
    return state.replace(**changes)


class _End:
    """Ends the watch generator (the client was closed)."""


END = _End()


class WatchController:
    """Fake ``KefAsyncClient.watch``: tests push states, ``None`` or exceptions."""

    def __init__(self) -> None:
        """Initialize the controller."""
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.calls: list[tuple[str, ...]] = []
        self.active = 0

    def watch(
        self,
        *,
        extra_paths: Iterable[str] = (),
        track_position: bool = False,
        reconnect: bool = True,
    ) -> AsyncIterator[SpeakerState | None]:
        """Start a new watch."""
        self.calls.append(tuple(extra_paths))
        return self._generate()

    async def _generate(self) -> AsyncIterator[SpeakerState | None]:
        self.active += 1
        try:
            while True:
                item = await self.queue.get()
                try:
                    if item is END:
                        return
                    if isinstance(item, BaseException):
                        raise item
                    yield item
                finally:
                    # Reached when the consumer asks for the next item (it has
                    # processed this one) or when the item ends the generator.
                    self.queue.task_done()
        finally:
            self.active -= 1

    async def push(self, hass: HomeAssistant, item: Any) -> None:
        """Send an item and wait until the coordinator has processed it."""
        self.queue.put_nowait(item)
        async with asyncio.timeout(5):
            await self.queue.join()
        await hass.async_block_till_done()


def make_client(
    host: str,
    info: DeviceInfo,
    state: SpeakerState,
    *,
    eq_version: int | None = 2,
) -> MagicMock:
    """Autospecced ``KefAsyncClient`` answering like a real speaker."""
    client = create_autospec(KefAsyncClient, instance=True)
    client.host = host
    client.is_secure = False
    client.get_device_info.return_value = info
    client.get_capabilities.return_value = get_capabilities(info.model, info.firmware)
    client.get_eq_version.return_value = eq_version
    client.get_eq_descriptors.return_value = dict(EQ_DESCRIPTORS)
    client.get_eq_ranges.return_value = dict(EQ_RANGES)
    client.get_state.return_value = state
    client.get_volume.return_value = state.volume
    watch = WatchController()
    client.watch.side_effect = watch.watch
    client.watch_controller = watch
    return client


def unreachable_client(host: str) -> MagicMock:
    """Client of an address where nothing answers."""
    client = create_autospec(KefAsyncClient, instance=True)
    client.host = host
    client.get_device_info.side_effect = KefConnectionError(f"{host} unreachable")
    return client


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up a config entry of the integration."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def entity_id(hass: HomeAssistant, domain: str, key: str) -> str:
    """Entity id of the entity ``key`` of the LS50 Wireless II."""
    registry = er.async_get(hass)
    found = registry.async_get_entity_id(domain, DOMAIN, f"{UNIQUE_ID}_{key}")
    assert found is not None, f"no {domain} {key}"
    return found


def entity_keys(
    hass: HomeAssistant, entry: MockConfigEntry
) -> dict[str, er.RegistryEntry]:
    """Registry entries of a config entry, by description key."""
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    return {e.unique_id.removeprefix(f"{UNIQUE_ID}_"): e for e in entries}
