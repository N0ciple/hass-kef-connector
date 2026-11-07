"""Tests of the setup, unload and registry migration of KEF Connector."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kef_connector.const import DOMAIN
from pykefcontrol import (
    FirmwareVersion,
    KefApiError,
    KefConnectionError,
    KefProtocolError,
    KefUnsupportedError,
)

from .common import END, EQ_PATH, WatchController, device_info, setup_integration
from .const import (
    ENTITY_ID,
    ENTITY_ID_2,
    HOST,
    MAC,
    NAME,
    NAME_2,
    SERIAL,
    SERIAL_2,
    UNIQUE_ID,
    UNIQUE_ID_2,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

MEDIA_PLAYER_UNIQUE_ID = f"KEF_SPEAKER_{UNIQUE_ID}"


async def test_setup_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client_class: MagicMock,
    mock_kef_client: MagicMock,
    mock_watch: WatchController,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The speaker is read once, then followed by its event queue."""
    assert init_integration.state is ConfigEntryState.LOADED
    mock_kef_client_class.assert_called_once_with(
        HOST, session=async_get_clientsession(hass)
    )
    mock_kef_client.get_state.assert_awaited_once_with((EQ_PATH,))
    assert mock_watch.calls == [(EQ_PATH,)]
    assert mock_watch.active == 1
    coordinator = init_integration.runtime_data
    assert coordinator.eq_version == 2
    assert coordinator.eq_profile is not None
    assert coordinator.eq_profile.profile_name == "Living room"

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, UNIQUE_ID), init_integration.entry_id
    )
    assert device is not None
    assert device.connections == {(dr.CONNECTION_NETWORK_MAC, UNIQUE_ID)}
    assert device.name == NAME
    assert device.manufacturer == "KEF"
    assert device.model == "LS50 Wireless II"
    assert device.model_id == "SP4025"
    assert device.serial_number == SERIAL
    assert device.sw_version == "4.1.192"
    assert hass.states.get(ENTITY_ID) is not None


@pytest.mark.parametrize(
    ("exception", "translation_key"),
    [
        (KefConnectionError("timeout"), "cannot_connect"),
        (KefProtocolError("not a KEF speaker"), "setup_failed"),
    ],
)
async def test_setup_entry_not_ready(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    exception: Exception,
    translation_key: str,
) -> None:
    """Setup is retried when the speaker cannot be read."""
    mock_kef_client.get_device_info.side_effect = exception
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.error_reason_translation_key == translation_key
    mock_kef_client.aclose.assert_awaited_once()


async def test_setup_entry_first_refresh_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> None:
    """Setup is retried when the state cannot be read."""
    mock_kef_client.get_state.side_effect = KefConnectionError("reset")
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_kef_client.watch.assert_not_called()


async def test_setup_entry_wrong_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> None:
    """Another device answers at the address of the speaker."""
    mock_kef_client.get_device_info.return_value = device_info(
        mac_address="84:17:15:FF:FF:FF"
    )
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.error_reason_translation_key == "wrong_device"


async def test_setup_entry_without_mac(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> None:
    """A speaker that does not tell its MAC address is trusted."""
    mock_kef_client.get_device_info.return_value = device_info(mac_address=None)
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(
    "exception",
    [
        KefApiError(404, "Not found", path=EQ_PATH),
        KefProtocolError("garbage"),
        KefUnsupportedError("no EQ"),
    ],
)
async def test_setup_entry_eq_version_unreadable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    mock_watch: WatchController,
    exception: Exception,
) -> None:
    """The EQ profile is not followed when its format cannot be read."""
    mock_kef_client.get_eq_version.side_effect = exception
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    coordinator = mock_config_entry.runtime_data
    assert coordinator.eq_version is None
    assert coordinator.eq_profile is None
    assert mock_watch.calls == [()]


async def test_setup_entry_eq_not_supported(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> None:
    """Firmware older than the EQ profile: its format is not even asked."""
    old = FirmwareVersion.parse("1.4.0")
    mock_kef_client.get_device_info.return_value = device_info(firmware=old)
    capabilities = mock_kef_client.get_capabilities.return_value
    mock_kef_client.get_capabilities.return_value = type(capabilities)(
        model=capabilities.model, firmware=old, sources=capabilities.sources
    )
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_kef_client.get_eq_version.assert_not_called()
    assert mock_config_entry.runtime_data.extra_paths == ()


async def test_unload_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_kef_client: MagicMock,
    mock_watch: WatchController,
) -> None:
    """Unloading stops the watch and closes the client, not the HA session."""
    assert mock_watch.active == 1
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert mock_watch.active == 0
    mock_kef_client.aclose.assert_awaited_once()
    assert not async_get_clientsession(hass).closed
    assert hass.states.get(ENTITY_ID).state == "unavailable"


