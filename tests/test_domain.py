import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typer.testing import CliRunner

from bball.cli import app
from bball.models import Game, LineupConfig, LineupSpin, Player, Team
from bball.repositories import (
    InMemoryGameRepository,
    InMemoryPlayerRepository,
    InMemoryTeamRepository,
    SQLiteGameRepository,
    SQLitePlayerRepository,
    SQLiteTeamRepository,
)
from bball.solver import build_default_team, render_solution_display_data


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


def test_sqlite_repositories_round_trip_player_team_and_game() -> None:
    player_repo = SQLitePlayerRepository()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()

    team = Team(id="sqlite-team", name="SQLite Test Team", players=[Player(id="sqlite-player", name="Ace")])
    team_repo.save(team)

    loaded_team = team_repo.get(team.id)
    assert loaded_team is not None
    assert loaded_team.name == team.name
    assert loaded_team.players[0].name == "Ace"

    game = Game(
        id="sqlite-game",
        team_id=team.id,
        date="week-1",
        lineup_spins=[LineupSpin(id="spin-1", players=[Player(id="sqlite-player", name="Ace")])],
    )
    game_repo.save(game)

    loaded_game = game_repo.get(game.id)
    assert loaded_game is not None
    assert loaded_game.team_id == team.id
    assert loaded_game.date == "week-1"
    assert loaded_game.lineup_spins[0].players[0].name == "Ace"


def test_lineup_spin_can_store_solver_display_data() -> None:
    spin = LineupSpin(
        id="spin-1",
        players=[Player(id="p-1", name="Indie")],
        display_data={
            "status": "OPTIMAL",
            "first_half_rows": [["1", "20:00", "Indie, Mila", "Scarlett, Katrina"]],
            "summary_rows": [["Indie", "1", "0"]],
        },
    )

    assert spin.display_data["first_half_rows"][0][2] == "Indie, Mila"


def test_team_show_includes_stored_lineup_settings() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    team = Team(id="cli-show-team", name="Show Team", players=[Player(id="cli-player", name="Ace")])
    team.lineup_config = LineupConfig(
        team=team,
        power_combos=[["Ace", "Bo"], ["Cara", "Drew"]],
        required_final_period_players=["Ace", "Drew"],
    )
    team_repo.save(team)

    result = runner.invoke(app, ["team", "show", team.name])
    assert result.exit_code == 0
    assert "Power combos" in result.stdout
    assert "Ace / Bo" in result.stdout
    assert "Must be on at the end" in result.stdout
    assert "Ace, Drew" in result.stdout


def test_spin_show_includes_config_snapshot() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team = Team(id="cli-spin-team", name="Spin Team", players=[Player(id="cli-spin-player", name="Ace")])
    team.lineup_config = LineupConfig(
        team=team,
        power_combos=[["Ace", "Bo"]],
        required_final_period_players=["Ace"],
    )
    team_repo.save(team)

    game = Game(id="cli-spin-game", team_id=team.id, date="spin-day", lineup_spins=[])
    spin = LineupSpin(
        id="cli-spin-1",
        number=1,
        players=[Player(id="cli-spin-player", name="Ace")],
        display_data={"status": "OPTIMAL", "first_half_rows": [], "second_half_rows": [], "summary_rows": []},
        config_snapshot={
            "power_combos": [["Ace", "Bo"]],
            "required_final_period_players": ["Ace"],
            "periods_per_half": [6, 6],
            "on_court_per_period": 5,
            "minutes_per_half": 20,
        },
    )
    game.add_spin(spin)
    game_repo.save(game)

    loaded_game = game_repo.get(game.id)
    loaded_spin = loaded_game.lineup_spins[0]
    assert loaded_spin.config_snapshot["required_final_period_players"] == ["Ace"]

    result = runner.invoke(app, ["game", "spin", "show", team.name, game.date, "1"])
    assert result.exit_code == 0
    assert "Power combos" in result.stdout
    assert "Ace / Bo" in result.stdout
    assert "Must be on at the end" in result.stdout
    assert "Ace" in result.stdout


