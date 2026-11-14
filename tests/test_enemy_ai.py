import random

import pytest

from cardgame.ai import EnemyBrain
from cardgame.engine import Battle, BattleError
from cardgame.models import AIAction, AIDef, Card, CardDataError, Effect, EffectKind, EnemyAIKind, Unit


def dmg(amount):
    return Effect(kind=EffectKind.DAMAGE, amount=amount)


def card(card_id, cost, *effects):
    return Card(id=card_id, name=card_id, cost=cost, effects=tuple(effects))


def seq(*cards, reveal=False):
    return AIDef(kind=EnemyAIKind.SEQUENCE, actions=tuple(AIAction(c) for c in cards), reveal_intent=reveal)


def weighted(*pairs, reveal=False):
    actions = tuple(AIAction(c, weight=w) for c, w in pairs)
    return AIDef(kind=EnemyAIKind.WEIGHTED, actions=actions, reveal_intent=reveal)


def battle_with(ai, seed=0, enemy_max_energy=2, player_deck=None):
    deck = player_deck if player_deck is not None else [card("p", 0, dmg(1))] * 5
    player = Unit(id="player", name="p", max_hp=200, max_energy=3, deck=list(deck))
    enemy = Unit(id="enemy", name="e", max_hp=500, max_energy=enemy_max_energy, ai=ai)
    return Battle(player, enemy, seed=seed)


def enemy_plays(battle):
    return [e.detail for e in battle.events if e.kind == "enemy_play"]


# ----- EnemyBrain: sequence -------------------------------------------------


def test_sequence_brain_cycles_through_actions_in_order():
    a, b, c = card("a", 0, dmg(1)), card("b", 0, dmg(1)), card("c", 0, dmg(1))
    brain = EnemyBrain(seq(a, b, c))
    rng = random.Random(0)
    picks = [brain.next_card(rng).id for _ in range(7)]
    assert picks == ["a", "b", "c", "a", "b", "c", "a"]


def test_sequence_brain_does_not_consume_the_rng():
    brain = EnemyBrain(seq(card("a", 0, dmg(1)), card("b", 0, dmg(1))))
    rng = random.Random(42)
    before = rng.getstate()
    for _ in range(5):
        brain.next_card(rng)
    assert rng.getstate() == before


def test_single_action_sequence_repeats_the_same_card():
    brain = EnemyBrain(seq(card("only", 0, dmg(1))))
    rng = random.Random(0)
    assert {brain.next_card(rng).id for _ in range(4)} == {"only"}


# ----- EnemyBrain: weighted -------------------------------------------------


def test_weighted_brain_is_reproducible_for_the_same_seed():
    ai = weighted((card("a", 0, dmg(1)), 1), (card("b", 0, dmg(1)), 3))

    def run(seed):
        brain = EnemyBrain(ai)
        rng = random.Random(seed)
        return [brain.next_card(rng).id for _ in range(30)]

    assert run(5) == run(5)


def test_weighted_brain_follows_the_weights_roughly():
    ai = weighted((card("rare", 0, dmg(1)), 1), (card("common", 0, dmg(1)), 3))
    brain = EnemyBrain(ai)
    rng = random.Random(1)
    picks = [brain.next_card(rng).id for _ in range(4000)]
    share_common = picks.count("common") / len(picks)
    assert 0.70 < share_common < 0.80  # expected 0.75


def test_weighted_brain_only_returns_listed_cards():
    ai = weighted((card("x", 0, dmg(1)), 2), (card("y", 0, dmg(1)), 2))
    brain = EnemyBrain(ai)
    rng = random.Random(9)
    assert {brain.next_card(rng).id for _ in range(50)} == {"x", "y"}


# ----- model validation -----------------------------------------------------


def test_ai_def_rejects_empty_actions():
    with pytest.raises(CardDataError):
        AIDef(kind=EnemyAIKind.SEQUENCE, actions=())


def test_ai_action_weight_must_be_positive_integer():
    with pytest.raises(CardDataError):
        AIAction(card("a", 0, dmg(1)), weight=0)
    with pytest.raises(CardDataError):
        AIAction(card("a", 0, dmg(1)), weight=True)


def test_sequence_actions_cannot_carry_a_weight():
    with pytest.raises(CardDataError):
        AIDef(kind=EnemyAIKind.SEQUENCE, actions=(AIAction(card("a", 0, dmg(1)), weight=2),))


def test_unit_rejects_an_ai_action_it_cannot_afford():
    with pytest.raises(CardDataError):
        Unit(id="e", name="e", max_hp=10, max_energy=1, ai=seq(card("pricey", 2, dmg(1))))


