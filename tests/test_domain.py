import sqlite3
import uuid
from pathlib import Path
from typing import Any

from pytest import CaptureFixture, MonkeyPatch
from typer.testing import CliRunner

from bball import settings
from bball.cli import app, build_render_data_from_solution_snapshot, render_solution_display_data
from bball.models import Game, LineupConfig, LineupSpin, Player, Team
from bball.repositories_inmemory import (
    InMemoryGameRepository,
    InMemoryPlayerRepository,
    InMemoryTeamRepository,
    InMemoryUserRepository,
)
from bball.repositories_sqlite import SQLiteGameRepository, SQLitePlayerRepository, SQLiteTeamRepository
from bball.solver import build_starting_lineup, solve_team_lineup
from tests.fixtures import build_default_team


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
    assert team.lineup_config.power_combos == []
    assert team.lineup_config.required_final_period_players == []


def test_lineup_config_defaults_boolean_preferences_to_enabled() -> None:
    team = Team(id="t-1", name="Vikings", players=[Player(id="p-1", name="Indie")])
    config = LineupConfig(team=team)

    assert "no_consecutive_off" not in config.boolean_preferences
    assert config.no_consecutive_off_mode == "preferred"
    assert "transition_constraints" not in config.boolean_preferences
    assert config.transition_constraints_mode == "preferred"
    assert config.boolean_preferences["power_combo_objective"] is True
    assert config.boolean_preferences["half_split_balance"] is True


def test_team_preference_toggle_updates_cli_config() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    team_name = f"cli-pref-team-{uuid.uuid4().hex}"
    team = Team(
        id=f"cli-pref-team-{uuid.uuid4().hex}",
        user_id="admin-001",
        name=team_name,
        players=[Player(id="p-1", name="Ace")],
    )
    team_repo.save(team)

    list_result = runner.invoke(app, ["--user", "admin-001", "team", "preference-list", team_name])
    assert list_result.exit_code == 0
    assert "half_split_balance" in list_result.stdout
    assert "no_consecutive_off" in list_result.stdout
    assert "transition_constraints" in list_result.stdout

    toggle_result = runner.invoke(
        app, ["--user", "admin-001", "team", "preference-toggle", team_name, "half_split_balance", "--disable"]
    )
    assert toggle_result.exit_code == 0

    updated_team = team_repo.get("admin-001", team.id)
    assert updated_team is not None
    assert updated_team.lineup_config is not None
    assert updated_team.lineup_config.boolean_preferences["half_split_balance"] is False


def test_team_preference_mode_updates_cli_config() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    team_name = f"cli-pref-mode-team-{uuid.uuid4().hex}"
    team = Team(
        id=f"cli-pref-mode-team-{uuid.uuid4().hex}",
        user_id="admin-001",
        name=team_name,
        players=[Player(id="p-1", name="Ace")],
    )
    team_repo.save(team)

    mode_result = runner.invoke(
        app, ["--user", "admin-001", "team", "preference-mode", team_name, "no_consecutive_off", "enforced"]
    )
    assert mode_result.exit_code == 0

    updated_team = team_repo.get("admin-001", team.id)
    assert updated_team is not None
    assert updated_team.lineup_config is not None
    assert updated_team.lineup_config.no_consecutive_off_mode == "enforced"

    invalid_result = runner.invoke(
        app, ["--user", "admin-001", "team", "preference-mode", team_name, "no_consecutive_off", "sometimes"]
    )
    assert invalid_result.exit_code != 0


