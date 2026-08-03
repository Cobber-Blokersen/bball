from __future__ import annotations

from bball.models import Player, Team


def build_default_team() -> Team:
    players = [
        Player(name=name)
        for name in [
            "Roula",
            "Toula",
            "Soula",
            "Voula",
            "Foula",
            "Houla",
            "Doula",
            "Agapi",
        ]
    ]
    return Team(
        id="deadbeef-dead-beef-dead-beefdeadbeef",
        name="Cons Angels",
        players=players,
    )
