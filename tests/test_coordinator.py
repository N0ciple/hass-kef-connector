"""Tests of the coordinator and base entity of KEF Connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.kef_connector.const import DOMAIN
from custom_components.kef_connector.entity import (
    KefEntity,
    KefEntityDescription,
    followed_paths,
    is_supported,
    kef_command,
)
from custom_components.kef_connector.setting_entity import (
    KefSettingEntity,
    KefSettingEntityDescription,
)
from pykefcontrol import (
    Capabilities,
    Feature,
    KefApiError,
    KefConnectionError,
    Settings,
    paths,
)
from pykefcontrol.eq import DEFAULT_RANGES

from .common import (
    EQ_DESCRIPTORS,
    EQ_RANGES,
    WatchController,
    device_info,
    setup_integration,
    speaker_state,
)
from .const import EQ_PROFILE_V1, UNIQUE_ID

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

STARTUP_TONE = Settings.STARTUP_TONE
MAXIMUM_VOLUME = Settings.MAXIMUM_VOLUME


async def test_eq_ranges_from_speaker(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_kef_client: MagicMock
) -> None:
    """EQ ranges and choices are read from the speaker at setup."""
    coordinator = init_integration.runtime_data
    mock_kef_client.get_eq_ranges.assert_awaited_once()
    mock_kef_client.get_eq_descriptors.assert_awaited_once()
    assert coordinator.eq_ranges == EQ_RANGES
    assert coordinator.eq_descriptors == EQ_DESCRIPTORS


async def test_eq_descriptors_unreadable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> None:
    """No EQ choices when the speaker does not tell them (ranges: library's)."""
    mock_kef_client.get_eq_descriptors.side_effect = KefApiError(404, "Not found")
    mock_kef_client.get_eq_ranges.return_value = dict(DEFAULT_RANGES)
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert coordinator.eq_descriptors == {}
    assert coordinator.eq_ranges == DEFAULT_RANGES


async def test_no_eq_profile(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
) -> None:
    """No EQ ranges nor choices to read without EQ profile."""
    mock_kef_client.get_eq_version.return_value = None
    await setup_integration(hass, mock_config_entry)
    mock_kef_client.get_eq_ranges.assert_not_called()
    mock_kef_client.get_eq_descriptors.assert_not_called()
    assert mock_config_entry.runtime_data.eq_ranges == DEFAULT_RANGES


async def test_eq_profile_v1(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    mock_watch: WatchController,
) -> None:
    """Old firmware: the EQ profile in indices (v1) is followed."""
    mock_kef_client.get_eq_version.return_value = 1
    mock_kef_client.get_state.return_value = speaker_state(
        extra={paths.EQ_PROFILE: EQ_PROFILE_V1}
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert coordinator.extra_paths == (paths.EQ_PROFILE,)
    assert mock_watch.calls == [(paths.EQ_PROFILE,)]
    mock_kef_client.get_eq_ranges.assert_awaited_once()
    mock_kef_client.get_eq_descriptors.assert_not_called()
    profile = coordinator.eq_profile
    assert profile is not None
    assert profile.version == 1
    assert profile.balance == 0

    await mock_watch.push(hass, speaker_state(extra={paths.EQ_PROFILE: None}))
    assert coordinator.eq_profile is None


async def test_eq_profile_invalid(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_watch: WatchController
) -> None:
    """An EQ profile that cannot be parsed is ignored."""
    await mock_watch.push(hass, speaker_state(extra={paths.EQ_PROFILE_V2: "garbage"}))
    assert init_integration.runtime_data.eq_profile is None


@pytest.mark.parametrize(
    ("extra", "startup_tone", "maximum_volume"),
    [
        ({STARTUP_TONE.path: True, MAXIMUM_VOLUME.path: 80}, True, 80),
        ({STARTUP_TONE.path: False, MAXIMUM_VOLUME.path: 80.0}, False, 80),
        ({STARTUP_TONE.path: "yes", MAXIMUM_VOLUME.path: "loud"}, None, None),
        ({STARTUP_TONE.path: None}, None, None),
        ({}, None, None),
    ],
)
async def test_settings(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_watch: WatchController,
    extra: dict[str, Any],
    startup_tone: bool | None,
    maximum_volume: int | None,
) -> None:
    """Followed settings are decoded; unknown or invalid values give None."""
    await mock_watch.push(hass, speaker_state(extra=extra))
    coordinator = init_integration.runtime_data
    assert coordinator.setting(STARTUP_TONE) is startup_tone
    assert coordinator.setting(MAXIMUM_VOLUME) == maximum_volume
    assert coordinator.has_value(STARTUP_TONE.path) is (
        extra.get(STARTUP_TONE.path) is not None
    )


async def test_writes(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_kef_client: MagicMock
) -> None:
    """Writes go to the client, errors are translated."""
    coordinator = init_integration.runtime_data
    await coordinator.async_set_setting(STARTUP_TONE, False)
    mock_kef_client.set_setting.assert_awaited_once_with(STARTUP_TONE, False)
    await coordinator.async_update_eq_profile(treble=1.0)
    mock_kef_client.update_eq_profile.assert_awaited_once_with(treble=1.0)

    mock_kef_client.set_setting.side_effect = KefConnectionError("timeout")
    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_set_setting(STARTUP_TONE, True)
    assert err.value.translation_key == "communication_error"
    mock_kef_client.update_eq_profile.side_effect = TypeError("unknown field")
    with pytest.raises(ServiceValidationError) as err:
        await coordinator.async_update_eq_profile(bass=1)
    assert err.value.translation_key == "invalid_value"


# --- base entity ------------------------------------------------------------------


EQ_ONLY = KefEntityDescription(
    key="treble", supported_fn=lambda c: c.supports(Feature.EQ_PROFILE)
)
TONE = KefEntityDescription(key="startup_tone", setting=STARTUP_TONE)
USB = KefEntityDescription(
    key="usb_charging",
    setting=Settings.USB_CHARGING,
    supported_fn=lambda c: c.supports(Feature.USB_CHARGING),
)


async def test_followed_paths(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Only the settings of supported descriptions are followed."""
    capabilities: Capabilities = init_integration.runtime_data.capabilities
    assert followed_paths((EQ_ONLY, TONE, USB), capabilities) == [STARTUP_TONE.path]


async def test_is_supported(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_watch: WatchController
) -> None:
    """Entities need a supported feature and a value read from the speaker."""
    coordinator = init_integration.runtime_data
    assert is_supported(coordinator, EQ_ONLY)
    assert not is_supported(coordinator, USB)
    assert not is_supported(coordinator, TONE)  # not exposed by the speaker
    await mock_watch.push(hass, speaker_state(extra={STARTUP_TONE.path: True}))
    assert is_supported(coordinator, TONE)


class _Entity(KefEntity):
    @kef_command
    async def async_fail(self, error: Exception) -> None:
        raise error


async def test_entity(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Entities with a description get a unique id and translated errors."""
    entity = _Entity(init_integration.runtime_data, TONE)
    assert entity.unique_id == f"{UNIQUE_ID}_startup_tone"
    assert entity.entity_description is TONE
    assert entity.device_info["identifiers"] == {(DOMAIN, UNIQUE_ID)}
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_fail(KefApiError(400, "Bad request"))
    assert err.value.translation_key == "command_failed"


async def test_device_without_firmware(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_kef_client: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Unknown firmware: no software version."""
    mock_kef_client.get_device_info.return_value = device_info(firmware=None)
    await setup_integration(hass, mock_config_entry)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, UNIQUE_ID), mock_config_entry.entry_id
    )
    assert device is not None
    assert device.sw_version is None


async def test_setting_entity_unbound(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_kef_client: MagicMock
) -> None:
    """A setting entity bound to no setting nor EQ field has no value to write."""
    entity = KefSettingEntity(
        init_integration.runtime_data, KefSettingEntityDescription(key="nothing")
    )
    assert entity._value is None
    await entity._async_write(True)
    mock_kef_client.set_setting.assert_not_called()
    mock_kef_client.update_eq_profile.assert_not_called()
