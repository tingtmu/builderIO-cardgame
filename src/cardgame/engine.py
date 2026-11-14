"""Turn flow and status effects for one battle (M2 + M3).

Turn order::

    draw -> player plays cards -> resolve effects -> enemy acts
         -> status settle -> next turn

Status behaviour (ticks, stack loss, lifetime, damage multipliers, absorption)
is data in ``data/statuses.json``. The engine only implements the generic
rules for those fields, so adding a status is a data change plus, at most, a
new handler in ``EFFECT_HANDLERS``.

All randomness comes from a ``random.Random`` seeded in the constructor, so the
same seed and the same sequence of actions always produce the same battle.

Effects are dispatched by ``EffectKind`` through ``EFFECT_HANDLERS``. The engine
never looks at card ids, so adding a card is a data change only.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction

from cardgame.loader import load_statuses
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

HAND_SIZE = 5
SHIELD_STATUS_ID = "shield"


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
    def __init__(
        self,
        player: Unit,
        enemy: Unit,
        seed: int,
        hand_size: int = HAND_SIZE,
        statuses: Mapping[str, StatusDef] | None = None,
    ) -> None:
        self.player = player
        self.enemy = enemy
        self.rng = random.Random(seed)
        self.hand_size = hand_size
        self.status_defs: Mapping[str, StatusDef] = load_statuses() if statuses is None else statuses
        self.turn = 0
        self.hand: list[Card] = []
        self.draw_pile: list[Card] = list(player.deck)
        self.discard_pile: list[Card] = []
        self.events: list[Event] = []
        for unit in (player, enemy):
            for status in unit.statuses:
                self.status_def(status.id)  # fail early on unknown initial statuses
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

    def status_def(self, status_id: str) -> StatusDef:
        try:
            return self.status_defs[status_id]
        except KeyError:
            raise CardDataError(f"unknown status id {status_id!r}") from None

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
        self._begin_enemy_turn()
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
        self._expire_owner_turn_start(self.player)
        self.player.energy = self.player.max_energy
        self._draw(self.hand_size)

    def _begin_enemy_turn(self) -> None:
        self._expire_owner_turn_start(self.enemy)

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
        self._log("status_settle", self.player.id)
        # Fixed order (player, then enemy) and list order keep this deterministic.
        for unit in (self.player, self.enemy):
            for status in list(unit.statuses):
                self._tick_status(unit, status)
                if self.over:
                    return

    def _tick_status(self, unit: Unit, status: Status) -> None:
        definition = self.status_def(status.id)
        if definition.damage_per_stack and status.stacks:
            lost = self._lose_hp(unit, status.stacks * definition.damage_per_stack)
            self._log("status_damage", unit.id, target=unit.id, amount=lost, detail=status.id)
        if definition.stacks_lost_per_turn:
            status.stacks = max(0, status.stacks - definition.stacks_lost_per_turn)
        timed = definition.lifetime is StatusLifetime.TURNS
        if timed:
            status.duration = max(0, status.duration - 1)
        if status.stacks == 0 or (timed and status.duration == 0):
            self._remove_status(unit, status)

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

    def _find_status(self, unit: Unit, status_id: str) -> Status | None:
        for status in unit.statuses:
            if status.id == status_id:
                return status
        return None

    def _add_status(self, unit: Unit, status_id: str, stacks: int, duration: int) -> None:
        """Apply a status. Same id adds stacks and refreshes duration to the max."""
        definition = self.status_def(status_id)
        existing = self._find_status(unit, status_id)
        if existing is None:
            unit.statuses.append(Status(id=status_id, name=definition.name, stacks=stacks, duration=duration))
        else:
            existing.stacks += stacks
            existing.duration = max(existing.duration, duration)

    def _remove_status(self, unit: Unit, status: Status) -> None:
        unit.statuses.remove(status)
        self._log("status_expire", unit.id, detail=status.id)

    def _expire_owner_turn_start(self, unit: Unit) -> None:
        for status in list(unit.statuses):
            if self.status_def(status.id).lifetime is StatusLifetime.OWNER_TURN_START:
                self._remove_status(unit, status)

    def _outgoing_damage(self, source: Unit, amount: int) -> int:
        multiplier = Fraction(1)
        for status in source.statuses:
            multiplier *= self.status_def(status.id).outgoing_damage_multiplier
        return math.floor(amount * multiplier)

    def _lose_hp(self, unit: Unit, amount: int) -> int:
        lost = min(unit.hp, amount)
        unit.hp -= lost
        return lost


def _resolve_damage(battle: Battle, effect: Effect, source: Unit, target: Unit) -> None:
    amount = battle._outgoing_damage(source, effect.amount)
    absorbed = 0
    for status in list(target.statuses):
        if not battle.status_def(status.id).absorbs_damage:
            continue
        taken = min(status.stacks, amount - absorbed)
        status.stacks -= taken
        absorbed += taken
        if status.stacks == 0:
            battle._remove_status(target, status)
    lost = amount - absorbed
    target.hp = max(0, target.hp - lost)
    battle._log("damage", source.id, target=target.id, amount=lost)


def _resolve_shield(battle: Battle, effect: Effect, source: Unit, target: Unit) -> None:
    # Shield always goes to the unit that played it. Its lifetime comes from
    # data/statuses.json (owner_turn_start), so no duration is set here.
    battle._add_status(source, SHIELD_STATUS_ID, stacks=effect.amount, duration=0)
    battle._log("shield", source.id, target=source.id, amount=effect.amount)


def _resolve_draw(battle: Battle, effect: Effect, source: Unit, target: Unit) -> None:
    # Only the player has a hand in M2, so an enemy draw does nothing.
    if source is battle.player:
        battle._draw(effect.amount)


def _resolve_apply_status(battle: Battle, effect: Effect, source: Unit, target: Unit) -> None:
    battle._add_status(target, effect.status, stacks=effect.amount, duration=effect.duration)
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
