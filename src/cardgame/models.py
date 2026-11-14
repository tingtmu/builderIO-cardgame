"""Core data structures: Effect, Card, Status, Unit.

Pure data + validation only. No engine logic and no I/O here; loading from
JSON lives in ``cardgame.loader``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction


class CardDataError(ValueError):
    """Raised when card, status or unit data is invalid."""


class EffectKind(str, Enum):
    DAMAGE = "damage"
    SHIELD = "shield"
    DRAW = "draw"
    APPLY_STATUS = "apply_status"


class StatusLifetime(str, Enum):
    # Duration counts down at each status settle; removed when it reaches 0.
    TURNS = "turns"
    # Duration is ignored; removed when the owner's next turn begins.
    OWNER_TURN_START = "owner_turn_start"


def _require_non_empty_str(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CardDataError(f"{field_name} must be a non-empty string, got {value!r}")


def _require_int(value: object, field_name: str, minimum: int) -> None:
    # bool is a subclass of int; reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise CardDataError(f"{field_name} must be an integer, got {value!r}")
    if value < minimum:
        raise CardDataError(f"{field_name} must be >= {minimum}, got {value}")


def _require_bool(value: object, field_name: str) -> None:
    if not isinstance(value, bool):
        raise CardDataError(f"{field_name} must be a boolean, got {value!r}")


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


@dataclass(frozen=True)
class StatusDef:
    """Behaviour of one status id, read from ``data/statuses.json``.

    - ``damage_per_stack``: HP lost by the afflicted unit at each settle, per
      stack. This is direct HP loss and bypasses absorbing statuses.
    - ``stacks_lost_per_turn``: stacks removed at each settle.
    - ``lifetime``: see ``StatusLifetime``.
    - ``outgoing_damage_multiplier``: scales damage dealt by the afflicted
      unit, rounded down. Stored as an exact ``Fraction``.
    - ``absorbs_damage``: stacks soak up incoming damage before HP is lost.
    """

    id: str
    name: str
    damage_per_stack: int = 0
    stacks_lost_per_turn: int = 0
    lifetime: StatusLifetime = StatusLifetime.TURNS
    outgoing_damage_multiplier: Fraction = Fraction(1)
    absorbs_damage: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        _require_non_empty_str(self.id, "status.id")
        _require_non_empty_str(self.name, "status.name")
        _require_int(self.damage_per_stack, f"status {self.id!r} damage_per_stack", minimum=0)
        _require_int(self.stacks_lost_per_turn, f"status {self.id!r} stacks_lost_per_turn", minimum=0)
        if not isinstance(self.lifetime, StatusLifetime):
            raise CardDataError(f"status {self.id!r} has unknown lifetime {self.lifetime!r}")
        if not isinstance(self.outgoing_damage_multiplier, Fraction) or self.outgoing_damage_multiplier < 0:
            raise CardDataError(
                f"status {self.id!r} outgoing_damage_multiplier must be a non-negative number, "
                f"got {self.outgoing_damage_multiplier!r}"
            )
        _require_bool(self.absorbs_damage, f"status {self.id!r} absorbs_damage")
        if not isinstance(self.description, str):
            raise CardDataError(f"status {self.id!r} description must be a string")


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
