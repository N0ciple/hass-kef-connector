"""Base of the entities showing a speaker setting or an EQ profile field."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .entity import KefEntity, KefEntityDescription, is_supported

if TYPE_CHECKING:
    from collections.abc import Callable

    from pykefcontrol import Capabilities, Feature, Source, SpeakerModel

    from .coordinator import KefCoordinator


@dataclass(frozen=True, kw_only=True)
class KefSettingEntityDescription(KefEntityDescription):
    """Entity bound to a ``setting`` or to the EQ profile field ``eq_field``.

    ``exists_fn`` is checked at setup, once the speaker has been read: an entity is
    created only if the speaker returned its setting, or has an EQ profile.
    """

    eq_field: str | None = None
    exists_fn: Callable[[KefCoordinator], bool] = lambda _: True


def exists(
    coordinator: KefCoordinator, description: KefSettingEntityDescription
) -> bool:
    """Tell whether an entity should be created for this speaker."""
    if description.eq_field is not None and coordinator.eq_profile is None:
        return False
    return is_supported(coordinator, description) and description.exists_fn(coordinator)


def supports(feature: Feature) -> Callable[[Capabilities], bool]:
    """``supported_fn`` of a feature gated by model and firmware."""
    return lambda caps: caps.supports(feature)


def is_model(model: SpeakerModel) -> Callable[[Capabilities], bool]:
    """``supported_fn`` of a model-specific setting."""
    return lambda caps: caps.model == model


def has_source(source: Source) -> Callable[[Capabilities], bool]:
    """``supported_fn`` of a source-specific setting or action."""
    return lambda caps: source in caps.sources


def eq_v2(coordinator: KefCoordinator) -> bool:
    """Fields that only the v2 EQ profile carries."""
    return coordinator.eq_version == 2


class KefSettingEntity(KefEntity):
    """Entity reading and writing a setting or an EQ profile field."""

    entity_description: KefSettingEntityDescription

    @property
    def _value(self) -> Any:
        """Current value (``None`` if unknown)."""
        desc = self.entity_description
        if desc.eq_field is not None:
            profile = self.coordinator.eq_profile
            return None if profile is None else getattr(profile, desc.eq_field)
        return None if desc.setting is None else self.coordinator.setting(desc.setting)

    async def _async_write(self, value: Any) -> None:
        """Write a new value (it comes back through the coordinator's watch)."""
        desc = self.entity_description
        if desc.eq_field is not None:
            await self.coordinator.async_update_eq_profile(**{desc.eq_field: value})
        elif desc.setting is not None:
            await self.coordinator.async_set_setting(desc.setting, value)
