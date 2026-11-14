"""Load cards and units from JSON data files.

Adding a card means editing ``data/cards.json`` only; nothing here knows
about specific card ids.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cardgame.models import Card, CardDataError, Effect, EffectKind, Status, Unit

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CARDS_FILE = DATA_DIR / "cards.json"
UNITS_FILE = DATA_DIR / "units.json"


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