def test_unit_without_ai_has_no_intent_and_is_valid():
    unit = Unit(id="e", name="e", max_hp=10, max_energy=1)
    assert unit.ai is None


# ----- battle: enemy plays the pattern -------------------------------------


def test_enemy_plays_its_sequence_one_card_per_turn():
    battle = battle_with(seq(card("a", 0, dmg(1)), card("b", 0, dmg(2))))
    battle.start()
    for _ in range(4):
        battle.end_turn()
    assert enemy_plays(battle) == ["a", "b", "a", "b"]


def test_enemy_plays_weighted_pattern_reproducibly():
    ai = weighted((card("a", 0, dmg(1)), 1), (card("b", 0, dmg(1)), 4))

    def run(seed):
        battle = battle_with(ai, seed=seed)
        battle.start()
        for _ in range(10):
            battle.end_turn()
        return enemy_plays(battle)

    assert run(3) == run(3)


def test_enemy_with_no_ai_takes_no_action():
    player = Unit(id="player", name="p", max_hp=20, max_energy=3, deck=[card("p", 0, dmg(1))])
    enemy = Unit(id="enemy", name="e", max_hp=20, max_energy=1)
    battle = Battle(player, enemy, seed=0)
    battle.start()
    battle.end_turn()
    assert enemy_plays(battle) == []
    assert battle.player.hp == battle.player.max_hp
    assert battle.enemy_intent is None


def test_enemy_energy_is_spent_on_its_chosen_card():
    battle = battle_with(seq(card("pay", 2, dmg(1))))
    battle.start()
    battle.end_turn()
    assert battle.enemy.energy == 0


# ----- battle: intent -------------------------------------------------------


def test_intent_is_the_first_action_when_the_battle_starts():
    battle = battle_with(seq(card("a", 0, dmg(1)), card("b", 0, dmg(1)), reveal=True))
    battle.start()
    assert battle.enemy_intent.id == "a"


def test_intent_is_the_card_the_enemy_plays_at_end_of_turn():
    battle = battle_with(seq(card("a", 0, dmg(1)), card("b", 0, dmg(2)), reveal=True))
    battle.start()
    for _ in range(5):
        shown = battle.enemy_intent.id
        battle.end_turn()
        assert enemy_plays(battle)[-1] == shown


def test_intent_advances_after_each_enemy_turn():
    battle = battle_with(seq(card("a", 0, dmg(1)), card("b", 0, dmg(1)), reveal=True))
    battle.start()
    assert battle.enemy_intent.id == "a"
    battle.end_turn()
    assert battle.enemy_intent.id == "b"


def test_playing_cards_does_not_change_intent():
    battle = battle_with(seq(card("a", 0, dmg(1)), card("b", 0, dmg(1)), reveal=True), player_deck=[card("p", 0, dmg(1))] * 3)
    battle.start()
    before = battle.enemy_intent.id
    battle.play_card(0)
    assert battle.enemy_intent.id == before


def test_intent_is_hidden_when_the_ai_does_not_reveal_it():
    battle = battle_with(seq(card("a", 0, dmg(1)), reveal=False))
    battle.start()
    assert battle.enemy_intent is None
    battle.end_turn()
    assert battle.enemy_intent is None
    assert enemy_plays(battle) == ["a"]  # still acts, the intent is just not shown


def test_hidden_weighted_intent_still_determines_the_action():
    ai = weighted((card("a", 0, dmg(1)), 1), (card("b", 0, dmg(1)), 1), reveal=False)
    battle = battle_with(ai, seed=11)
    battle.start()
    for _ in range(6):
        battle.end_turn()
    assert len(enemy_plays(battle)) == 6


def test_revealed_weighted_intent_matches_the_played_card():
    ai = weighted((card("a", 0, dmg(1)), 1), (card("b", 0, dmg(1)), 3), reveal=True)
    battle = battle_with(ai, seed=21)
    battle.start()
    for _ in range(12):
        shown = battle.enemy_intent.id
        battle.end_turn()
        assert enemy_plays(battle)[-1] == shown


def test_intent_is_none_before_the_battle_starts():
    battle = battle_with(seq(card("a", 0, dmg(1)), reveal=True))
    assert battle.enemy_intent is None


def test_intent_is_none_once_the_battle_is_over():
    battle = battle_with(seq(card("a", 0, dmg(1)), reveal=True))
    battle.start()
    battle.enemy.hp = 0
    assert battle.enemy_intent is None
    with pytest.raises(BattleError):
        battle.end_turn()
