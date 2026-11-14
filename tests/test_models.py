import pytest

from cardgame.models import Card, CardDataError, Effect, EffectKind, Status, Unit


def test_damage_effect_holds_amount():
    effect = Effect(kind=EffectKind.DAMAGE, amount=6)
    assert effect.kind is EffectKind.DAMAGE
    assert effect.amount == 6
    assert effect.status is None
    assert effect.duration == 0


def test_apply_status_effect_requires_status_and_duration():
    effect = Effect(kind=EffectKind.APPLY_STATUS, amount=3, status="poison", duration=3)
    assert effect.status == "poison"
    with pytest.raises(CardDataError):
        Effect(kind=EffectKind.APPLY_STATUS, amount=3, status=None, duration=3)
    with pytest.raises(CardDataError):
        Effect(kind=EffectKind.APPLY_STATUS, amount=3, status="poison", duration=0)


def test_non_status_effect_rejects_status_fields():
    with pytest.raises(CardDataError):
        Effect(kind=EffectKind.SHIELD, amount=5, status="poison")
    with pytest.raises(CardDataError):
        Effect(kind=EffectKind.DRAW, amount=1, duration=2)


@pytest.mark.parametrize("amount", [0, -1])
def test_effect_amount_must_be_positive(amount):
    with pytest.raises(CardDataError):
        Effect(kind=EffectKind.DAMAGE, amount=amount)


def test_effect_amount_rejects_bool_and_float():
    with pytest.raises(CardDataError):
        Effect(kind=EffectKind.DAMAGE, amount=True)
    with pytest.raises(CardDataError):
        Effect(kind=EffectKind.DAMAGE, amount=2.5)


def test_card_holds_name_cost_and_effects():
    card = Card(
        id="strike",
        name="攻擊",
        cost=1,
        effects=(Effect(kind=EffectKind.DAMAGE, amount=6),),
    )
    assert card.cost == 1
    assert card.effects[0].amount == 6


def test_card_cost_can_be_zero_but_not_negative():
    effects = (Effect(kind=EffectKind.DRAW, amount=1),)
    assert Card(id="x", name="x", cost=0, effects=effects).cost == 0
    with pytest.raises(CardDataError):
        Card(id="x", name="x", cost=-1, effects=effects)


def test_card_requires_at_least_one_effect():
    with pytest.raises(CardDataError):
        Card(id="x", name="x", cost=1, effects=())


def test_card_requires_non_empty_id_and_name():
    effects = (Effect(kind=EffectKind.DRAW, amount=1),)
    with pytest.raises(CardDataError):
        Card(id="", name="x", cost=1, effects=effects)
    with pytest.raises(CardDataError):
        Card(id="x", name="  ", cost=1, effects=effects)


def test_status_has_stacks_and_duration():
    status = Status(id="poison", name="中毒", stacks=3, duration=2)
    assert status.stacks == 3
    assert status.duration == 2


def test_status_rejects_negative_values():
    with pytest.raises(CardDataError):
        Status(id="poison", name="中毒", stacks=-1)
    with pytest.raises(CardDataError):
        Status(id="poison", name="中毒", duration=-1)


def test_unit_starts_full_hp_and_energy_by_default():
    unit = Unit(id="p", name="玩家", max_hp=80, max_energy=3)
    assert unit.hp == 80
    assert unit.energy == 3
    assert unit.deck == []
    assert unit.statuses == []


def test_unit_accepts_explicit_hp_and_energy():
    unit = Unit(id="p", name="玩家", max_hp=80, max_energy=3, hp=10, energy=0)
    assert unit.hp == 10
    assert unit.energy == 0


def test_unit_rejects_hp_or_energy_above_max():
    with pytest.raises(CardDataError):
        Unit(id="p", name="玩家", max_hp=80, max_energy=3, hp=81)
    with pytest.raises(CardDataError):
        Unit(id="p", name="玩家", max_hp=80, max_energy=3, energy=4)


def test_unit_rejects_non_positive_max_hp():
    with pytest.raises(CardDataError):
        Unit(id="p", name="玩家", max_hp=0, max_energy=3)
