"""Core data structures: Effect, Card, Status, Unit.

Pure data + validation only. No engine logic and no I/O here; loading from
JSON lives in ``cardgame.loader``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CardDataError(ValueError):
    """Raised when card, status or unit data is invalid."""


class EffectKind(str, Enum):
    DAMAGE = "damage"
    SHIELD = "shield"
    DRAW = "draw"
    APPLY_STATUS = "apply_status"


def _require_non_empty_str(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CardDataError(f"{field_name} must be a non-empty string, got {value!r}")


def _require_int(value: object, field_name: str, minimum: int) -> None:
    # bool is a subclass of int; reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise CardDataError(f"{field_name} must be an integer, got {value!r}")
    if value < minimum:
        raise CardDataError(f"{field_name} must be >= {minimum}, got {value}")


@dataclass(frozen=True)
class Effect:
    """One effect of a card.

    ``amount`` is the magnitude for damage, shield and draw. For
    ``apply_status`` it is the number of stacks applied, and ``status`` names
    the status id and ``duration`` the number of turns it lasts.
    """

    kind: EffectKind
    amount: int
    status: str | None = None
    duration: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EffectKind):
            raise CardDataError(f"unknown effect kind: {self.kind!r}")
        _require_int(self.amount, "effect.amount", minimum=1)
        if self.kind is EffectKind.APPLY_STATUS:
            _require_non_empty_str(self.status, "effect.status")
            _require_int(self.duration, "effect.duration", minimum=1)
        else:
            if self.status is not None:
                raise CardDataError(f"effect.status is only valid for apply_status, not {self.kind.value}")
            if self.duration != 0:
                raise CardDataError(f"effect.duration is only valid for apply_status, not {self.kind.value}")


@dataclass(frozen=True)
class Card:
    id: str
    name: str
    cost: int
    effects: tuple[Effect, ...]

    def __post_init__(self) -> None:
        _require_non_empty_str(self.id, "card.id")
        _require_non_empty_str(self.name, "card.name")
        _require_int(self.cost, "card.cost", minimum=0)
        if not self.effects:
            raise CardDataError(f"card {self.id!r} must have at least one effect")
        for effect in self.effects:
            if not isinstance(effect, Effect):
                raise CardDataError(f"card {self.id!r} effects must be Effect objects")


@dataclass
class Status:
    """A status (poison, weak, shield, ...) with stacks and remaining turns."""

    id: str
    name: str
    stacks: int = 0
    duration: int = 0

    def __post_init__(self) -> None:
        _require_non_empty_str(self.id, "status.id")
        _require_non_empty_str(self.name, "status.name")
        _require_int(self.stacks, "status.stacks", minimum=0)
        _require_int(self.duration, "status.duration", minimum=0)


@dataclass
class Unit:
    """A player or enemy: HP, energy, deck and active statuses."""

    id: str
    name: str
    max_hp: int
    max_energy: int
    deck: list[Card] = field(default_factory=list)
    hp: int | None = None
    energy: int | None = None
    statuses: list[Status] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_non_empty_str(self.id, "unit.id")
        _require_non_empty_str(self.name, "unit.name")
        _require_int(self.max_hp, "unit.max_hp", minimum=1)
        _require_int(self.max_energy, "unit.max_energy", minimum=0)
        # None means "not given": start at full HP / full energy.
        if self.hp is None:
            self.hp = self.max_hp
        if self.energy is None:
            self.energy = self.max_energy
        _require_int(self.hp, "unit.hp", minimum=0)
        _require_int(self.energy, "unit.energy", minimum=0)
        if self.hp > self.max_hp:
            raise CardDataError(f"unit {self.id!r} hp {self.hp} exceeds max_hp {self.max_hp}")
        if self.energy > self.max_energy:
            raise CardDataError(f"unit {self.id!r} energy {self.energy} exceeds max_energy {self.max_energy}")
