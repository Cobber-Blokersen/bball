from __future__ import annotations

import uuid
from dataclasses import dataclass, field

DEFAULT_POWER_COMBOS = [
    ["Mila", "Katrina"],
    ["Hannah", "Sanavi"],
    ["Indie", "Scarlett"],
]
DEFAULT_REQUIRED_FINAL_PERIOD_PLAYERS = ["Mila", "Katrina"]
DEFAULT_PERIODS_PER_HALF = [6, 6]
DEFAULT_ON_COURT_PER_PERIOD = 5
DEFAULT_MINUTES_PER_HALF = 20


@dataclass(slots=True)
class LineupConfig:
    team: Team
    power_combos: list[list[str]] = field(default_factory=lambda: [list(combo) for combo in DEFAULT_POWER_COMBOS])
    required_final_period_players: list[str] = field(
        default_factory=lambda: list(DEFAULT_REQUIRED_FINAL_PERIOD_PLAYERS)
    )
    periods_per_half: list[int] = field(default_factory=lambda: list(DEFAULT_PERIODS_PER_HALF))
    on_court_per_period: int = DEFAULT_ON_COURT_PER_PERIOD
    minutes_per_half: int = DEFAULT_MINUTES_PER_HALF


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
    display_data: dict[str, list[list[str]] | str] | None = None
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