def test_team_transition_constraints_mode_updates_cli_config() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    team_name = f"cli-pref-transition-team-{uuid.uuid4().hex}"
    team = Team(
        id=f"cli-pref-transition-team-{uuid.uuid4().hex}",
        user_id="admin-001",
        name=team_name,
        players=[Player(id="p-1", name="Ace")],
    )
    team_repo.save(team)

    mode_result = runner.invoke(
        app, ["--user", "admin-001", "team", "preference-mode", team_name, "transition_constraints", "enforced"]
    )
    assert mode_result.exit_code == 0

    updated_team = team_repo.get("admin-001", team.id)
    assert updated_team is not None
    assert updated_team.lineup_config is not None
    assert updated_team.lineup_config.transition_constraints_mode == "enforced"

    invalid_key_result = runner.invoke(
        app, ["--user", "admin-001", "team", "preference-mode", team_name, "bogus_key", "enforced"]
    )
    assert invalid_key_result.exit_code != 0

    invalid_result = runner.invoke(
        app, ["--user", "admin-001", "team", "preference-mode", team_name, "transition_constraints", "sometimes"]
    )
    assert invalid_result.exit_code != 0


def test_build_starting_lineup_excludes_never_on_first_players() -> None:
    active_players = ["Ace", "Bo", "Cara", "Drew", "Eli", "Finn", "Gus"]

    starting_lineup = build_starting_lineup(active_players, [], 5, forbidden_start_players=["Ace", "Bo"])

    assert len(starting_lineup) == 5
    assert set(starting_lineup).isdisjoint({"Ace", "Bo"})


def test_build_starting_lineup_prefers_power_combos_when_no_start_requested() -> None:
    active_players = ["Ace", "Bo", "Cara", "Drew", "Eli", "Finn", "Gus"]

    starting_lineup = build_starting_lineup(
        active_players,
        [],
        5,
        power_combos=[["Ace", "Bo"], ["Cara", "Drew"]],
    )

    assert len(starting_lineup) == 5
    assert {"Ace", "Bo"}.issubset(starting_lineup)
    assert set(starting_lineup).issubset(set(active_players))


def test_render_data_highlights_requested_players() -> None:
    solution_snapshot = {
        "status": "OPTIMAL",
        "players": ["Ace", "Bo"],
        "periods_per_half": [1, 0],
        "period_start_times": ["20:00"],
        "player_periods": [{"player": "Ace", "on": [True]}, {"player": "Bo", "on": [False]}],
    }

    display_data = build_render_data_from_solution_snapshot(solution_snapshot, highlighted_player_names={"Ace"})

    assert "[red reverse]Ace[/red reverse]" in display_data["first_half_rows"][0][2]
    assert "Bo" in display_data["first_half_rows"][0][3]


def test_run_spin_rejects_start_conflicts_with_never_on_first_rule() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team_name = f"cli-spin-start-conflict-{uuid.uuid4().hex}"
    team = Team(
        id=f"cli-spin-start-conflict-{uuid.uuid4().hex}",
        user_id="admin-001",
        name=team_name,
        players=[Player(id="p-1", name="Aaron"), Player(id="p-2", name="Erin"), Player(id="p-3", name="Bo")],
    )
    team.lineup_config = LineupConfig(team=team, never_on_first_period_players=["Aaron", "Erin"])
    team_repo.save(team)
    game_repo.save(
        Game(id="spin-conflict-game", user_id="admin-001", team_id=team.id, date="2026-08-01", lineup_spins=[])
    )

    result = runner.invoke(app, ["game", "spin", "run", team_name, "2026-08-01", "--start", "Aaron,Erin"])

    assert result.exit_code == 1
    assert "cannot start the game" in result.stdout.lower()


def test_in_memory_repositories_can_back_the_domain() -> None:
    player_repo = InMemoryPlayerRepository([Player(id="p-1", name="Indie")])
    player = player_repo.get("p-1")
    assert player is not None
    assert player.name == "Indie"

    team_repo = InMemoryTeamRepository([Team(id="t-1", name="Vikings", players=[player])])
    team = team_repo.get("", "t-1")
    assert team is not None
    assert team.name == "Vikings"

    game_repo = InMemoryGameRepository([Game(id="g-1", team_id="t-1", date="2026-01-10")])
    game = game_repo.get("", "g-1")
    assert game is not None
    assert game.team_id == "t-1"


def test_in_memory_game_repository_can_lookup_by_team_and_date() -> None:
    game_repo = InMemoryGameRepository([Game(id="g-1", team_id="t-1", date="2026-01-10")])

    found_game = game_repo.get_by_team_and_date("", "t-1", "2026-01-10")

    assert found_game is not None
    assert found_game.id == "g-1"


