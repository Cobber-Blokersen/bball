from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class Player:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""


@dataclass(slots=True)
class Team:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    players: list[Player] = field(default_factory=list)

    def add_player(self, player: Player) -> None:
        self.players.append(player)

    def get_player_by_name(self, name: str) -> Player | None:
        for player in self.players:
            if player.name == name:
                return player
        return None

    def get_player_names(self) -> list[str]:
        return [player.name for player in self.players]


@dataclass(slots=True)
class LineupSpin:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    players: list[Player] = field(default_factory=list)
    created_at: str | None = None


@dataclass(slots=True)
class Game:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    team_id: str = ""
    date: str = ""
    lineup_spins: list[LineupSpin] = field(default_factory=list)
    selected_lineup_id: str | None = None

    def add_spin(self, spin: LineupSpin) -> None:
        self.lineup_spins.append(spin)

    def select_spin(self, spin_id: str) -> None:
        if not any(spin.id == spin_id for spin in self.lineup_spins):
            raise KeyError(f"Unknown lineup spin: {spin_id}")
        self.selected_lineup_id = spin_id

    def get_selected_spin(self) -> LineupSpin | None:
        for spin in self.lineup_spins:
            if spin.id == self.selected_lineup_id:
                return spin
        return None
