import json
from fractions import Fraction

import pytest

from cardgame.engine import SHIELD_STATUS_ID, Battle, BattleError
from cardgame.loader import CARDS_FILE, STATUSES_FILE, load_cards, load_statuses
from cardgame.models import (
    Card,
    CardDataError,
    Effect,
    EffectKind,
    Status,
    StatusDef,
    StatusLifetime,
    Unit,
)


def dmg(amount):
    return Effect(kind=EffectKind.DAMAGE, amount=amount)


def shield(amount):
    return Effect(kind=EffectKind.SHIELD, amount=amount)


def apply(status, stacks, duration):
    return Effect(kind=EffectKind.APPLY_STATUS, amount=stacks, status=status, duration=duration)


def poison(stacks, duration):
    return apply("poison", stacks, duration)


def weak(stacks, duration):
    return apply("weak", stacks, duration)


def card(card_id, cost, *effects):
    return Card(id=card_id, name=card_id, cost=cost, effects=tuple(effects))


def unit(unit_id, max_hp=50, max_energy=3, deck=()):
    return Unit(id=unit_id, name=unit_id, max_hp=max_hp, max_energy=max_energy, deck=list(deck))


def make_battle(player_deck, enemy_deck=(), seed=0, hand_size=5, statuses=None):
    player = unit("player", deck=player_deck)
    enemy = unit("enemy", max_hp=30, max_energy=2, deck=enemy_deck)
    return Battle(player, enemy, seed=seed, hand_size=hand_size, statuses=statuses)


def play_by_id(battle, card_id):
    index = [c.id for c in battle.hand].index(card_id)
    battle.play_card(index)


def status_on(unit_, status_id):
    matches = [s for s in unit_.statuses if s.id == status_id]
    return matches[0] if matches else None


def events_of(battle, kind):
    return [e for e in battle.events if e.kind == kind]


def write_statuses(tmp_path, data):
    path = tmp_path / "statuses.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# ----- data loading --------------------------------------------------------


def test_real_statuses_file_defines_poison_weak_and_shield():
    defs = load_statuses(STATUSES_FILE)
    assert set(defs) == {"poison", "weak", "shield"}
    assert defs["poison"].damage_per_stack == 1
    assert defs["poison"].stacks_lost_per_turn == 1
    assert defs["weak"].outgoing_damage_multiplier == Fraction(3, 4)
    assert defs["shield"].absorbs_damage is True
    assert defs["shield"].lifetime is StatusLifetime.OWNER_TURN_START


def test_every_status_used_by_example_cards_is_defined():
    defs = load_statuses(STATUSES_FILE)
    for card_def in load_cards(CARDS_FILE).values():
        for effect in card_def.effects:
            if effect.kind is EffectKind.APPLY_STATUS:
                assert effect.status in defs


def test_status_definition_rejects_unknown_key(tmp_path):
    path = write_statuses(tmp_path, [{"id": "x", "name": "x", "damge_per_stack": 1}])
    with pytest.raises(CardDataError, match="unknown keys"):
        load_statuses(path)


def test_status_definition_rejects_unknown_lifetime(tmp_path):
    path = write_statuses(tmp_path, [{"id": "x", "name": "x", "lifetime": "forever"}])
    with pytest.raises(CardDataError, match="unknown lifetime"):
        load_statuses(path)


def test_status_definition_rejects_negative_multiplier(tmp_path):
    path = write_statuses(tmp_path, [{"id": "x", "name": "x", "outgoing_damage_multiplier": -0.5}])
    with pytest.raises(CardDataError, match="non-negative"):
        load_statuses(path)


def test_status_definition_rejects_duplicate_ids(tmp_path):
    path = write_statuses(tmp_path, [{"id": "x", "name": "a"}, {"id": "x", "name": "b"}])
    with pytest.raises(CardDataError, match="duplicate"):
        load_statuses(path)


def test_multiplier_is_parsed_as_exact_fraction(tmp_path):
    path = write_statuses(tmp_path, [{"id": "x", "name": "x", "outgoing_damage_multiplier": 0.7}])
    assert load_statuses(path)["x"].outgoing_damage_multiplier == Fraction(7, 10)