def test_sqlite_repositories_round_trip_player_team_and_game() -> None:
    SQLitePlayerRepository()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()

    team = Team(id="sqlite-team", name="SQLite Test Team", players=[Player(id="sqlite-player", name="Ace")])
    team_repo.save(team)

    loaded_team = team_repo.get(team.user_id, team.id)
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

    loaded_game = game_repo.get(game.user_id, game.id)
    assert loaded_game is not None
    assert loaded_game.team_id == team.id
    assert loaded_game.date == "week-1"
    assert loaded_game.lineup_spins[0].players[0].name == "Ace"


def test_sqlite_repositories_round_trip_solution_snapshot() -> None:
    game_repo = SQLiteGameRepository()
    game = Game(
        id="snapshot-game",
        team_id="snapshot-team",
        date="snapshot-day",
        lineup_spins=[
            LineupSpin(
                id="snapshot-spin",
                players=[Player(id="p-1", name="Ace")],
                solution_snapshot={
                    "status": "OPTIMAL",
                    "players": ["Ace"],
                    "period_start_times": ["20:00"],
                    "player_periods": [{"player": "Ace", "on": [True]}],
                },
            )
        ],
    )

    game_repo.save(game)

    loaded_game = game_repo.get(game.user_id, game.id)
    assert loaded_game is not None
    assert loaded_game.lineup_spins[0].solution_snapshot is not None
    assert loaded_game.lineup_spins[0].solution_snapshot["players"] == ["Ace"]


def test_lineup_spin_can_store_solution_snapshot() -> None:
    spin = LineupSpin(
        id="spin-1",
        players=[Player(id="p-1", name="Indie")],
        solution_snapshot={
            "status": "OPTIMAL",
            "players": ["Indie", "Mila"],
            "periods_per_half": [1, 1],
            "period_start_times": ["20:00", "20:00"],
            "player_periods": [{"player": "Indie", "on": [True, False]}],
        },
    )

    assert spin.solution_snapshot["player_periods"][0]["player"] == "Indie"  # type: ignore


def test_team_add_creates_team_with_players() -> None:
    runner = CliRunner()
    team_name = f"cli-add-team-{uuid.uuid4().hex}"

    result = runner.invoke(app, ["team", "add", team_name, "Ace", "Bo"])

    assert result.exit_code == 0
    assert "Created team" in result.stdout

    team_repo = SQLiteTeamRepository()
    created_team = next((team for team in team_repo.list("admin-001") if team.name == team_name), None)
    assert created_team is not None
    assert [player.name for player in created_team.players] == ["Ace", "Bo"]


def test_team_show_includes_stored_lineup_settings() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    team = Team(
        id="cli-show-team", user_id="admin-001", name="Show Team", players=[Player(id="cli-player", name="Ace")]
    )
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


def test_team_player_add_and_remove_update_roster() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    team_name = f"cli-player-roster-{uuid.uuid4().hex}"
    team = Team(
        id=f"cli-player-roster-{uuid.uuid4().hex}",
        user_id="admin-001",
        name=team_name,
        players=[Player(id="cli-player-ace", name="Ace")],
    )
    team_repo.save(team)

    add_result = runner.invoke(app, ["team", "player-add", team_name, "Bo", "Cara"])
    assert add_result.exit_code == 0
    assert "Added player" in add_result.stdout

    updated_team = team_repo.get("admin-001", team.id)
    assert updated_team is not None
    assert [player.name for player in updated_team.players] == ["Ace", "Bo", "Cara"]

    remove_result = runner.invoke(app, ["team", "player-remove", team_name, "Bo"])
    assert remove_result.exit_code == 0
    assert "Removed player" in remove_result.stdout

    updated_team = team_repo.get("admin-001", team.id)
    assert updated_team is not None
    assert [player.name for player in updated_team.players] == ["Ace", "Cara"]