async def test_watch_ends_when_client_closed(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
) -> None:
    """The watch is not restarted when it ends (client closed)."""
    await mock_watch.push(hass, END)
    assert mock_watch.active == 0
    assert len(mock_watch.calls) == 1


async def test_reload_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """The media player keeps its registry entry across reloads."""
    entry = entity_registry.async_get(ENTITY_ID)
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.LOADED
    assert entity_registry.async_get(ENTITY_ID) == entry


async def test_migrate_entry_from_future_version(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """A config entry of a newer version (downgrade) is not loaded."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=UNIQUE_ID, data={CONF_HOST: HOST}, version=2
    )
    await setup_integration(hass, entry)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_migrate_entry_minor_version(
    hass: HomeAssistant, mock_kef_client: MagicMock
) -> None:
    """Older minor versions need no migration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=UNIQUE_ID,
        data={CONF_HOST: HOST},
        version=1,
        minor_version=0,
    )
    await setup_integration(hass, entry)
    assert entry.state is ConfigEntryState.LOADED


async def test_migrate_legacy_unique_id(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """The unique id of 0.3 (``KEFLS50W2_<MAC>``) is migrated and adopted."""
    legacy = entity_registry.async_get_or_create(
        "media_player", DOMAIN, f"KEFLS50W2_{MAC}", suggested_object_id="kef_ls50"
    )
    # Not migrated: other platform / domain / speaker, or not a legacy id.
    other_platform = entity_registry.async_get_or_create(
        "media_player", "other", f"KEFLS50W2_{MAC}"
    )
    other_domain = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"KEFLS50W2_{MAC}"
    )
    other_speaker = entity_registry.async_get_or_create(
        "media_player", DOMAIN, "KEFLS50W2_84:17:15:FF:FF:FF"
    )
    not_legacy = entity_registry.async_get_or_create(
        "media_player", DOMAIN, "something_else"
    )

    await setup_integration(hass, mock_config_entry)

    entry = entity_registry.async_get(legacy.entity_id)
    assert entry is not None
    assert entry.unique_id == MEDIA_PLAYER_UNIQUE_ID
    assert entry.config_entry_id == mock_config_entry.entry_id
    assert entry.device_id is not None
    assert hass.states.get("media_player.kef_ls50") is not None
    assert hass.states.get(ENTITY_ID) is None
    for untouched in (other_platform, other_domain, other_speaker, not_legacy):
        assert entity_registry.async_get(untouched.entity_id) == untouched


async def test_adopt_yaml_entity_with_name(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
) -> None:
    """The entity of the YAML platform keeps its id and user settings."""
    area = area_registry.async_create("Living room")
    yaml_entity = entity_registry.async_get_or_create(
        "media_player",
        DOMAIN,
        MEDIA_PLAYER_UNIQUE_ID,
        suggested_object_id="living_room_kef",
    )
    entity_registry.async_update_entity(
        yaml_entity.entity_id,
        name="Hi-fi",
        icon="mdi:speaker",
        area_id=area.id,
    )

    await setup_integration(hass, mock_config_entry)

    entry = entity_registry.async_get("media_player.living_room_kef")
    assert entry is not None
    assert entry.config_entry_id == mock_config_entry.entry_id
    assert entry.name == "Hi-fi"
    assert entry.icon == "mdi:speaker"
    assert entry.area_id == area.id  # own name: the area stays on the entity
    device = device_registry.async_get(entry.device_id)
    assert device is not None
    assert device.identifiers == {(DOMAIN, UNIQUE_ID)}
    assert device.area_id is None
    assert er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    ) == [entry]
    state = hass.states.get("media_player.living_room_kef")
    assert state is not None
    assert state.name == "Hi-fi"
    assert state.attributes["icon"] == "mdi:speaker"


