"""Fixtures of the KEF Connector tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.const import CONF_HOST, Platform
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kef_connector import ENTITY_DESCRIPTIONS
from custom_components.kef_connector.const import DOMAIN
from pykefcontrol import Source

from .common import (
    EQ_DESCRIPTORS_LS50WII,
    EQ_RANGES_LS50WII,
    SPEAKER_VALUES,
    WatchController,
    answer_settings,
    device_info,
    device_info_2,
    make_client,
    setup_integration,
    speaker_state,
    unreachable_client,
)
from .const import HOST, HOST_2, NAME, NAME_2, UNIQUE_ID, UNIQUE_ID_2

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in every test."""


@pytest.fixture
def platforms() -> list[Platform]:
    """Platforms to set up (the module of each platform overrides it)."""
    return [Platform.MEDIA_PLAYER]


@pytest.fixture(autouse=True)
def mock_platforms(platforms: list[Platform]) -> Generator[None]:
    """Set up the platforms under test only.

    The media player alone follows no setting; the other platforms follow the
    settings of all the real entity descriptions, as in production.
    """
    descriptions = () if platforms == [Platform.MEDIA_PLAYER] else ENTITY_DESCRIPTIONS
    with (
        patch("custom_components.kef_connector.PLATFORMS", platforms),
        patch("custom_components.kef_connector.ENTITY_DESCRIPTIONS", descriptions),
    ):
        yield


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable the entities disabled by default (snapshots of every entity)."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Do not set up the config entries created by the config flow."""
    with patch(
        "custom_components.kef_connector.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def mock_clients() -> dict[str, MagicMock]:
    """Mocked speakers, by host (nothing answers at other addresses)."""
    return {}


@pytest.fixture
def mock_kef_client_class(
    mock_clients: dict[str, MagicMock],
) -> Generator[MagicMock]:
    """Patch ``KefAsyncClient`` where the integration imports it."""
    with (
        patch(
            "custom_components.kef_connector.KefAsyncClient", autospec=True
        ) as client_class,
        patch(
            "custom_components.kef_connector.config_flow.KefAsyncClient",
            new=client_class,
        ),
    ):
        client_class.side_effect = lambda host, **_: (
            mock_clients.get(host) or unreachable_client(host)
        )
        yield client_class


@pytest.fixture
def mock_kef_client(
    mock_kef_client_class: MagicMock, mock_clients: dict[str, MagicMock]
) -> MagicMock:
    """The user's LS50 Wireless II, playing Spotify."""
    client = make_client(HOST, device_info(), speaker_state())
    mock_clients[HOST] = client
    return client


@pytest.fixture
def mock_watch(mock_kef_client: MagicMock) -> WatchController:
    """Push states to the LS50 Wireless II."""
    return mock_kef_client.watch_controller


@pytest.fixture
def second_kef_client(
    mock_kef_client_class: MagicMock, mock_clients: dict[str, MagicMock]
) -> MagicMock:
    """A second speaker (LSX II), on the optical input."""
    client = make_client(
        HOST_2,
        device_info_2(),
        speaker_state(
            source=Source.OPTICAL, name=NAME_2, player=None, position_ms=None
        ),
    )
    mock_clients[HOST_2] = client
    return client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Config entry of the LS50 Wireless II."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        unique_id=UNIQUE_ID,
        data={CONF_HOST: HOST},
    )


@pytest.fixture
def second_config_entry() -> MockConfigEntry:
    """Config entry of the LSX II."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=NAME_2,
        unique_id=UNIQUE_ID_2,
        data={CONF_HOST: HOST_2},
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> MockConfigEntry:
    """Set up the LS50 Wireless II."""
    await setup_integration(hass, mock_config_entry)
    return mock_config_entry


@pytest.fixture
def speaker_values() -> dict[str, Any]:
    """Values the speaker returns for each path (tests may change them)."""
    return dict(SPEAKER_VALUES)


@pytest.fixture
def settings_client(
    mock_kef_client: MagicMock, speaker_values: dict[str, Any]
) -> MagicMock:
    """The LS50 Wireless II with its settings and EQ descriptors."""
    mock_kef_client.get_eq_descriptors.return_value = dict(EQ_DESCRIPTORS_LS50WII)
    mock_kef_client.get_eq_ranges.return_value = dict(EQ_RANGES_LS50WII)
    answer_settings(mock_kef_client, speaker_values)
    return mock_kef_client


@pytest.fixture
async def init_settings(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    settings_client: MagicMock,
) -> MockConfigEntry:
    """Set up the LS50 Wireless II with its settings."""
    await setup_integration(hass, mock_config_entry)
    return mock_config_entry
