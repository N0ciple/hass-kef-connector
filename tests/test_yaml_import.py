"""Tests of the import of the 0.x YAML configuration of KEF Connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.media_player import DOMAIN as MP_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PLATFORM
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.kef_connector import media_player
from custom_components.kef_connector.const import (
    CONF_MAX_VOLUME,
    CONF_VOLUME_STEP,
    DOMAIN,
)
from custom_components.kef_connector.media_player import _host_hash
from pykefcontrol import KefConnectionError, KefProtocolError

from .const import ENTITY_ID_2, HOST, HOST_2, NAME, NAME_2, UNIQUE_ID

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

HOST_HASH = _host_hash(HOST)
ISSUE_ID = f"deprecated_yaml_{HOST_HASH}"
YAML_ENTITY_ID = "media_player.living_room_kef"
YAML_SPEAKER = {
    CONF_PLATFORM: DOMAIN,
    CONF_HOST: HOST,
    "name": "Living room KEF",
    "maximum_volume": 0.6,
    "volume_step": 0.05,
    "speaker_model": "LS50",
}


async def _setup_yaml(hass: HomeAssistant, *speakers: dict[str, Any]) -> None:
    assert await async_setup_component(hass, MP_DOMAIN, {MP_DOMAIN: list(speakers)})
    await hass.async_block_till_done()


async def test_yaml_import(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    issue_registry: ir.IssueRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """The YAML speaker is imported into a config entry, with a repair issue."""
    await _setup_yaml(hass, YAML_SPEAKER)

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.title == "Living room KEF"
    assert entry.unique_id == UNIQUE_ID
    assert entry.data == {CONF_HOST: HOST}
    assert entry.options == {CONF_MAX_VOLUME: 60, CONF_VOLUME_STEP: 5}
    assert entry.state is ConfigEntryState.LOADED

    issue = issue_registry.async_get_issue(DOMAIN, ISSUE_ID)
    assert issue is not None
    assert issue.translation_key == "deprecated_yaml"
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable
    assert issue.translation_placeholders == {"host": HOST, "name": "Living room KEF"}

    # The only media player is the one of the config entry.
    entities = [e for e in entity_registry.entities.values() if e.platform == DOMAIN]
    assert len(entities) == 1
    assert entities[0].config_entry_id == entry.entry_id
    assert hass.states.async_entity_ids(MP_DOMAIN) == [YAML_ENTITY_ID]
    state = hass.states.get(YAML_ENTITY_ID)
    assert state.attributes["friendly_name"] == "Living room KEF"


async def test_yaml_import_adopts_entity(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Upgrade from 0.x: the entity of the YAML platform is kept."""
    legacy = entity_registry.async_get_or_create(
        MP_DOMAIN,
        DOMAIN,
        f"KEF_SPEAKER_{UNIQUE_ID}",
        suggested_object_id="kef_ls50",
    )
    entity_registry.async_update_entity(legacy.entity_id, name="Hi-fi")
    await _setup_yaml(hass, YAML_SPEAKER)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    adopted = entity_registry.async_get("media_player.kef_ls50")
    assert adopted is not None
    assert adopted.config_entry_id == entry.entry_id
    assert adopted.name == "Hi-fi"
    assert hass.states.async_entity_ids(MP_DOMAIN) == ["media_player.kef_ls50"]
    assert hass.states.get("media_player.kef_ls50").name == "Hi-fi"