def test_card_referencing_unknown_status_is_an_error():
    battle = make_battle([card("venom", 0, poison(1, 1))])
    battle.start()
    battle.status_defs = {k: v for k, v in battle.status_defs.items() if k != "poison"}
    with pytest.raises(CardDataError, match="unknown status"):
        battle.play_card(0)


# ----- poison --------------------------------------------------------------


def test_poison_deals_damage_equal_to_stacks_at_settle_then_loses_one_stack():
    battle = make_battle([card("venom", 0, poison(3, 3))])
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert battle.enemy.hp == 30 - 3
    status = status_on(battle.enemy, "poison")
    assert (status.stacks, status.duration) == (2, 2)


def test_poison_ticks_down_each_settle_and_is_removed_when_duration_ends():
    battle = make_battle([card("venom", 0, poison(3, 3))])
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    battle.end_turn()
    battle.end_turn()
    # 3 + 2 + 1 damage over three settles, then the status is gone.
    assert battle.enemy.hp == 30 - 6
    assert status_on(battle.enemy, "poison") is None
    assert [e.amount for e in events_of(battle, "status_damage")] == [3, 2, 1]


def test_poison_removed_early_when_stacks_run_out():
    battle = make_battle([card("a", 0, dmg(1))])
    battle.start()
    battle.enemy.statuses.append(Status(id="poison", name="中毒", stacks=1, duration=5))
    battle.end_turn()
    assert battle.enemy.hp == 29
    assert status_on(battle.enemy, "poison") is None


def test_poison_damage_ignores_shield():
    battle = make_battle([card("guard", 0, shield(10))])
    battle.start()
    battle.play_card(0)
    battle.player.statuses.append(Status(id="poison", name="中毒", stacks=3, duration=3))
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - 3
    assert events_of(battle, "status_damage")[0].amount == 3
    assert events_of(battle, "damage") == []  # the shield was never hit by the settle tick


def test_poison_can_kill_enemy_and_ends_battle_with_player_winning():
    battle = make_battle([card("a", 0, dmg(1))])
    battle.start()
    battle.enemy.hp = 2
    battle.enemy.statuses.append(Status(id="poison", name="中毒", stacks=3, duration=3))
    battle.end_turn()
    assert battle.enemy.hp == 0
    assert battle.over
    assert battle.winner == "player"
    assert battle.turn == 1  # no new turn starts after a death
    with pytest.raises(BattleError, match="over"):
        battle.end_turn()


def test_poison_can_kill_player_and_enemy_wins():
    battle = make_battle([card("a", 0, dmg(1))], enemy_deck=[])
    battle.start()
    battle.player.hp = 2
    battle.player.statuses.append(Status(id="poison", name="中毒", stacks=2, duration=2))
    battle.end_turn()
    assert battle.player.hp == 0
    assert battle.winner == "enemy"
    assert events_of(battle, "status_damage")[0].target == "player"


def test_poison_death_stops_settling_the_other_units_statuses():
    battle = make_battle([card("a", 0, dmg(1))], enemy_deck=[])
    battle.start()
    battle.player.hp = 2
    battle.player.statuses.append(Status(id="poison", name="中毒", stacks=2, duration=2))
    battle.enemy.statuses.append(Status(id="poison", name="中毒", stacks=5, duration=5))
    battle.end_turn()
    assert battle.winner == "enemy"
    assert battle.enemy.hp == 30  # enemy's poison never ticked
    assert [e.target for e in events_of(battle, "status_damage")] == ["player"]


def test_poison_applied_twice_stacks_its_damage():
    battle = make_battle([card("venom", 0, poison(2, 2)), card("venom2", 0, poison(2, 2))])
    battle.start()
    play_by_id(battle, "venom")
    play_by_id(battle, "venom2")
    battle.end_turn()
    assert battle.enemy.hp == 30 - 4


# ----- weak ----------------------------------------------------------------


def test_weak_reduces_damage_dealt_by_the_afflicted_enemy_to_three_quarters():
    battle = make_battle([card("hex", 0, weak(1, 2))], enemy_deck=[card("hit", 0, dmg(8))])
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - 6


