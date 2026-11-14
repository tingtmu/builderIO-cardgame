"""Enemy action selection (M4).

An enemy's behaviour is ``AIDef`` data from ``data/units.json``. ``EnemyBrain``
holds the per-battle cursor for that pattern and picks the next card. The
battle calls it once to pre-roll each intent, so the card an enemy shows to
the player is the card it will play.

Nothing here knows about specific card or unit ids.
"""

from __future__ import annotations

import random

from cardgame.models import AIDef, Card, EnemyAIKind


class EnemyBrain:
    def __init__(self, definition: AIDef) -> None:
        self.definition = definition
        self._cursor = 0

    def next_card(self, rng: random.Random) -> Card:
        """Return the card for the next enemy turn and advance the pattern.

        ``sequence`` uses no randomness. ``weighted`` draws from ``rng``, so the
        battle stays reproducible for a given seed.
        """
        actions = self.definition.actions
        if self.definition.kind is EnemyAIKind.SEQUENCE:
            action = actions[self._cursor % len(actions)]
            self._cursor += 1
            return action.card
        (action,) = rng.choices(actions, weights=[a.weight for a in actions], k=1)
        return action.card