def test_never_on_first_players_are_stored_and_manageable_via_cli() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    team_name = f"cli-never-on-first-{uuid.uuid4().hex}"
    team = Team(
        id=f"cli-never-on-first-{uuid.uuid4().hex}",
        user_id="admin-001",
        name=team_name,
        players=[Player(id="p-1", name="Ace"), Player(id="p-2", name="Bo")],
    )
    team_repo.save(team)

    add_result = runner.invoke(app, ["team", "rule", "never-on-first", "add", team_name, "Ace", "Bo"])
    assert add_result.exit_code == 0

    updated_team = team_repo.get("admin-001", team.id)
    assert updated_team is not None
    assert updated_team.lineup_config is not None
    assert updated_team.lineup_config.never_on_first_period_players == ["Ace", "Bo"]

    list_result = runner.invoke(app, ["team", "rule", "never-on-first", "list", team_name])
    assert list_result.exit_code == 0
    assert "Ace" in list_result.stdout

    remove_result = runner.invoke(app, ["team", "rule", "never-on-first", "remove", team_name, "1"])
    assert remove_result.exit_code == 0

    updated_team = team_repo.get("admin-001", team.id)
    assert updated_team is not None
    assert updated_team.lineup_config is not None
    assert updated_team.lineup_config.never_on_first_period_players == ["Bo"]


def test_rule_list_add_rejects_players_not_on_the_team() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    team_name = f"cli-rule-member-check-{uuid.uuid4().hex}"
    team = Team(
        id=f"cli-rule-member-check-{uuid.uuid4().hex}",
        user_id="admin-001",
        name=team_name,
        players=[Player(id="p-1", name="Ace")],
    )
    team_repo.save(team)

    commands = [
        ["team", "rule", "never-on-first", "add", team_name, "Ace", "Bo"],
        ["team", "rule", "cleanup", "add", team_name, "Bo"],
        ["team", "rule", "power-combo", "add", team_name, "Ace", "Bo"],
    ]

    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 1
        assert "Unknown player" in result.stdout

    updated_team = team_repo.get("admin-001", team.id)
    assert updated_team is not None
    assert updated_team.lineup_config is not None
    assert updated_team.lineup_config.required_final_period_players == []
    assert updated_team.lineup_config.never_on_first_period_players == []
    assert updated_team.lineup_config.power_combos == []


def test_team_remove_deletes_team_and_related_games_after_confirmation() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team_name = f"cli-remove-team-{uuid.uuid4().hex}"
    team = Team(
        id=f"cli-remove-team-{uuid.uuid4().hex}",
        user_id="admin-001",
        name=team_name,
        players=[Player(id="p-1", name="Ace")],
    )
    team_repo.save(team)
    game = Game(id="remove-game", user_id="admin-001", team_id=team.id, date="2026-01-01", lineup_spins=[])
    game_repo.save(game)

    result = runner.invoke(app, ["team", "remove", team_name], input="y\n")

    assert result.exit_code == 0
    assert team_repo.get("admin-001", team.id) is None
    assert game_repo.get("admin-001", game.id) is None


