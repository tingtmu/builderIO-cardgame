import json

import pytest

from cardgame.engine import EFFECT_HANDLERS, HAND_SIZE, SHIELD_STATUS_ID, Battle, BattleError
from cardgame.loader import CARDS_FILE, UNITS_FILE, load_cards, load_units
from cardgame.models import Card, Effect, EffectKind, Unit


def dmg(amount):
    return Effect(kind=EffectKind.DAMAGE, amount=amount)


def shield(amount):
    return Effect(kind=EffectKind.SHIELD, amount=amount)


def draw(amount):
    return Effect(kind=EffectKind.DRAW, amount=amount)


def poison(stacks, duration):
    return Effect(kind=EffectKind.APPLY_STATUS, amount=stacks, status="poison", duration=duration)


def card(card_id, cost, *effects):
    return Card(id=card_id, name=card_id, cost=cost, effects=tuple(effects))


def unit(unit_id, max_hp=50, max_energy=3, deck=()):
    return Unit(id=unit_id, name=unit_id, max_hp=max_hp, max_energy=max_energy, deck=list(deck))


def hand_ids(battle):
    return [c.id for c in battle.hand]


def kinds(battle, turn=None):
    return [e.kind for e in battle.events if turn is None or e.turn == turn]


def make_battle(player_deck, enemy_deck=(), seed=0, hand_size=HAND_SIZE, **unit_kwargs):
    player = unit("player", deck=player_deck, **unit_kwargs)
    enemy = unit("enemy", max_hp=30, max_energy=2, deck=enemy_deck)
    return Battle(player, enemy, seed=seed, hand_size=hand_size)


# ----- turn start and draw -------------------------------------------------


def test_start_begins_turn_one_with_full_energy_and_opening_hand():
    battle = make_battle([card("a", 1, dmg(1))] * 8)
    battle.start()
    assert battle.turn == 1
    assert battle.player.energy == battle.player.max_energy
    assert len(battle.hand) == HAND_SIZE
    assert len(battle.draw_pile) == 8 - HAND_SIZE


def test_start_twice_is_rejected():
    battle = make_battle([card("a", 1, dmg(1))])
    battle.start()
    with pytest.raises(BattleError):
        battle.start()


def test_hand_size_is_configurable():
    battle = Battle(unit("player", deck=[card("a", 0, draw(1))] * 5), unit("enemy"), seed=0, hand_size=2)
    battle.start()
    assert len(battle.hand) == 2


def test_draw_takes_from_pile_when_deck_has_enough_cards():
    deck = [card("a", 1, dmg(1)), card("b", 1, dmg(1)), card("c", 1, dmg(1))]
    battle = make_battle(deck, hand_size=2)
    battle.start()
    assert sorted(hand_ids(battle) + [c.id for c in battle.draw_pile]) == ["a", "b", "c"]


def test_draw_reshuffles_discard_when_draw_pile_is_empty():
    deck = [card("a", 0, dmg(1)), card("b", 0, dmg(1))]
    battle = make_battle(deck, hand_size=2)
    battle.start()
    battle.play_card(0)
    battle.play_card(0)
    assert battle.draw_pile == [] and len(battle.discard_pile) == 2
    battle.end_turn()
    assert len(battle.hand) == 2
    assert battle.discard_pile == []
    assert sorted(hand_ids(battle)) == ["a", "b"]


def test_draw_with_a_single_card_in_total_recycles_it_without_duplicating():
    battle = make_battle([card("a", 0, dmg(1))], hand_size=5)
    battle.start()
    assert hand_ids(battle) == ["a"]
    battle.play_card(0)
    battle.end_turn()
    assert hand_ids(battle) == ["a"]
    assert battle.draw_pile == []


# ----- playing cards -------------------------------------------------------


def test_play_card_removes_card_from_hand_and_pays_energy():
    battle = make_battle([card("a", 1, dmg(1)), card("b", 2, dmg(1))], max_energy=3)
    battle.start()
    index = hand_ids(battle).index("b")
    battle.play_card(index)
    assert "b" not in hand_ids(battle)
    assert battle.player.energy == 1
    assert [c.id for c in battle.discard_pile] == ["b"]


def test_play_card_cost_is_deducted_from_energy():
    battle = make_battle([card("a", 2, dmg(1))] * 3, max_energy=3)
    battle.start()
    battle.play_card(0)
    assert battle.player.energy == 1


def test_play_card_rejects_unaffordable_card_without_changing_state():
    battle = make_battle([card("big", 4, dmg(1))] * 3, max_energy=3)
    battle.start()
    hand_before = list(battle.hand)
    with pytest.raises(BattleError, match="costs 4"):
        battle.play_card(0)
    assert battle.hand == hand_before
    assert battle.player.energy == 3
    assert battle.discard_pile == []


def test_play_card_rejects_bad_index():
    battle = make_battle([card("a", 0, dmg(1))])
    battle.start()
    with pytest.raises(BattleError):
        battle.play_card(1)
    with pytest.raises(BattleError):
        battle.play_card(-1)