async def test_adopt_yaml_entity_without_name(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
) -> None:
    """The area of an entity without its own name moves to the device."""
    area = area_registry.async_create("Living room")
    yaml_entity = entity_registry.async_get_or_create(
        "media_player",
        DOMAIN,
        MEDIA_PLAYER_UNIQUE_ID,
        suggested_object_id="living_room_kef",
    )
    entity_registry.async_update_entity(yaml_entity.entity_id, area_id=area.id)

    await setup_integration(hass, mock_config_entry)

    entry = entity_registry.async_get("media_player.living_room_kef")
    assert entry is not None
    assert entry.config_entry_id == mock_config_entry.entry_id
    assert entry.area_id is None
    device = device_registry.async_get(entry.device_id)
    assert device is not None
    assert device.area_id == area.id
    state = hass.states.get("media_player.living_room_kef")
    assert state is not None
    assert state.name == NAME


async def test_adopt_yaml_entity_device_has_area(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
) -> None:
    """The area of the device is not replaced by the area of the entity."""
    kitchen = area_registry.async_create("Kitchen")
    living_room = area_registry.async_create("Living room")
    mock_config_entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, UNIQUE_ID)},
    )
    device_registry.async_update_device(device.id, area_id=kitchen.id)
    yaml_entity = entity_registry.async_get_or_create(
        "media_player", DOMAIN, MEDIA_PLAYER_UNIQUE_ID
    )
    entity_registry.async_update_entity(yaml_entity.entity_id, area_id=living_room.id)

    await setup_integration(hass, mock_config_entry)

    entry = entity_registry.async_get(yaml_entity.entity_id)
    assert entry is not None
    assert entry.config_entry_id == mock_config_entry.entry_id
    assert entry.area_id == living_room.id
    assert device_registry.async_get(device.id).area_id == kitchen.id


async def test_entity_of_another_entry_not_adopted(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
) -> None:
    """An entity attached to a config entry is not migrated again."""
    area = area_registry.async_create("Living room")
    other_entry = MockConfigEntry(
        domain=DOMAIN, unique_id="other", data={CONF_HOST: "192.168.1.99"}
    )
    other_entry.add_to_hass(hass)
    owned = entity_registry.async_get_or_create(
        "media_player",
        DOMAIN,
        MEDIA_PLAYER_UNIQUE_ID,
        config_entry=other_entry,
    )
    entity_registry.async_update_entity(owned.entity_id, area_id=area.id)

    await setup_integration(hass, mock_config_entry)

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, UNIQUE_ID), mock_config_entry.entry_id
    )
    assert device is not None
    assert device.area_id is None  # area not moved: the migration did nothing
    assert entity_registry.async_get(owned.entity_id).area_id == area.id


async def test_two_speakers(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    second_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    second_kef_client: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Two speakers have their own client, device and media player."""
    await setup_integration(hass, mock_config_entry)
    await setup_integration(hass, second_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert second_config_entry.state is ConfigEntryState.LOADED

    device_1 = device_registry.async_get_device_by_identifier(
        (DOMAIN, UNIQUE_ID), mock_config_entry.entry_id
    )
    device_2 = device_registry.async_get_device_by_identifier(
        (DOMAIN, UNIQUE_ID_2), second_config_entry.entry_id
    )
    assert device_1 is not None
    assert device_2 is not None
    assert device_1.id != device_2.id
    assert (device_1.name, device_1.serial_number) == (NAME, SERIAL)
    assert (device_2.name, device_2.serial_number) == (NAME_2, SERIAL_2)
    assert device_2.model == "LSX II"
    assert device_2.model_id == "SP4041"
    assert device_2.sw_version == "3.0.139.12"

    entity_1 = entity_registry.async_get(ENTITY_ID)
    entity_2 = entity_registry.async_get(ENTITY_ID_2)
    assert entity_1.device_id == device_1.id
    assert entity_1.config_entry_id == mock_config_entry.entry_id
    assert entity_2.device_id == device_2.id
    assert entity_2.config_entry_id == second_config_entry.entry_id
    assert hass.states.get(ENTITY_ID).state == "playing"
    assert hass.states.get(ENTITY_ID_2).state == "on"
    assert hass.states.get(ENTITY_ID_2).attributes["source_list"] == [
        "wifi",
        "bluetooth",
        "tv",
        "optical",
        "usb",
        "analog",
    ]

    # Each speaker is followed by its own client.
    await mock_kef_client.watch_controller.push(hass, None)
    assert hass.states.get(ENTITY_ID).state == "unavailable"
    assert hass.states.get(ENTITY_ID_2).state == "on"

    assert await hass.config_entries.async_unload(second_config_entry.entry_id)
    second_kef_client.aclose.assert_awaited_once()
    mock_kef_client.aclose.assert_not_called()
