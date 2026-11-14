"""Load cards and units from JSON data files.

Adding a card means editing ``data/cards.json`` only; nothing here knows
about specific card ids.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from cardgame.models import Card, CardDataError, Effect, EffectKind, Status, StatusDef, StatusLifetime, Unit

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CARDS_FILE = DATA_DIR / "cards.json"
UNITS_FILE = DATA_DIR / "units.json"
STATUSES_FILE = DATA_DIR / "statuses.json"

_STATUS_DEF_KEYS = frozenset(
    {
        "id",
        "name",
        "description",
        "damage_per_stack",
        "stacks_lost_per_turn",
        "lifetime",
        "outgoing_damage_multiplier",
        "absorbs_damage",
    }
)


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise CardDataError(f"{path}: invalid JSON: {exc}") from exc


def _as_object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CardDataError(f"{where} must be a JSON object")
    return value


def _as_list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise CardDataError(f"{where} must be a JSON array")
    return value


def _get(obj: dict[str, Any], key: str, where: str) -> Any:
    if key not in obj:
        raise CardDataError(f"{where}: missing required key {key!r}")
    return obj[key]


def parse_effect(raw: Any) -> Effect:
    obj = _as_object(raw, "effect")
    try:
        kind = EffectKind(_get(obj, "kind", "effect"))
    except ValueError as exc:
        raise CardDataError(f"effect: unknown kind {obj.get('kind')!r}") from exc
    if kind is EffectKind.APPLY_STATUS:
        return Effect(
            kind=kind,
            amount=_get(obj, "stacks", "effect"),
            status=_get(obj, "status", "effect"),
            duration=_get(obj, "duration", "effect"),
        )
    return Effect(kind=kind, amount=_get(obj, "amount", "effect"))


def parse_card(raw: Any) -> Card:
    obj = _as_object(raw, "card")
    card_id = _get(obj, "id", "card")
    where = f"card {card_id!r}"
    effects = tuple(parse_effect(e) for e in _as_list(_get(obj, "effects", where), f"{where}.effects"))
    return Card(
        id=card_id,
        name=_get(obj, "name", where),
        cost=_get(obj, "cost", where),
        effects=effects,
    )


def load_cards(path: Path = CARDS_FILE) -> dict[str, Card]:
    """Return all cards keyed by id. Duplicate ids are an error."""
    cards: dict[str, Card] = {}
    for raw in _as_list(_read_json(path), f"{path}"):
        card = parse_card(raw)
        if card.id in cards:
            raise CardDataError(f"duplicate card id {card.id!r} in {path}")
        cards[card.id] = card
    return cards


def parse_status_def(raw: Any) -> StatusDef:
    obj = _as_object(raw, "status definition")
    status_id = _get(obj, "id", "status definition")
    where = f"status {status_id!r}"
    unknown = set(obj) - _STATUS_DEF_KEYS
    if unknown:
        raise CardDataError(f"{where}: unknown keys {sorted(unknown)}")
    lifetime_raw = obj.get("lifetime", StatusLifetime.TURNS.value)
    try:
        lifetime = StatusLifetime(lifetime_raw)
    except ValueError as exc:
        raise CardDataError(f"{where}: unknown lifetime {lifetime_raw!r}") from exc
    multiplier = obj.get("outgoing_damage_multiplier", 1)
    if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
        raise CardDataError(f"{where}: outgoing_damage_multiplier must be a number, got {multiplier!r}")
    return StatusDef(
        id=status_id,
        name=_get(obj, "name", where),
        description=obj.get("description", ""),
        damage_per_stack=obj.get("damage_per_stack", 0),
        stacks_lost_per_turn=obj.get("stacks_lost_per_turn", 0),
        lifetime=lifetime,
        # str() keeps the decimal literal exact (0.75 -> 3/4) instead of a binary float.
        outgoing_damage_multiplier=Fraction(str(multiplier)),
        absorbs_damage=obj.get("absorbs_damage", False),
    )


def load_statuses(path: Path = STATUSES_FILE) -> dict[str, StatusDef]:
    """Return all status definitions keyed by id. Duplicate ids are an error."""
    statuses: dict[str, StatusDef] = {}
    for raw in _as_list(_read_json(path), f"{path}"):
        definition = parse_status_def(raw)
        if definition.id in statuses:
            raise CardDataError(f"duplicate status id {definition.id!r} in {path}")
        statuses[definition.id] = definition
    return statuses


def parse_status(raw: Any) -> Status:
    obj = _as_object(raw, "status")
    return Status(
        id=_get(obj, "id", "status"),
        name=_get(obj, "name", "status"),
        stacks=obj.get("stacks", 0),
        duration=obj.get("duration", 0),
    )


def parse_unit(raw: Any, cards: dict[str, Card]) -> Unit:
    obj = _as_object(raw, "unit")
    unit_id = _get(obj, "id", "unit")
    where = f"unit {unit_id!r}"
    deck: list[Card] = []
    for card_id in _as_list(_get(obj, "deck", where), f"{where}.deck"):
        if card_id not in cards:
            raise CardDataError(f"{where}: deck references unknown card {card_id!r}")
        deck.append(cards[card_id])
    statuses = [parse_status(s) for s in _as_list(obj.get("statuses", []), f"{where}.statuses")]
    return Unit(
        id=unit_id,
        name=_get(obj, "name", where),
        max_hp=_get(obj, "max_hp", where),
        max_energy=_get(obj, "max_energy", where),
        deck=deck,
        statuses=statuses,
    )


def load_units(path: Path = UNITS_FILE, cards: dict[str, Card] | None = None) -> dict[str, Unit]:
    """Return all units keyed by id. Deck entries must reference known card ids."""
    if cards is None:
        cards = load_cards()
    units: dict[str, Unit] = {}
    for raw in _as_list(_read_json(path), f"{path}"):
        unit = parse_unit(raw, cards)
        if unit.id in units:
            raise CardDataError(f"duplicate unit id {unit.id!r} in {path}")
        units[unit.id] = unit
    return units