async def test_yaml_import_default_name(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Without a name, the entry gets the name of the speaker."""
    await _setup_yaml(hass, {CONF_PLATFORM: DOMAIN, CONF_HOST: HOST})
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.title == NAME
    assert entry.options == {CONF_MAX_VOLUME: 100, CONF_VOLUME_STEP: 3}
    issue = issue_registry.async_get_issue(DOMAIN, ISSUE_ID)
    assert issue.translation_placeholders == {
        "host": HOST,
        "name": "DEFAULT_KEFSPEAKER",
    }


@pytest.mark.parametrize(
    ("side_effect", "reason"),
    [
        (KefConnectionError("timeout"), "cannot_connect"),
        (KefProtocolError("not KEF"), "not_kef"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_yaml_import_failure(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    issue_registry: ir.IssueRegistry,
    caplog: pytest.LogCaptureFixture,
    side_effect: Exception,
    reason: str,
) -> None:
    """A failed import raises an issue telling why."""
    mock_kef_client.get_device_info.side_effect = side_effect
    await _setup_yaml(hass, YAML_SPEAKER)

    assert not hass.config_entries.async_entries(DOMAIN)
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_ID) is None
    issue = issue_registry.async_get_issue(
        DOMAIN, f"deprecated_yaml_import_issue_{reason}_{HOST_HASH}"
    )
    assert issue is not None
    assert issue.translation_key == f"deprecated_yaml_import_issue_{reason}"
    assert issue.translation_placeholders == {"host": HOST, "name": "Living room KEF"}
    assert "Could not import the YAML configuration" in caplog.text
    assert hass.states.async_entity_ids(MP_DOMAIN) == []


async def test_yaml_import_unexpected_abort(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Other abort reasons are reported as unknown errors."""
    with patch(
        "custom_components.kef_connector.config_flow.KefConfigFlow.async_step_import",
        return_value={"type": "abort", "reason": "already_in_progress"},
    ):
        await _setup_yaml(hass, YAML_SPEAKER)
    assert issue_registry.async_get_issue(
        DOMAIN, f"deprecated_yaml_import_issue_unknown_{HOST_HASH}"
    )


async def test_yaml_import_two_speakers(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    second_kef_client: MagicMock,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Each YAML speaker gets its config entry and its issue."""
    await _setup_yaml(
        hass,
        YAML_SPEAKER,
        {CONF_PLATFORM: DOMAIN, CONF_HOST: HOST_2, "name": NAME_2},
    )
    entries = hass.config_entries.async_entries(DOMAIN)
    assert sorted(e.title for e in entries) == ["Living room KEF", NAME_2]
    assert all(e.state is ConfigEntryState.LOADED for e in entries)
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_ID)
    assert issue_registry.async_get_issue(
        DOMAIN, f"deprecated_yaml_{_host_hash(HOST_2)}"
    )
    assert sorted(hass.states.async_entity_ids(MP_DOMAIN)) == [
        YAML_ENTITY_ID,
        ENTITY_ID_2,
    ]


async def test_yaml_import_restart(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    issue_registry: ir.IssueRegistry,
) -> None:
    """The import at the next start finds the entry: nothing is added."""
    await _setup_yaml(hass, YAML_SPEAKER)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    # Next start: the YAML platform is set up again.
    add_entities = MagicMock()
    await media_player.async_setup_platform(
        hass, media_player.PLATFORM_SCHEMA(YAML_SPEAKER), add_entities
    )
    await hass.async_block_till_done()

    assert hass.config_entries.async_entries(DOMAIN) == [entry]
    add_entities.assert_not_called()
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_ID)
    assert len(issue_registry.issues) == 1


async def test_yaml_import_failure_then_success(
    hass: HomeAssistant,
    mock_kef_client: MagicMock,
    issue_registry: ir.IssueRegistry,
) -> None:
    """The failure issue is replaced once the import succeeds."""
    mock_kef_client.get_device_info.side_effect = KefConnectionError("timeout")
    await _setup_yaml(hass, YAML_SPEAKER)
    failure_id = f"deprecated_yaml_import_issue_cannot_connect_{HOST_HASH}"
    assert issue_registry.async_get_issue(DOMAIN, failure_id)

    mock_kef_client.get_device_info.side_effect = None
    await media_player.async_setup_platform(
        hass, media_player.PLATFORM_SCHEMA(YAML_SPEAKER), MagicMock()
    )
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, failure_id) is None
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_ID)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