def test_spin_show_includes_config_snapshot() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team = Team(
        id="cli-spin-team", user_id="admin-001", name="Spin Team", players=[Player(id="cli-spin-player", name="Ace")]
    )
    team.lineup_config = LineupConfig(
        team=team,
        power_combos=[["Ace", "Bo"]],
        required_final_period_players=["Ace"],
    )
    team_repo.save(team)

    game = Game(id="cli-spin-game", user_id="admin-001", team_id=team.id, date="spin-day", lineup_spins=[])
    spin = LineupSpin(
        id="cli-spin-1",
        number=1,
        players=[Player(id="cli-spin-player", name="Ace")],
        solution_snapshot={
            "status": "OPTIMAL",
            "players": ["Ace"],
            "periods_per_half": [6, 6],
            "period_start_times": ["20:00", "20:00"],
            "player_periods": [{"player": "Ace", "on": [True, True]}],
        },
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

    loaded_game = game_repo.get("admin-001", game.id)
    loaded_spin = loaded_game.lineup_spins[0]  # type: ignore
    assert loaded_spin.config_snapshot["required_final_period_players"] == ["Ace"]  # type: ignore

    result = runner.invoke(app, ["game", "spin", "show", team.name, game.date, "1"])
    assert result.exit_code == 0
    assert "Power combos" in result.stdout
    assert "Ace / Bo" in result.stdout
    assert "Must be on at the end" in result.stdout
    assert "Ace" in result.stdout


def test_solved_spin_snapshot_records_boolean_preferences() -> None:
    team = Team(
        id="snapshot-prefs-team",
        user_id="admin-001",
        name="Snapshot Prefs Team",
        players=[Player(id=f"snapshot-prefs-player-{i}", name=f"P{i}") for i in range(8)],
    )
    config = LineupConfig(team=team, periods_per_half=[6, 6])
    config.boolean_preferences["half_split_balance"] = False
    config.boolean_preferences["power_combo_objective"] = True

    game = solve_team_lineup(team, config=config)

    assert game is not None
    snapshot = game.lineup_spins[0].config_snapshot
    assert snapshot is not None
    assert snapshot["boolean_preferences"] == {"half_split_balance": False, "power_combo_objective": True}


def test_spin_show_with_stats_renders_co_play_table() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team = Team(
        id="cli-stats-team", user_id="admin-001", name="Stats Team", players=[Player(id="cli-stats-player", name="Ace")]
    )
    team_repo.save(team)

    game = Game(id="cli-stats-game", user_id="admin-001", team_id=team.id, date="stats-day", lineup_spins=[])
    spin = LineupSpin(
        id="cli-stats-spin",
        number=1,
        players=[Player(id="cli-stats-player", name="Ace")],
        solution_snapshot={
            "status": "OPTIMAL",
            "players": ["Ace", "Bo", "Cara"],
            "periods_per_half": [2, 0],
            "period_start_times": ["20:00", "20:00"],
            "player_periods": [
                {"player": "Ace", "on": [True, True]},
                {"player": "Bo", "on": [True, False]},
                {"player": "Cara", "on": [False, True]},
            ],
        },
    )
    game.add_spin(spin)
    game_repo.save(game)

    result = runner.invoke(app, ["game", "spin", "show", team.name, game.date, "1", "--stats"])
    assert result.exit_code == 0
    assert "Co-play stats" in result.stdout
    assert "Ace / Bo" in result.stdout
    assert "Cara" not in result.stdout or "Ace / Bo" in result.stdout


def test_spin_list_includes_run_timestamp() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team = Team(
        id="cli-list-team", user_id="admin-001", name="List Team", players=[Player(id="cli-list-player", name="Ace")]
    )
    team_repo.save(team)

    game = Game(id="cli-list-game", user_id="admin-001", team_id=team.id, date="list-day", lineup_spins=[])
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
    assert root_result.exit_code == 2
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
    team = Team(
        id="cli-prune-team", user_id="admin-001", name="Prune Team", players=[Player(id="cli-prune-player", name="Ace")]
    )
    team_repo.save(team)

    game = Game(id="cli-prune-game", user_id="admin-001", team_id=team.id, date="prune-day", lineup_spins=[])
    game.add_spin(LineupSpin(id="cli-prune-spin-1", number=1, players=[Player(id="cli-prune-player", name="Ace")]))
    game.add_spin(LineupSpin(id="cli-prune-spin-2", number=2, players=[Player(id="cli-prune-player", name="Ace")]))
    game_repo.save(game)

    result = runner.invoke(app, ["game", "spin", "prune", team.name, game.date], input="y\n")
    assert result.exit_code == 0
    assert "Are you sure?" in result.stdout

    updated_game = game_repo.get("admin-001", game.id)
    assert updated_game is not None
    assert updated_game.lineup_spins == []


def test_delete_spin_command_removes_selected_spin_after_confirmation() -> None:
    runner = CliRunner()
    team_repo = SQLiteTeamRepository()
    game_repo = SQLiteGameRepository()
    team = Team(
        id="cli-delete-team",
        user_id="admin-001",
        name="Delete Team",
        players=[Player(id="cli-delete-player", name="Ace")],
    )
    team_repo.save(team)

    game = Game(id="cli-delete-game", user_id="admin-001", team_id=team.id, date="delete-day", lineup_spins=[])
    game.add_spin(LineupSpin(id="cli-delete-spin-1", number=1, players=[Player(id="cli-delete-player", name="Ace")]))
    game.add_spin(LineupSpin(id="cli-delete-spin-2", number=2, players=[Player(id="cli-delete-player", name="Ace")]))
    game_repo.save(game)

    result = runner.invoke(app, ["game", "spin", "delete", team.name, game.date, "2"], input="y\n")
    assert result.exit_code == 0
    assert "Are you sure?" in result.stdout

    updated_game = game_repo.get("admin-001", game.id)
    assert updated_game is not None
    assert len(updated_game.lineup_spins) == 1
    assert updated_game.lineup_spins[0].number == 1


def test_settings_can_select_repository_backend(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "REPOSITORY_BACKEND", "inmemory")

    repo_classes = settings.get_repository_classes()

    assert repo_classes.user is InMemoryUserRepository
    assert repo_classes.player is InMemoryPlayerRepository
    assert repo_classes.team is InMemoryTeamRepository
    assert repo_classes.game is InMemoryGameRepository


def test_system_db_create_creates_database_when_missing(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "system.sqlite3"
    monkeypatch.setattr("bball.settings.DB_PATH", db_path)
    if db_path.exists():
        db_path.unlink()

    runner = CliRunner()
    result = runner.invoke(app, ["system", "db-create"])

    assert result.exit_code == 0
    assert db_path.exists()


def test_system_db_create_uses_repository_initialization(monkeypatch: MonkeyPatch) -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.initialized = False

        def initialize(self) -> None:
            self.initialized = True

        def get(self, *args: tuple[Any, ...], **kwargs: dict[str, Any]) -> None:
            raise NotImplementedError

        def list(self, *args: tuple[Any, ...], **kwargs: dict[str, Any]) -> None:
            raise NotImplementedError

        def save(self, *args: tuple[Any, ...], **kwargs: dict[str, Any]) -> None:
            raise NotImplementedError

        def reset(self, *args: tuple[Any, ...], **kwargs: dict[str, Any]) -> None:
            raise NotImplementedError

        def db_exists(self, *args: tuple[Any, ...], **kwargs: dict[str, Any]) -> None:
            raise NotImplementedError

    monkeypatch.setattr(
        "bball.cli.get_repository_classes",
        lambda: settings.RepositoryClasses(
            user=FakeRepository,  # type: ignore
            player=FakeRepository,  # type: ignore
            team=FakeRepository,  # type: ignore
            game=FakeRepository,  # type: ignore
        ),
    )
    monkeypatch.setattr("bball.cli.settings.DB_PATH", Path("./tmp/ignored.sqlite3"))

    runner = CliRunner()
    result = runner.invoke(app, ["system", "db-create"])

    assert result.exit_code == 0
    assert "Created storage" in result.stdout


def test_system_db_truncate_deletes_all_rows_after_confirmation(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "system.sqlite3"
    monkeypatch.setattr("bball.settings.DB_PATH", db_path)

    team_repo = SQLiteTeamRepository(str(db_path))
    team_repo.save(Team(id="truncate-team", name="Truncate Team", players=[Player(id="truncate-player", name="Ace")]))

    runner = CliRunner()
    result = runner.invoke(app, ["system", "db-truncate"], input="y\n")

    assert result.exit_code == 0
    assert "Truncated database" in result.stdout

    with sqlite3.connect(db_path) as conn:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        team_count = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        game_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        player_count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]

    assert user_count == 0
    assert team_count == 0
    assert game_count == 0
    assert player_count == 0


def test_render_solution_display_data_renders_solver_tables(capsys: CaptureFixture) -> None:
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
