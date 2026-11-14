import json

import pytest

from cardgame.loader import UNITS_FILE, load_cards, load_units
from cardgame.models import CardDataError, EnemyAIKind

CARD_JSON = [
    {"id": "strike", "name": "攻擊", "cost": 1, "effects": [{"kind": "damage", "amount": 6}]},
    {"id": "defend", "name": "防禦", "cost": 1, "effects": [{"kind": "shield", "amount": 5}]},
    {"id": "pricey", "name": "貴", "cost": 3, "effects": [{"kind": "damage", "amount": 9}]},
]


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def load_enemy(tmp_path, ai, max_energy=2):
    cards_path = write_json(tmp_path / "cards.json", CARD_JSON)
    units_path = write_json(
        tmp_path / "units.json",
        [{"id": "e", "name": "e", "max_hp": 10, "max_energy": max_energy, "ai": ai}],
    )
    return load_units(units_path, load_cards(cards_path))["e"]


def test_sequence_ai_parses_card_ids_in_order(tmp_path):
    enemy = load_enemy(tmp_path, {"type": "sequence", "actions": ["strike", "defend"]})
    assert enemy.ai.kind is EnemyAIKind.SEQUENCE
    assert [a.card.id for a in enemy.ai.actions] == ["strike", "defend"]
    assert all(a.weight == 1 for a in enemy.ai.actions)


def test_reveal_intent_defaults_to_hidden(tmp_path):
    enemy = load_enemy(tmp_path, {"type": "sequence", "actions": ["strike"]})
    assert enemy.ai.reveal_intent is False


def test_reveal_intent_can_be_turned_on(tmp_path):
    enemy = load_enemy(tmp_path, {"type": "sequence", "actions": ["strike"], "reveal_intent": True})
    assert enemy.ai.reveal_intent is True


def test_weighted_ai_parses_card_and_weight_objects(tmp_path):
    enemy = load_enemy(
        tmp_path,
        {"type": "weighted", "actions": [{"card": "strike", "weight": 3}, {"card": "defend"}]},
    )
    assert enemy.ai.kind is EnemyAIKind.WEIGHTED
    assert [(a.card.id, a.weight) for a in enemy.ai.actions] == [("strike", 3), ("defend", 1)]


def test_unknown_ai_type_is_rejected(tmp_path):
    with pytest.raises(CardDataError, match="unknown type"):
        load_enemy(tmp_path, {"type": "random", "actions": ["strike"]})


def test_ai_action_referencing_unknown_card_is_rejected(tmp_path):
    with pytest.raises(CardDataError, match="unknown card"):
        load_enemy(tmp_path, {"type": "sequence", "actions": ["ghost"]})


def test_ai_with_no_actions_is_rejected(tmp_path):
    with pytest.raises(CardDataError):
        load_enemy(tmp_path, {"type": "sequence", "actions": []})


def test_ai_unknown_keys_are_rejected(tmp_path):
    with pytest.raises(CardDataError, match="unknown keys"):
        load_enemy(tmp_path, {"type": "sequence", "actions": ["strike"], "speed": 2})


def test_ai_action_unknown_keys_are_rejected(tmp_path):
    with pytest.raises(CardDataError, match="unknown keys"):
        load_enemy(tmp_path, {"type": "weighted", "actions": [{"card": "strike", "chance": 2}]})


def test_weight_on_a_sequence_action_is_rejected(tmp_path):
    with pytest.raises(CardDataError, match="only valid for type 'weighted'"):
        load_enemy(tmp_path, {"type": "sequence", "actions": [{"card": "strike", "weight": 2}]})


def test_zero_weight_is_rejected(tmp_path):
    with pytest.raises(CardDataError):
        load_enemy(tmp_path, {"type": "weighted", "actions": [{"card": "strike", "weight": 0}]})


def test_ai_card_costing_more_than_enemy_energy_is_rejected(tmp_path):
    with pytest.raises(CardDataError, match="more than max_energy"):
        load_enemy(tmp_path, {"type": "sequence", "actions": ["pricey"]}, max_energy=2)


def test_unit_cannot_have_both_a_deck_and_an_ai(tmp_path):
    cards_path = write_json(tmp_path / "cards.json", CARD_JSON)
    units_path = write_json(
        tmp_path / "units.json",
        [
            {
                "id": "e",
                "name": "e",
                "max_hp": 10,
                "max_energy": 2,
                "deck": ["strike"],
                "ai": {"type": "sequence", "actions": ["strike"]},
            }
        ],
    )
    with pytest.raises(CardDataError, match="either a deck or an ai"):
        load_units(units_path, load_cards(cards_path))


def test_real_units_file_defines_slime_and_cultist_ai():
    units = load_units(UNITS_FILE)
    slime = units["slime"]
    assert slime.ai.kind is EnemyAIKind.SEQUENCE
    assert slime.ai.reveal_intent is True
    assert [a.card.id for a in slime.ai.actions] == ["strike", "defend"]

    cultist = units["cultist"]
    assert cultist.ai.kind is EnemyAIKind.WEIGHTED
    assert cultist.ai.reveal_intent is False
    assert [(a.card.id, a.weight) for a in cultist.ai.actions] == [("venom", 2), ("strike", 3)]

    assert units["player"].ai is None
