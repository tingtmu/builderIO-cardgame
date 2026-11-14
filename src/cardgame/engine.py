"""Turn flow for one battle (M2).

Turn order::

    draw -> player plays cards -> resolve effects -> enemy acts
         -> status settle (placeholder) -> next turn

All randomness comes from a ``random.Random`` seeded in the constructor, so the
same seed and the same sequence of actions always produce the same battle.

Effects are dispatched by ``EffectKind`` through ``EFFECT_HANDLERS``. The engine
never looks at card ids, so adding a card is a data change only.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from cardgame.models import Card, Effect, EffectKind, Status, Unit

HAND_SIZE = 5
SHIELD_STATUS_ID = "shield"
SHIELD_STATUS_NAME = "護盾"


class BattleError(RuntimeError):
    """Raised for an illegal action, such as playing a card you cannot afford."""


@dataclass(frozen=True)
class Event:
    """One entry in the battle log.

    ``kind`` is an engine event name (``play_card``, ``damage``, ``draw``, ...).
    ``detail`` carries data such as a card id or status id, for logging only.
    """

    turn: int
    actor: str
    kind: str
    target: str | None = None
    amount: int = 0
    detail: str = ""


class Battle:
    def __init__(self, player: Unit, enemy: Unit, seed: int, hand_size: int = HAND_SIZE) -> None:
        self.player = player
        self.enemy = enemy
        self.rng = random.Random(seed)
        self.hand_size = hand_size
        self.turn = 0
        self.hand: list[Card] = []
        self.draw_pile: list[Card] = list(player.deck)
        self.discard_pile: list[Card] = []
        self.events: list[Event] = []
        self.rng.shuffle(self.draw_pile)

    # ----- state queries -------------------------------------------------

    @property
    def over(self) -> bool:
        return self.player.hp == 0 or self.enemy.hp == 0

    @property
    def winner(self) -> str | None:
        if self.enemy.hp == 0:
            return self.player.id
        if self.player.hp == 0:
            return self.enemy.id
        return None

    # ----- actions -------------------------------------------------------

    def start(self) -> None:
        """Begin turn 1: refill energy and draw the opening hand."""
        if self.turn != 0:
            raise BattleError("battle already started")
        self._begin_turn()

    def play_card(self, index: int) -> None:
        """Play the card at ``index`` in hand and resolve its effects."""
        self._require_player_turn()
        if not 0 <= index < len(self.hand):
            raise BattleError(f"no card at hand index {index}")
        card = self.hand[index]
        if card.cost > self.player.energy:
            raise BattleError(f"card {card.id!r} costs {card.cost}, only {self.player.energy} energy left")
        self.player.energy -= card.cost
        del self.hand[index]
        self.discard_pile.append(card)
        self._log("play_card", self.player.id, detail=card.id)
        for effect in card.effects:
            self._resolve(effect, source=self.player, target=self.enemy)

    def end_turn(self) -> None:
        """End the player's turn: enemy acts, statuses settle, next turn begins."""
        self._require_player_turn()
        # Unplayed cards go to the discard pile so the hand resets each turn.
        self.discard_pile.extend(self.hand)
        self.hand.clear()
        self._enemy_act()
        if self.over:
            return
        self._settle_statuses()
        if self.over:
            return
        self._begin_turn()

    # ----- turn steps ----------------------------------------------------

    def _require_player_turn(self) -> None:
        if self.turn == 0:
            raise BattleError("battle not started")
        if self.over:
            raise BattleError("battle is over")

    def _begin_turn(self) -> None:
        self.turn += 1
        self.player.energy = self.player.max_energy
        self._draw(self.hand_size)

    def _enemy_act(self) -> None:
        # Placeholder AI (real enemy AI is M4): refill energy, then play one
        # random card from the deck that the energy can pay for.
        enemy = self.enemy
        enemy.energy = enemy.max_energy
        affordable = [card for card in enemy.deck if card.cost <= enemy.energy]
        if not affordable:
            return
        card = self.rng.choice(affordable)
        enemy.energy -= card.cost
        self._log("enemy_play", enemy.id, detail=card.id)
        for effect in card.effects:
            self._resolve(effect, source=enemy, target=self.player)

    def _settle_statuses(self) -> None:
        # Placeholder for M3: tick status durations and apply per-turn effects.
        self._log("status_settle", self.player.id)

    # ----- helpers -------------------------------------------------------

    def _draw(self, count: int) -> None:
        for _ in range(count):
            if not self.draw_pile:
                if not self.discard_pile:
                    return
                self.draw_pile, self.discard_pile = self.discard_pile, []
                self.rng.shuffle(self.draw_pile)
            card = self.draw_pile.pop()
            self.hand.append(card)
            self._log("draw", self.player.id, detail=card.id)

    def _resolve(self, effect: Effect, source: Unit, target: Unit) -> None:
        EFFECT_HANDLERS[effect.kind](self, effect, source, target)

    def _log(
        self,
        kind: str,
        actor: str,
        target: str | None = None,
        amount: int = 0,
        detail: str = "",
    ) -> None:
        self.events.append(Event(self.turn, actor, kind, target, amount, detail))


def _shield_status(unit: Unit) -> Status | None:
    for status in unit.statuses:
        if status.id == SHIELD_STATUS_ID:
            return status
    return None


def _resolve_damage(battle: Battle, effect: Effect, source: Unit, target: Unit) -> None:
    shield = _shield_status(target)
    absorbed = 0
    if shield is not None:
        absorbed = min(shield.stacks, effect.amount)
        shield.stacks -= absorbed
        if shield.stacks == 0:
            target.statuses.remove(shield)
    lost = effect.amount - absorbed
    target.hp = max(0, target.hp - lost)
    battle._log("damage", source.id, target=target.id, amount=lost)


def _resolve_shield(battle: Battle, effect: Effect, source: Unit, target: Unit) -> None:
    # Shield always goes to the unit that played it. Its lifetime is M3's job,
    # so duration stays 0 here.
    shield = _shield_status(source)
    if shield is None:
        source.statuses.append(Status(id=SHIELD_STATUS_ID, name=SHIELD_STATUS_NAME, stacks=effect.amount))
    else:
        shield.stacks += effect.amount
    battle._log("shield", source.id, target=source.id, amount=effect.amount)


def _resolve_draw(battle: Battle, effect: Effect, source: Unit, target: Unit) -> None:
    # Only the player has a hand in M2, so an enemy draw does nothing.
    if source is battle.player:
        battle._draw(effect.amount)


def _resolve_apply_status(battle: Battle, effect: Effect, source: Unit, target: Unit) -> None:
    # Recorded only. Applying and ticking statuses is M3.
    battle._log(
        "apply_status",
        source.id,
        target=target.id,
        amount=effect.amount,
        detail=f"{effect.status}:{effect.duration}",
    )


Handler = Callable[[Battle, Effect, Unit, Unit], None]

EFFECT_HANDLERS: dict[EffectKind, Handler] = {
    EffectKind.DAMAGE: _resolve_damage,
    EffectKind.SHIELD: _resolve_shield,
    EffectKind.DRAW: _resolve_draw,
    EffectKind.APPLY_STATUS: _resolve_apply_status,
}
