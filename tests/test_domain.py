import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bball.models import Game, LineupSpin, LineupConfig, Player, Team
from bball.repositories import (
    InMemoryGameRepository,
    InMemoryPlayerRepository,
    InMemoryTeamRepository,
)
from bball.solver import build_default_team


def test_player_and_team_modeling() -> None:
    player = Player(id="p-1", name="Indie")
    team = Team(id="t-1", name="Vikings", players=[player])

    assert team.get_player_by_name("Indie") == player
    assert team.get_player_names() == ["Indie"]


def test_game_tracks_lineup_spins_and_selection() -> None:
    team = Team(id="t-1", name="Vikings")
    game = Game(id="g-1", team_id=team.id, date="2026-01-10")
    spin = LineupSpin(id="spin-1", players=[Player(id="p-1", name="Indie")])

    game.add_spin(spin)
    game.select_spin("spin-1")

    assert game.selected_lineup_id == "spin-1"
    assert game.get_selected_spin() == spin


def test_lineup_config_lives_with_domain_models() -> None:
    team = Team(id="t-1", name="Vikings", players=[Player(id="p-1", name="Indie")])
    config = LineupConfig(team=team, periods_per_half=[4, 4])

    assert config.team is team
    assert config.periods_per_half == [4, 4]


def test_default_team_contains_lineup_config() -> None:
    team = build_default_team()

    assert team.lineup_config is not None
    assert team.lineup_config.power_combos == [["Mila", "Katrina"], ["Hannah", "Sanavi"], ["Indie", "Scarlett"]]
    assert team.lineup_config.required_final_period_players == ["Mila", "Katrina"]


def test_in_memory_repositories_can_back_the_domain() -> None:
    player_repo = InMemoryPlayerRepository([Player(id="p-1", name="Indie")])
    team_repo = InMemoryTeamRepository([Team(id="t-1", name="Vikings", players=[player_repo.get("p-1")])])
    game_repo = InMemoryGameRepository([Game(id="g-1", team_id="t-1", date="2026-01-10")])

    assert player_repo.get("p-1").name == "Indie"
    assert team_repo.get("t-1").name == "Vikings"
    assert game_repo.get("g-1").team_id == "t-1"
