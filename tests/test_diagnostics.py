"""Tests of the diagnostics of KEF Connector."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from .common import BLUETOOTH_STATE_PATH, speaker_state
from .const import BLUETOOTH_ADDRESS, HOST, MAC, SERIAL, SYSTEM_MEMBER_ID, UNIQUE_ID

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
    from syrupy.assertion import SnapshotAssertion

    from .common import WatchController


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Diagnostics hold the speaker data, without identifying values."""
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )
    assert diagnostics == snapshot
    text = json.dumps(diagnostics)
    for secret in (HOST, MAC, UNIQUE_ID, SERIAL):
        assert secret not in text


async def test_diagnostics_unavailable(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
) -> None:
    """Diagnostics tell when the speaker is unreachable (last state kept)."""
    await mock_watch.push(hass, None)
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )
    assert diagnostics["available"] is False
    assert diagnostics["state"]["volume"] == 35


async def test_diagnostics_redact_bluetooth_and_member_ids(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
) -> None:
    """The speaker's Bluetooth address and member ids are redacted (issue #31)."""
    state = speaker_state()
    extra = {
        **state.extra,
        BLUETOOTH_STATE_PATH: {"connected": True, "address": BLUETOOTH_ADDRESS},
    }
    await mock_watch.push(hass, state.replace(extra=extra))
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )
    text = json.dumps(diagnostics)
    for secret in (BLUETOOTH_ADDRESS, SYSTEM_MEMBER_ID, HOST):
        assert secret not in text
