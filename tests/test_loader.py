import json

import pytest

from cardgame.loader import CARDS_FILE, UNITS_FILE, load_cards, load_units
from cardgame.models import CardDataError, EffectKind


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_real_cards_file_loads_three_example_cards():
    cards = load_cards(CARDS_FILE)
    assert set(cards) == {"strike", "defend", "venom"}


def test_example_cards_have_expected_effects():
    cards = load_cards(CARDS_FILE)

    strike = cards["strike"]
    assert strike.cost == 1
    assert [(e.kind, e.amount) for e in strike.effects] == [(EffectKind.DAMAGE, 6)]

    defend = cards["defend"]
    assert [(e.kind, e.amount) for e in defend.effects] == [(EffectKind.SHIELD, 5)]

    venom = cards["venom"]
    (effect,) = venom.effects
    assert effect.kind is EffectKind.APPLY_STATUS
    assert effect.status == "poison"
    assert effect.amount == 3
    assert effect.duration == 3


def test_real_units_file_loads_player_with_deck_of_known_cards():
    units = load_units(UNITS_FILE)
    player = units["player"]
    cards = load_cards(CARDS_FILE)
    assert player.hp == player.max_hp == 80
    assert player.energy == player.max_energy == 3
    assert all(card in cards.values() for card in player.deck)
    assert [c.id for c in player.deck] == ["strike", "strike", "defend", "defend", "venom"]


def test_adding_a_card_only_needs_a_data_file(tmp_path):
    # Adding a card is a data change: a new entry in a JSON file is enough.
    path = write_json(
        tmp_path / "cards.json",
        [
            {
                "id": "heavy_strike",
                "name": "重擊",
                "cost": 2,
                "effects": [{"kind": "damage", "amount": 12}],
            },
            {
                "id": "weak_touch",
                "name": "虛弱",
                "cost": 0,
                "effects": [
                    {"kind": "apply_status", "status": "weak", "stacks": 1, "duration": 2},
                    {"kind": "draw", "amount": 1},
                ],
            },
        ],
    )
    cards = load_cards(path)
    assert cards["heavy_strike"].cost == 2
    assert len(cards["weak_touch"].effects) == 2


def test_unit_deck_is_resolved_against_cards(tmp_path):
    cards_path = write_json(
        tmp_path / "cards.json",
        [{"id": "strike", "name": "攻擊", "cost": 1, "effects": [{"kind": "damage", "amount": 6}]}],
    )
    units_path = write_json(
        tmp_path / "units.json",
        [{"id": "enemy", "name": "史萊姆", "max_hp": 20, "max_energy": 1, "deck": ["strike"]}],
    )
    units = load_units(units_path, load_cards(cards_path))
    assert units["enemy"].deck[0].id == "strike"


def test_unit_with_unknown_card_in_deck_is_rejected(tmp_path):
    cards_path = write_json(tmp_path / "cards.json", [])
    units_path = write_json(
        tmp_path / "units.json",
        [{"id": "enemy", "name": "x", "max_hp": 1, "max_energy": 1, "deck": ["ghost"]}],
    )
    with pytest.raises(CardDataError, match="ghost"):
        load_units(units_path, load_cards(cards_path))


def test_unit_status_list_is_loaded(tmp_path):
    path = write_json(
        tmp_path / "units.json",
        [
            {
                "id": "p",
                "name": "p",
                "max_hp": 10,
                "max_energy": 3,
                "deck": [],
                "statuses": [{"id": "shield", "name": "護盾", "stacks": 4, "duration": 1}],
            }
        ],
    )
    units = load_units(path, cards={})
    (status,) = units["p"].statuses
    assert (status.id, status.stacks, status.duration) == ("shield", 4, 1)


def test_duplicate_card_id_is_rejected(tmp_path):
    card = {"id": "a", "name": "a", "cost": 1, "effects": [{"kind": "draw", "amount": 1}]}
    path = write_json(tmp_path / "cards.json", [card, card])
    with pytest.raises(CardDataError, match="duplicate card id 'a'"):
        load_cards(path)


def test_unknown_effect_kind_is_rejected(tmp_path):
    path = write_json(
        tmp_path / "cards.json",
        [{"id": "a", "name": "a", "cost": 1, "effects": [{"kind": "teleport", "amount": 1}]}],
    )
    with pytest.raises(CardDataError, match="unknown kind"):
        load_cards(path)


def test_missing_key_is_rejected(tmp_path):
    path = write_json(tmp_path / "cards.json", [{"id": "a", "name": "a", "effects": []}])
    with pytest.raises(CardDataError, match="cost"):
        load_cards(path)


def test_invalid_json_is_rejected(tmp_path):
    path = tmp_path / "cards.json"
    path.write_text("[{", encoding="utf-8")
    with pytest.raises(CardDataError, match="invalid JSON"):
        load_cards(path)