def test_play_card_before_start_is_rejected():
    battle = make_battle([card("a", 0, dmg(1))])
    with pytest.raises(BattleError, match="not started"):
        battle.play_card(0)


def test_playing_several_cards_spends_energy_until_it_runs_out():
    battle = make_battle([card("a", 1, dmg(1))] * 5, max_energy=2)
    battle.start()
    battle.play_card(0)
    battle.play_card(0)
    with pytest.raises(BattleError):
        battle.play_card(0)
    assert battle.player.energy == 0


# ----- effect resolution ---------------------------------------------------


def test_damage_reduces_enemy_hp():
    battle = make_battle([card("a", 0, dmg(7))])
    battle.start()
    battle.play_card(0)
    assert battle.enemy.hp == 30 - 7


def test_damage_never_takes_hp_below_zero_and_ends_battle():
    battle = make_battle([card("a", 0, dmg(999))])
    battle.start()
    battle.play_card(0)
    assert battle.enemy.hp == 0
    assert battle.over
    assert battle.winner == "player"


def test_shield_is_granted_to_the_player_and_absorbs_damage_first():
    battle = make_battle([card("guard", 0, shield(5))])
    battle.enemy.deck = [card("hit", 0, dmg(8))]
    battle.start()
    battle.play_card(0)
    assert [(s.id, s.stacks) for s in battle.player.statuses] == [(SHIELD_STATUS_ID, 5)]
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - 3
    assert battle.player.statuses == []


def test_shield_stacks_add_up():
    battle = make_battle([card("guard", 0, shield(3)), card("guard2", 0, shield(4))])
    battle.start()
    battle.play_card(0)
    battle.play_card(0)
    (status,) = battle.player.statuses
    assert status.stacks == 7


def test_damage_larger_than_shield_leaves_remaining_shield_gone_and_hp_reduced():
    battle = make_battle([card("guard", 0, shield(2))])
    battle.enemy.deck = [card("hit", 0, dmg(5))]
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - 3
    assert battle.player.statuses == []


def test_draw_effect_puts_cards_into_hand():
    battle = make_battle([card("pump", 0, draw(2))] * 4, hand_size=1)
    battle.start()
    assert len(battle.hand) == 1
    battle.play_card(0)
    assert len(battle.hand) == 2
    assert len(battle.draw_pile) == 1


def test_apply_status_is_recorded_and_does_not_change_hp():
    battle = make_battle([card("venom", 0, poison(3, 3))])
    battle.start()
    battle.play_card(0)
    assert battle.enemy.hp == battle.enemy.max_hp
    (event,) = [e for e in battle.events if e.kind == "apply_status"]
    assert (event.target, event.amount, event.detail) == ("enemy", 3, "poison:3")


def test_multi_effect_card_resolves_effects_in_order():
    battle = make_battle([card("combo", 0, dmg(4), shield(2))])
    battle.start()
    battle.play_card(0)
    assert [e.kind for e in battle.events if e.turn == 1 and e.kind in ("damage", "shield")] == [
        "damage",
        "shield",
    ]


def test_play_card_event_is_logged_before_its_effects():
    battle = make_battle([card("a", 0, dmg(1))])
    battle.start()
    battle.events.clear()
    battle.play_card(0)
    assert kinds(battle) == ["play_card", "damage"]
    assert battle.events[0].detail == "a"


def test_every_effect_kind_has_a_handler():
    assert set(EFFECT_HANDLERS) == set(EffectKind)