def test_spin_list_includes_run_timestamp() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team = Team(id="cli-list-team", name="List Team", players=[Player(id="cli-list-player", name="Ace")])
    team_repo.save(team)

    game = Game(id="cli-list-game", team_id=team.id, date="list-day", lineup_spins=[])
    spin = LineupSpin(
        id="cli-list-spin",
        number=1,
        players=[Player(id="cli-list-player", name="Ace")],
        created_at="2026-07-31T12:34:56",
        away_players=["Bo"],
    )
    game.add_spin(spin)
    game_repo.save(game)

    result = runner.invoke(app, ["game", "spin", "list", team.name, game.date])
    assert result.exit_code == 0
    assert "Start" in result.stdout
    assert "Away" in result.stdout
    assert "Run Date" in result.stdout
    assert "Ace" in result.stdout
    assert "Bo" in result.stdout


def test_build_parser_supports_subcommands() -> None:
    groups = app.registered_groups
    assert any(group.name == "team" for group in groups)
    assert any(group.name == "game" for group in groups)


def test_typer_help_output_includes_commands() -> None:
    runner = CliRunner()

    root_result = runner.invoke(app, [])
    assert root_result.exit_code == 0
    assert "Usage:" in root_result.stdout
    assert "team" in root_result.stdout
    assert "game" in root_result.stdout

    team_result = runner.invoke(app, ["team", "--help"])
    assert team_result.exit_code == 0
    assert "show" in team_result.stdout
    assert "list" in team_result.stdout


def test_game_renumbers_spins_after_deletion() -> None:
    game = Game(id="game-renumber", team_id="team", date="day", lineup_spins=[])
    game.add_spin(LineupSpin(id="spin-1", number=1, players=[]))
    game.add_spin(LineupSpin(id="spin-2", number=2, players=[]))
    game.add_spin(LineupSpin(id="spin-3", number=3, players=[]))

    game.lineup_spins = [spin for spin in game.lineup_spins if spin.number != 2]
    game.renumber_spins()

    assert [spin.number for spin in game.lineup_spins] == [1, 2]


def test_prune_spin_command_deletes_all_spins_after_confirmation() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team = Team(id="cli-prune-team", name="Prune Team", players=[Player(id="cli-prune-player", name="Ace")])
    team_repo.save(team)

    game = Game(id="cli-prune-game", team_id=team.id, date="prune-day", lineup_spins=[])
    game.add_spin(LineupSpin(id="cli-prune-spin-1", number=1, players=[Player(id="cli-prune-player", name="Ace")]))
    game.add_spin(LineupSpin(id="cli-prune-spin-2", number=2, players=[Player(id="cli-prune-player", name="Ace")]))
    game_repo.save(game)

    result = runner.invoke(app, ["game", "spin", "prune", team.name, game.date], input="y\n")
    assert result.exit_code == 0
    assert "Are you sure?" in result.stdout

    updated_game = game_repo.get(game.id)
    assert updated_game is not None
    assert updated_game.lineup_spins == []


def test_delete_spin_command_removes_selected_spin_after_confirmation() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team = Team(id="cli-delete-team", name="Delete Team", players=[Player(id="cli-delete-player", name="Ace")])
    team_repo.save(team)

    game = Game(id="cli-delete-game", team_id=team.id, date="delete-day", lineup_spins=[])
    game.add_spin(LineupSpin(id="cli-delete-spin-1", number=1, players=[Player(id="cli-delete-player", name="Ace")]))
    game.add_spin(LineupSpin(id="cli-delete-spin-2", number=2, players=[Player(id="cli-delete-player", name="Ace")]))
    game_repo.save(game)

    result = runner.invoke(app, ["game", "spin", "delete", team.name, game.date, "2"], input="y\n")
    assert result.exit_code == 0
    assert "Are you sure?" in result.stdout

    updated_game = game_repo.get(game.id)
    assert updated_game is not None
    assert len(updated_game.lineup_spins) == 1
    assert updated_game.lineup_spins[0].number == 1


def test_render_solution_display_data_renders_solver_tables(capsys) -> None:
    display_data = {
        "status": "OPTIMAL",
        "first_half_rows": [("1", "20:00", "Indie, Mila", "Scarlett, Katrina")],
        "second_half_rows": [("7", "20:00", "Mila", "Indie")],
        "summary_rows": [("Indie", "1", "1")],
    }

    render_solution_display_data(display_data)

    output = capsys.readouterr().out
    assert "First Half" in output
    assert "Second Half" in output
    assert "Player Summary" in output
    assert "Indie" in output
