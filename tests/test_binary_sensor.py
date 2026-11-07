"""Tests of the binary sensors of KEF Connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
    Platform,
)
from pytest_homeassistant_custom_component.common import snapshot_platform

from pykefcontrol import Source, SpeakerModel

from .common import (
    BLUETOOTH_STATE_PATH,
    entity_id,
    entity_keys,
    set_model,
    settings_state,
    setup_integration,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from syrupy.assertion import SnapshotAssertion

    from .common import WatchController

KEY = "bluetooth_connected"


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the binary sensors only."""
    return [Platform.BINARY_SENSOR]


def _state(hass: HomeAssistant) -> str:
    state = hass.states.get(entity_id(hass, BINARY_SENSOR_DOMAIN, KEY))
    assert state is not None
    return state.state


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_settings: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Snapshot of the binary sensors of the LS50 Wireless II."""
    await snapshot_platform(hass, entity_registry, snapshot, init_settings.entry_id)


async def test_entity_set(hass: HomeAssistant, init_settings: MockConfigEntry) -> None:
    """The Bluetooth connection is a diagnostic sensor, disabled by default."""
    entries = entity_keys(hass, init_settings)
    assert {
        key: (entry.disabled_by is None, entry.entity_category)
        for key, entry in entries.items()
    } == {KEY: (False, EntityCategory.DIAGNOSTIC)}


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_states(
    hass: HomeAssistant, init_settings: MockConfigEntry, mock_watch: WatchController
) -> None:
    """The state follows the pushed Bluetooth state."""
    assert _state(hass) == STATE_OFF
    await mock_watch.push(
        hass, settings_state({BLUETOOTH_STATE_PATH: {"connected": True}})
    )
    assert _state(hass) == STATE_ON
    await mock_watch.push(hass, settings_state({BLUETOOTH_STATE_PATH: None}))
    assert _state(hass) == STATE_UNKNOWN
    await mock_watch.push(hass, settings_state({BLUETOOTH_STATE_PATH: "garbage"}))
    assert _state(hass) == STATE_UNKNOWN  # not a Bluetooth state
    await mock_watch.push(hass, None)
    assert _state(hass) == STATE_UNAVAILABLE


async def test_not_returned(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
    speaker_values: dict[str, Any],
) -> None:
    """No sensor if the speaker does not return its Bluetooth state."""
    del speaker_values[BLUETOOTH_STATE_PATH]
    await setup_integration(hass, mock_config_entry)
    assert entity_keys(hass, mock_config_entry) == {}


async def test_no_bluetooth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> None:
    """No sensor (nor followed state) without Bluetooth source."""
    set_model(
        settings_client,
        SpeakerModel.LS50_WIRELESS_II,
        "4.1.192",
        sources=(Source.WIFI, Source.OPTICAL),
    )
    await setup_integration(hass, mock_config_entry)
    assert entity_keys(hass, mock_config_entry) == {}
    assert BLUETOOTH_STATE_PATH not in settings_client.watch_controller.calls[0]