@pytest.mark.parametrize("raw, expected", [(6, 4), (5, 3), (4, 3), (3, 2), (1, 0)])
def test_weak_rounds_damage_down(raw, expected):
    battle = make_battle([card("hex", 0, weak(1, 2))], enemy_deck=[card("hit", 0, dmg(raw))])
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - expected


def test_weak_on_the_enemy_does_not_reduce_damage_the_enemy_receives():
    battle = make_battle([card("hit", 0, dmg(6))])
    battle.start()
    battle.enemy.statuses.append(Status(id="weak", name="虛弱", stacks=1, duration=2))
    battle.play_card(0)
    assert battle.enemy.hp == 30 - 6


def test_weak_on_the_player_reduces_the_players_own_damage():
    battle = make_battle([card("hit", 0, dmg(6))])
    battle.start()
    battle.player.statuses.append(Status(id="weak", name="虛弱", stacks=1, duration=2))
    battle.play_card(0)
    assert battle.enemy.hp == 30 - 4


def test_weak_does_not_reduce_shield_gained_by_the_afflicted_unit():
    battle = make_battle([card("hex", 0, weak(1, 2))], enemy_deck=[card("guard", 0, shield(4))])
    battle.start()
    play_by_id(battle, "hex")
    battle.end_turn()
    # The enemy's shield lasts until the enemy's own next turn starts, so it is still up now.
    assert status_on(battle.enemy, SHIELD_STATUS_ID).stacks == 4
    assert events_of(battle, "shield")[0].amount == 4


def test_weak_expires_after_its_duration_and_full_damage_returns():
    battle = make_battle([card("hex", 0, weak(1, 1))], enemy_deck=[card("hit", 0, dmg(8))], hand_size=1)
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - 6
    assert status_on(battle.enemy, "weak") is None
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - 6 - 8


def test_weak_does_not_tick_stacks_down():
    battle = make_battle([card("hex", 0, weak(3, 2))], enemy_deck=[card("hit", 0, dmg(8))])
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    status = status_on(battle.enemy, "weak")
    assert (status.stacks, status.duration) == (3, 1)


# ----- shield lifetime -----------------------------------------------------


def test_player_shield_absorbs_enemy_attack_in_the_same_round():
    battle = make_battle([card("guard", 0, shield(10))], enemy_deck=[card("hit", 0, dmg(4))])
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp
    assert battle.turn == 2


def test_unused_player_shield_expires_when_owner_next_turn_begins():
    battle = make_battle([card("guard", 0, shield(10))], enemy_deck=[card("hit", 0, dmg(4))])
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert status_on(battle.player, SHIELD_STATUS_ID) is None
    assert [e.turn for e in events_of(battle, "status_expire")] == [2]


def test_expired_shield_does_not_absorb_the_next_enemy_attack():
    battle = make_battle([card("guard", 0, shield(10))], enemy_deck=[card("hit", 0, dmg(4))])
    battle.start()
    battle.play_card(0)
    battle.end_turn()  # hit absorbed; 6 stacks left, then the shield expires at turn 2
    battle.end_turn()  # no shield on turn 2, so the hit lands in full
    assert battle.player.hp == battle.player.max_hp - 4


def test_enemy_shield_survives_the_player_turn_and_expires_at_enemy_next_turn():
    battle = make_battle([card("strike", 0, dmg(3))], enemy_deck=[])
    battle.start()
    battle.enemy.statuses.append(Status(id="shield", name="護盾", stacks=5, duration=0))
    battle.play_card(0)
    assert battle.enemy.hp == 30  # 3 absorbed by the 5-stack shield
    assert status_on(battle.enemy, SHIELD_STATUS_ID).stacks == 2
    battle.end_turn()
    assert status_on(battle.enemy, SHIELD_STATUS_ID) is None
    assert [e.actor for e in events_of(battle, "status_expire")] == ["enemy"]


def test_shield_absorbs_several_hits_in_one_action_then_is_gone():
    battle = make_battle([card("guard", 0, shield(5))], enemy_deck=[card("double", 0, dmg(3), dmg(3))])
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - 1  # 3 + 2 absorbed, 1 through
    assert status_on(battle.player, SHIELD_STATUS_ID) is None


# ----- stacking ------------------------------------------------------------


