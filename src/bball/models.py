from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LineupConfig:
    team: Team
    power_combos: list[list[str]] = field(default_factory=list)
    required_final_period_players: list[str] = field(default_factory=list)
    periods_per_half: list[int] = field(default_factory=lambda: [6, 6])
    on_court_per_period: int = 5
    minutes_per_half: int = 20


@dataclass(slots=True)
class Player:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""


@dataclass(slots=True)
class Team:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    players: list[Player] = field(default_factory=list)
    lineup_config: LineupConfig | None = None

    def __post_init__(self) -> None:
        if self.lineup_config is None:
            self.lineup_config = LineupConfig(team=self)

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
    number: int = 1
    players: list[Player] = field(default_factory=list)
    created_at: str | None = None
    solution_snapshot: dict[str, Any] | None = None
    config_snapshot: dict[str, Any] | None = None
    away_players: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Game:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    team_id: str = ""
    date: str = ""
    lineup_spins: list[LineupSpin] = field(default_factory=list)
    selected_lineup_id: str | None = None

    def add_spin(self, spin: LineupSpin) -> None:
        self.lineup_spins.append(spin)

    def renumber_spins(self) -> None:
        for index, spin in enumerate(self.lineup_spins, start=1):
            spin.number = index

    def select_spin(self, spin_id: str) -> None:
        if not any(spin.id == spin_id for spin in self.lineup_spins):
            raise KeyError(f"Unknown lineup spin: {spin_id}")
        self.selected_lineup_id = spin_id

    def get_selected_spin(self) -> LineupSpin | None:
        for spin in self.lineup_spins:
            if spin.id == self.selected_lineup_id:
                return spin
        return None

    def get_next_spin_number(self) -> int:
        if not self.lineup_spins:
            return 1

        existing_numbers = sorted({spin.number for spin in self.lineup_spins if spin.number is not None})
        if 1 not in existing_numbers:
            return 1
        return max(existing_numbers) + 1
