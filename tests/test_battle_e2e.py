"""End-to-end: a full battle from the real data files, run twice with the same seed."""

import pytest

from cardgame.engine import Battle
from cardgame.loader import CARDS_FILE, UNITS_FILE, load_cards, load_units

MAX_TURNS = 200


def play_first_affordable_each_turn(battle):
    """Scripted player: play the first card in hand that the energy can pay for, then end turn."""
    while not battle.over and battle.turn < MAX_TURNS:
        for index, candidate in enumerate(battle.hand):
            if candidate.cost <= battle.player.energy:
                battle.play_card(index)
                break
        else:
            battle.end_turn()
            continue
        if battle.over:
            break
        battle.end_turn()


def run_full_battle(enemy_id, seed):
    units = load_units(UNITS_FILE, load_cards(CARDS_FILE))
    battle = Battle(units["player"], units[enemy_id], seed=seed)
    battle.start()
    play_first_affordable_each_turn(battle)
    return battle


def log_of(battle):
    return [(e.turn, e.actor, e.kind, e.target, e.amount, e.detail) for e in battle.events]


@pytest.mark.parametrize("enemy_id", ["slime", "cultist"])
@pytest.mark.parametrize("seed", [0, 1, 2024])
def test_full_seeded_battle_runs_to_completion_and_repeats_exactly(enemy_id, seed):
    first = run_full_battle(enemy_id, seed)
    second = run_full_battle(enemy_id, seed)

    assert first.over, "battle did not finish within the turn limit"
    assert first.winner in {"player", enemy_id}
    assert first.turn < MAX_TURNS

    assert first.winner == second.winner
    assert first.turn == second.turn
    assert log_of(first) == log_of(second)


def test_enemy_actions_in_the_full_battle_follow_their_ai():
    slime = run_full_battle("slime", seed=5)
    slime_plays = [e.detail for e in slime.events if e.kind == "enemy_play"]
    # The slime's pattern is strike, defend, repeating; it cannot deviate from it.
    expected = ["strike", "defend"] * (len(slime_plays) // 2 + 1)
    assert slime_plays == expected[: len(slime_plays)]
    assert len(slime_plays) > 0