def test_engine_works_with_arbitrary_card_ids(tmp_path):
    # The engine must not special-case card ids: unknown ids with any mix of
    # effects are played just like the example cards.
    path = tmp_path / "cards.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "zz_custom",
                    "name": "自訂",
                    "cost": 0,
                    "effects": [
                        {"kind": "draw", "amount": 1},
                        {"kind": "damage", "amount": 2},
                        {"kind": "shield", "amount": 1},
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    custom = load_cards(path)["zz_custom"]
    battle = make_battle([custom] * 3, hand_size=1)
    battle.enemy.deck = []
    battle.start()
    battle.play_card(0)
    assert battle.enemy.hp == battle.enemy.max_hp - 2
    assert battle.player.statuses[0].stacks == 1
    assert len(battle.hand) == 1


# ----- enemy turn ----------------------------------------------------------


def test_end_turn_runs_enemy_then_status_settle_then_next_draw():
    battle = make_battle([card("a", 0, dmg(1))] * 6, enemy_deck=[card("e", 0, dmg(1))], hand_size=2)
    battle.start()
    battle.events.clear()
    battle.end_turn()
    assert kinds(battle) == ["enemy_play", "damage", "status_settle", "draw", "draw"]
    assert battle.turn == 2
    assert len(battle.hand) == 2


def test_unplayed_hand_is_discarded_at_end_of_turn():
    battle = make_battle([card("a", 0, dmg(1))] * 6, hand_size=3)
    battle.start()
    unplayed = list(battle.hand)
    battle.end_turn()
    assert len(battle.hand) == 3
    assert all(c in battle.discard_pile for c in unplayed)
    assert len(battle.hand) + len(battle.draw_pile) + len(battle.discard_pile) == 6


def test_enemy_damage_hits_player():
    battle = make_battle([card("a", 0, dmg(1))], enemy_deck=[card("e", 0, dmg(6))])
    battle.start()
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - 6


def test_enemy_only_plays_cards_its_energy_can_pay_for():
    # Enemy has 2 energy; the 3-cost card can never be played.
    battle = make_battle([card("a", 0, dmg(1))], enemy_deck=[card("pricey", 3, dmg(40))])
    battle.start()
    for _ in range(5):
        battle.end_turn()
    assert "enemy_play" not in kinds(battle)
    assert battle.player.hp == battle.player.max_hp


def test_enemy_with_empty_deck_does_nothing():
    battle = make_battle([card("a", 0, dmg(1))], enemy_deck=[])
    battle.start()
    battle.end_turn()
    assert "enemy_play" not in kinds(battle)
    assert battle.turn == 2


def test_enemy_energy_refills_each_turn():
    battle = make_battle([card("a", 0, dmg(1))], enemy_deck=[card("e", 2, dmg(1))])
    battle.start()
    battle.end_turn()
    battle.end_turn()
    assert battle.enemy.energy == 0
    assert kinds(battle).count("enemy_play") == 2


def test_enemy_card_is_chosen_with_the_seeded_rng():
    enemy_deck = [card("e1", 0, dmg(1)), card("e2", 0, dmg(2)), card("e3", 0, dmg(3))]
    picks = []
    for seed in range(10):
        battle = make_battle([card("a", 0, dmg(1))], enemy_deck=enemy_deck, seed=seed)
        battle.start()
        battle.end_turn()
        picks.append(next(e.detail for e in battle.events if e.kind == "enemy_play"))
    assert len(set(picks)) > 1


def test_battle_ends_when_enemy_dies_so_enemy_does_not_act():
    battle = make_battle([card("finish", 0, dmg(30))], enemy_deck=[card("e", 0, dmg(1))])
    battle.start()
    battle.play_card(0)
    assert battle.winner == "player"
    with pytest.raises(BattleError, match="over"):
        battle.end_turn()
    assert "enemy_play" not in kinds(battle)


def test_player_death_during_enemy_turn_ends_battle_with_enemy_winner():
    battle = make_battle([card("a", 0, dmg(1))], enemy_deck=[card("e", 0, dmg(999))])
    battle.start()
    battle.end_turn()
    assert battle.player.hp == 0
    assert battle.winner == "enemy"
    assert battle.over
    assert kinds(battle).count("status_settle") == 0
    with pytest.raises(BattleError):
        battle.play_card(0)


def test_end_turn_before_start_is_rejected():
    battle = make_battle([card("a", 0, dmg(1))])
    with pytest.raises(BattleError):
        battle.end_turn()


def test_winner_is_none_while_battle_is_ongoing():
    battle = make_battle([card("a", 0, dmg(1))])
    battle.start()
    assert battle.winner is None
    assert not battle.over


def test_unit_hp_and_energy_default_to_full_in_battle():
    player = Unit(id="player", name="p", max_hp=10, max_energy=2, deck=[card("a", 0, dmg(1))])
    enemy = Unit(id="enemy", name="e", max_hp=10, max_energy=1)
    battle = Battle(player, enemy, seed=1)
    battle.start()
    assert battle.player.hp == 10
    assert battle.player.energy == 2


# ----- reproducibility -----------------------------------------------------


def run_scripted(player, enemy, seed, max_turns=50):
    """Play the first affordable card each turn until the battle ends."""
    battle = Battle(player, enemy, seed=seed)
    battle.start()
    while not battle.over and battle.turn < max_turns:
        for index, candidate in enumerate(battle.hand):
            if candidate.cost <= battle.player.energy:
                battle.play_card(index)
                break
        if battle.over:
            break
        battle.end_turn()
    return battle


def fresh_units():
    cards = load_cards(CARDS_FILE)
    player = load_units(UNITS_FILE, cards)["player"]
    enemy_deck = [cards["strike"], cards["defend"], cards["venom"]]
    enemy = Unit(id="slime", name="slime", max_hp=40, max_energy=2, deck=enemy_deck)
    return player, enemy


def snapshot(battle):
    return (
        battle.turn,
        battle.winner,
        battle.player.hp,
        battle.enemy.hp,
        [(e.turn, e.actor, e.kind, e.target, e.amount, e.detail) for e in battle.events],
    )


def test_same_seed_gives_identical_battle():
    results = []
    for _ in range(2):
        player, enemy = fresh_units()
        results.append(snapshot(run_scripted(player, enemy, seed=12345)))
    assert results[0] == results[1]


def test_same_seed_reproduces_result_for_many_seeds():
    for seed in range(20):
        first = snapshot(run_scripted(*fresh_units(), seed=seed))
        second = snapshot(run_scripted(*fresh_units(), seed=seed))
        assert first == second


def test_different_seeds_can_produce_different_draw_orders():
    orders = set()
    for seed in range(10):
        player, enemy = fresh_units()
        battle = Battle(player, enemy, seed=seed)
        battle.start()
        orders.add(tuple(hand_ids(battle)))
    assert len(orders) > 1