def test_same_status_id_adds_stacks():
    battle = make_battle([card("a", 0, poison(2, 2)), card("b", 0, poison(3, 1))])
    battle.start()
    play_by_id(battle, "a")
    play_by_id(battle, "b")
    assert len(battle.enemy.statuses) == 1
    assert status_on(battle.enemy, "poison").stacks == 5


def test_reapplying_status_refreshes_duration_to_the_max_and_never_shortens_it():
    battle = make_battle([card("long", 0, poison(1, 4)), card("short", 0, poison(1, 1))])
    battle.start()
    play_by_id(battle, "long")
    play_by_id(battle, "short")
    assert status_on(battle.enemy, "poison").duration == 4


def test_reapplying_status_with_longer_duration_extends_it():
    battle = make_battle([card("short", 0, poison(1, 1)), card("long", 0, poison(1, 4))])
    battle.start()
    play_by_id(battle, "short")
    play_by_id(battle, "long")
    status = status_on(battle.enemy, "poison")
    assert (status.stacks, status.duration) == (2, 4)


def test_different_statuses_coexist_on_one_unit():
    battle = make_battle([card("combo", 0, poison(1, 2), weak(1, 2))])
    battle.start()
    battle.play_card(0)
    assert sorted(s.id for s in battle.enemy.statuses) == ["poison", "weak"]


def test_stacking_shield_adds_stacks_and_keeps_one_entry():
    battle = make_battle([card("guard", 0, shield(3)), card("guard2", 0, shield(4))])
    battle.start()
    play_by_id(battle, "guard")
    play_by_id(battle, "guard2")
    assert len(battle.player.statuses) == 1
    assert status_on(battle.player, SHIELD_STATUS_ID).stacks == 7


# ----- data-driven behaviour ----------------------------------------------


def test_new_status_works_from_data_alone_without_engine_changes():
    # "bleed" deals 2 HP per stack at each settle and never loses stacks.
    defs = {"bleed": StatusDef(id="bleed", name="流血", damage_per_stack=2, stacks_lost_per_turn=0)}
    battle = make_battle([card("cut", 0, apply("bleed", 2, 2))], statuses=defs)
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert status_on(battle.enemy, "bleed").duration == 1
    battle.end_turn()
    assert battle.enemy.hp == 30 - 4 - 4
    assert status_on(battle.enemy, "bleed") is None


def test_custom_outgoing_multiplier_is_applied_from_data():
    defs = load_statuses(STATUSES_FILE)
    defs["frail"] = StatusDef(id="frail", name="脆弱", outgoing_damage_multiplier=Fraction(1, 2))
    battle = make_battle([card("cut", 0, apply("frail", 1, 1))], enemy_deck=[card("hit", 0, dmg(7))], statuses=defs)
    battle.start()
    battle.play_card(0)
    battle.end_turn()
    assert battle.player.hp == battle.player.max_hp - 3


def test_initial_unit_status_with_unknown_id_is_rejected():
    player = unit("player", deck=[card("a", 0, dmg(1))])
    player.statuses.append(Status(id="nope", name="?", stacks=1, duration=1))
    with pytest.raises(CardDataError, match="unknown status"):
        Battle(player, unit("enemy"), seed=0)


def test_status_battle_is_reproducible_for_a_seed():
    def run(seed):
        player = unit(
            "player",
            deck=[card("venom", 0, poison(2, 3)), card("hex", 0, weak(1, 2)), card("guard", 0, shield(3))] * 2,
        )
        enemy = unit(
            "enemy",
            max_hp=40,
            max_energy=2,
            deck=[card("hit", 0, dmg(5)), card("guard", 0, shield(2))],
        )
        battle = Battle(player, enemy, seed=seed)
        battle.start()
        while not battle.over and battle.turn < 20:
            for index, candidate in enumerate(battle.hand):
                if candidate.cost <= battle.player.energy:
                    battle.play_card(index)
                    break
            if battle.over:
                break
            battle.end_turn()
        return battle.turn, battle.winner, [(e.turn, e.kind, e.actor, e.amount, e.detail) for e in battle.events]

    for seed in range(10):
        assert run(seed) == run(seed)
