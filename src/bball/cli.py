from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from . import settings
from .models import LineupConfig, Player, Team
from .solver import normalize_player_argument_values, solve_team_lineup

PLAYER_CONSOLE_COLORS = [
    "red",
    "white",
    "cyan",
    "yellow",
    "green",
    "blue",
    "bright_magenta",
    "orange1",
]

app = typer.Typer(help="Basketball lineup optimizer and manager", no_args_is_help=True)
team_app = typer.Typer(help="Team-related commands", no_args_is_help=True)
rule_app = typer.Typer(help="Team rule management commands", no_args_is_help=True)
power_combo_app = typer.Typer(help="Power-combo rule commands", no_args_is_help=True)
cleanup_app = typer.Typer(help="Cleanup-rule commands", no_args_is_help=True)
game_app = typer.Typer(help="Game-related commands", no_args_is_help=True)
spin_app = typer.Typer(help="Spin-related commands", no_args_is_help=True)
system_app = typer.Typer(help="System maintenance commands", no_args_is_help=True)

app.add_typer(team_app, name="team")
team_app.add_typer(rule_app, name="rule")
rule_app.add_typer(power_combo_app, name="power-combo")
rule_app.add_typer(cleanup_app, name="cleanup")
app.add_typer(game_app, name="game")
game_app.add_typer(spin_app, name="spin")
app.add_typer(system_app, name="system")


def get_repository_classes() -> settings.RepositoryClasses:
    """Return the repository classes configured for the current backend."""
    return settings.get_repository_classes()


@system_app.command("db-create", help="Create the configured storage backend if it does not already exist.")
def create_database() -> None:
    """Create or initialize the configured storage backend."""
    repositories = get_repository_classes()
    repositories.player().initialize()
    repositories.team().initialize()
    repositories.game().initialize()
    typer.echo("Created storage")


@system_app.command("db-truncate", help="Delete all rows from the SQLite database after confirmation.")
def truncate_database() -> None:
    """Delete all rows from the SQLite database after confirmation."""
    confirm = typer.confirm("This will delete all data from the database. Continue?")
    if not confirm:
        typer.echo("Aborted")
        raise typer.Exit()

    repositories = get_repository_classes()
    player_repo = repositories.player()
    team_repo = repositories.team()
    game_repo = repositories.game()

    player_repo.reset()
    team_repo.reset()
    game_repo.reset()

    typer.echo("Truncated database")


def load_team(team_name: str) -> Team:
    """Load a team by name from the configured repository backend."""
    repo = get_repository_classes().team()
    for team in repo.list():
        if team.name == team_name:
            return team
    raise KeyError(f"Unknown team: {team_name}")


def format_player_name_for_display(player_name: str, player_index_by_name: dict[str, int]) -> str:
    """Return a Rich-formatted player name using a stable color."""
    if player_name in player_index_by_name:
        player_index = player_index_by_name[player_name]
        color = PLAYER_CONSOLE_COLORS[player_index % len(PLAYER_CONSOLE_COLORS)]
    else:
        color = "white"
    return f"[{color}]{player_name}[/{color}]"


def format_player_names_for_display(player_names: list[str], player_index_by_name: dict[str, int]) -> str:
    """Format a list of player names for display in a single table cell."""
    return ", ".join(
        format_player_name_for_display(player_name, player_index_by_name) for player_name in sorted(player_names)
    )


def normalize_player_input(player_inputs: list[str]) -> list[str]:
    """Split comma-delimited player input into a flat list of names."""
    normalized: list[str] = []
    for raw_value in player_inputs:
        for part in raw_value.split(","):
            cleaned = part.strip()
            if cleaned:
                normalized.append(cleaned)
    return normalized


def render_team_rules_table(team: Team) -> None:
    """Render a tabular view of the team rules and power combos."""
    console = Console()
    config = team.lineup_config
    if config is None:
        config = LineupConfig(team=team)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Rule Type")
    table.add_column("Value")

    if config.power_combos:
        for index, combo in enumerate(config.power_combos, start=1):
            table.add_row(f"Power combo {index}", " / ".join(combo))
    else:
        table.add_row("Power combo", "(none)")

    if config.required_final_period_players:
        table.add_row("Must be on at the end", ", ".join(config.required_final_period_players))
    else:
        table.add_row("Must be on at the end", "(none)")

    console.print(table)


def render_solution_display_data(display_data: dict[str, Any], config_snapshot: dict[str, Any] | None = None) -> None:
    """Render solved schedule tables and summary details from precomputed display data."""
    console = Console(force_terminal=True, color_system="truecolor")
    status = display_data.get("status", "UNKNOWN")
    first_half_rows = display_data.get("first_half_rows", [])
    second_half_rows = display_data.get("second_half_rows", [])
    summary_rows = display_data.get("summary_rows", [])

    if status in ("OPTIMAL", "FEASIBLE"):
        console.print(f"[bold green]Status:[/bold green] {status}")
        console.print()

        first_table = Table(show_header=True, header_style="bold cyan", border_style="blue")
        first_table.add_column("Period", style="dim", width=6)
        first_table.add_column("Time", style="magenta", width=10)
        first_table.add_column("On Court", style="green")
        first_table.add_column("Off Court", style="red")
        for period, time, on_court, off_court in first_half_rows:
            first_table.add_row(period, time, on_court, off_court)

        console.print("[bold cyan]── First Half ──[/bold cyan]")
        console.print(first_table)
        console.print()

        second_table = Table(show_header=True, header_style="bold cyan", border_style="blue")
        second_table.add_column("Period", style="dim", width=6)
        second_table.add_column("Time", style="magenta", width=10)
        second_table.add_column("On Court", style="green")
        second_table.add_column("Off Court", style="red")
        for period, time, on_court, off_court in second_half_rows:
            second_table.add_row(period, time, on_court, off_court)

        console.print("[bold cyan]── Second Half ──[/bold cyan]")
        console.print(second_table)
        console.print()

        summary_table = Table(show_header=True, header_style="bold cyan", border_style="blue")
        summary_table.add_column("Player", style="bold white")
        summary_table.add_column("On Count", style="green")
        summary_table.add_column("Off Count", style="red")
        for player, on_count, off_count in summary_rows:
            summary_table.add_row(player, on_count, off_count)

        console.print("[bold cyan]── Player Summary ──[/bold cyan]")
        console.print(summary_table)

        if config_snapshot:
            console.print()
            console.print("[bold]Lineup config snapshot[/bold]")
            power_combos = config_snapshot.get("power_combos", [])
            if power_combos:
                console.print("[bold]Power combos[/bold]")
                for combo in power_combos:
                    console.print(f"- {' / '.join(combo)}")
            required_players = config_snapshot.get("required_final_period_players", [])
            if required_players:
                console.print(f"[bold]Must be on at the end[/bold]: {', '.join(required_players)}")
    else:
        console.print("No solution found.")


def build_render_data_from_solution_snapshot(solution_snapshot: dict[str, Any]) -> dict[str, Any]:
    status = solution_snapshot.get("status", "UNKNOWN")
    players = solution_snapshot.get("players", [])
    periods_per_half = solution_snapshot.get("periods_per_half", [0, 0])
    period_start_times = solution_snapshot.get("period_start_times", [])
    player_periods = solution_snapshot.get("player_periods", [])

    if status not in ("OPTIMAL", "FEASIBLE"):
        return {"status": status, "first_half_rows": [], "second_half_rows": [], "summary_rows": []}

    player_index_by_name = {player_name: index for index, player_name in enumerate(players)}
    first_half_rows = []
    second_half_rows = []
    summary_rows = []

    for period_idx, period_start_time in enumerate(period_start_times):
        on_court = []
        off_court = []
        for player_period in player_periods:
            player_name = player_period.get("player", "")
            on = bool(player_period.get("on", [False] * len(period_start_times))[period_idx])
            if on:
                on_court.append(player_name)
            else:
                off_court.append(player_name)

        row = (
            str(period_idx + 1),
            period_start_time,
            format_player_names_for_display(on_court, player_index_by_name),
            format_player_names_for_display(off_court, player_index_by_name),
        )
        if period_idx < periods_per_half[0]:
            first_half_rows.append(row)
        else:
            second_half_rows.append(row)

    for player_period in player_periods:
        player_name = player_period.get("player", "")
        on_count = sum(bool(on_value) for on_value in player_period.get("on", []))
        off_count = len(period_start_times) - on_count
        summary_rows.append(
            (format_player_name_for_display(player_name, player_index_by_name), str(on_count), str(off_count))
        )

    return {
        "status": status,
        "first_half_rows": first_half_rows,
        "second_half_rows": second_half_rows,
        "summary_rows": summary_rows,
    }


@team_app.command("add", help="Create a new team with the provided players.", no_args_is_help=True)
def add_team(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    player_names: Annotated[list[str], typer.Argument(help="Player names to add to the team")],
) -> None:
    """Create a new team with the provided players."""
    team_repo = get_repository_classes().team()
    team = Team(name=team_name, players=[Player(name=player_name) for player_name in player_names])
    team_repo.save(team)
    typer.echo(f"Created team {team.name}")


@team_app.command("list", help="List available teams.")
def list_teams(
    team_filter: Annotated[str | None, typer.Option("--team", help="Optional team name filter")] = None,
) -> None:
    team_repo = get_repository_classes().team()
    console = Console()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Name")
    table.add_column("Players")
    for team in team_repo.list():
        if team_filter and team_filter not in team.name:
            continue
        table.add_row(team.name, ", ".join(player.name for player in team.players))
    console.print(table)


@team_app.command("show", help="Show the players and stored lineup settings for a team.", no_args_is_help=True)
def show_team(team_name: Annotated[str, typer.Argument(help="Team name")]) -> None:
    """Show the players and stored lineup settings for a team."""
    team = load_team(team_name)
    console = Console()
    console.print(f"[bold]{team.name}[/bold]")

    config = team.lineup_config
    if config is None:
        config = LineupConfig(team=team)

    console.print("\n[bold]Players[/bold]")
    for player in team.players:
        console.print(f"- {player.name}")

    if config.power_combos:
        console.print("\n[bold]Power combos[/bold]")
        for combo in config.power_combos:
            combo_names = " / ".join(combo)
            console.print(f"- {combo_names}")

    if config.required_final_period_players:
        required_players = ", ".join(config.required_final_period_players)
        console.print(f"\n[bold]Must be on at the end[/bold]: {required_players}")


@team_app.command("player-add", help="Add one or more players to a team roster.", no_args_is_help=True)
def add_team_players(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    player_names: Annotated[list[str], typer.Argument(help="Player names to add to the team")],
) -> None:
    """Add one or more players to a team roster."""
    team = load_team(team_name)
    team_repo = get_repository_classes().team()
    added: list[str] = []
    already_existed: list[str] = []

    for player_name in normalize_player_input(player_names):
        if team.get_player_by_name(player_name) is None:
            team.add_player(Player(name=player_name))
            added.append(player_name)
        else:
            already_existed.append(player_name)

    team_repo.save(team)
    if added:
        typer.echo(f"Added player{'s' if len(added) != 1 else ''} to {team.name}: {', '.join(added)}")
    if already_existed:
        typer.echo(f"Player{'s' if len(already_existed) != 1 else ''} already existed: {', '.join(already_existed)}")


@team_app.command("player-remove", help="Remove one or more players from a team roster.", no_args_is_help=True)
def remove_team_players(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    player_names: Annotated[list[str], typer.Argument(help="Player names to remove from the team")],
) -> None:
    """Remove one or more players from a team roster."""
    team = load_team(team_name)
    team_repo = get_repository_classes().team()

    names_to_remove = set(normalize_player_input(player_names))
    remaining_players = [player for player in team.players if player.name not in names_to_remove]
    team.players = remaining_players
    team_repo.save(team)
    typer.echo(f"Removed player{'s' if len(names_to_remove) != 1 else ''} from {team.name}")


@rule_app.command("list", help="List the team's stored rule data as a table.", no_args_is_help=True)
def list_team_rules(team_name: Annotated[str, typer.Argument(help="Team name")]) -> None:
    """List the team's stored rule data in a table."""
    team = load_team(team_name)
    render_team_rules_table(team)


@power_combo_app.command("list", help="List the team's power combos.", no_args_is_help=True)
def list_power_combos(team_name: Annotated[str, typer.Argument(help="Team name")]) -> None:
    """List the team's power combos in a table."""
    team = load_team(team_name)
    config = team.lineup_config or LineupConfig(team=team)

    console = Console()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#")
    table.add_column("Power Combo")
    for index, combo in enumerate(config.power_combos, start=1):
        table.add_row(str(index), " / ".join(combo))
    if not config.power_combos:
        table.add_row("-", "(none)")
    console.print(table)


@power_combo_app.command("add", help="Add a power combo to a team.", no_args_is_help=True)
def add_power_combo(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    player_names: Annotated[list[str], typer.Argument(help="Player names for the power combo")],
) -> None:
    """Add a power combo to a team."""
    team = load_team(team_name)
    team_repo = get_repository_classes().team()
    config = team.lineup_config or LineupConfig(team=team)

    combo = normalize_player_input(player_names)
    if len(combo) < 2:
        typer.echo("Power combos require at least two players")
        raise typer.Exit(code=1)

    config.power_combos.append(combo)
    team.lineup_config = config
    team_repo.save(team)
    typer.echo(f"Added power combo to {team.name}")


@power_combo_app.command("remove", help="Remove a power combo by number.", no_args_is_help=True)
def remove_power_combo(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    combo_number: Annotated[int, typer.Argument(help="Power-combo number to remove")],
) -> None:
    """Remove a power combo by its displayed number."""
    team = load_team(team_name)
    team_repo = get_repository_classes().team()
    config = team.lineup_config or LineupConfig(team=team)

    if combo_number < 1 or combo_number > len(config.power_combos):
        typer.echo("No such power combo")
        raise typer.Exit(code=1)

    del config.power_combos[combo_number - 1]
    team.lineup_config = config
    team_repo.save(team)
    typer.echo(f"Removed power combo {combo_number} from {team.name}")


@cleanup_app.command(
    "list", help="List the players that must be on the floor at the end of the game.", no_args_is_help=True
)
def list_cleanup_players(team_name: Annotated[str, typer.Argument(help="Team name")]) -> None:
    """List the players that must be on the floor at the end of the game."""
    team = load_team(team_name)
    config = team.lineup_config or LineupConfig(team=team)

    console = Console()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#")
    table.add_column("Player")
    for index, player_name in enumerate(config.required_final_period_players, start=1):
        table.add_row(str(index), player_name)
    if not config.required_final_period_players:
        table.add_row("-", "(none)")
    console.print(table)


@cleanup_app.command("add", help="Add players who must be on the floor at the end of the game.", no_args_is_help=True)
def add_cleanup_players(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    player_names: Annotated[list[str], typer.Argument(help="Players who must be on the floor at the end")],
) -> None:
    """Add players who must be on the floor at the end of the game."""
    team = load_team(team_name)
    team_repo = get_repository_classes().team()
    config = team.lineup_config or LineupConfig(team=team)

    for player_name in normalize_player_input(player_names):
        if player_name not in config.required_final_period_players:
            config.required_final_period_players.append(player_name)

    team.lineup_config = config
    team_repo.save(team)
    typer.echo(f"Added cleanup players to {team.name}")


@cleanup_app.command("remove", help="Remove a required cleanup player by number.", no_args_is_help=True)
def remove_cleanup_player(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    player_number: Annotated[int, typer.Argument(help="Cleanup-player number to remove")],
) -> None:
    """Remove a required cleanup player by its displayed number."""
    team = load_team(team_name)
    team_repo = get_repository_classes().team()
    config = team.lineup_config or LineupConfig(team=team)

    if player_number < 1 or player_number > len(config.required_final_period_players):
        typer.echo("No such cleanup player")
        raise typer.Exit(code=1)

    del config.required_final_period_players[player_number - 1]
    team.lineup_config = config
    team_repo.save(team)
    typer.echo(f"Removed cleanup player {player_number} from {team.name}")


@game_app.command("list", help="List games recorded for a team.", no_args_is_help=True)
def list_games(team_name: Annotated[str, typer.Argument(help="Team name")]) -> None:
    """List games recorded for a team."""
    team = load_team(team_name)
    game_repo = get_repository_classes().game()
    console = Console()
    for game in game_repo.list():
        if game.team_id == team.id:
            console.print(game.date or "(no date)")


@spin_app.command("list", help="List the recorded spins for a team and game.", no_args_is_help=True)
def list_spins(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
) -> None:
    """List the recorded spins for a team/game."""
    team = load_team(team_name)
    game_repo = get_repository_classes().game()
    game = game_repo.get_by_team_and_date(team.id, game_name)
    if game is None:
        typer.echo("No spins found")
        raise typer.Exit()
    console = Console()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim")
    table.add_column("Start")
    table.add_column("Away")
    table.add_column("Run Date")

    for spin in game.lineup_spins:
        timestamp = spin.created_at or "unknown"
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            localized = parsed.astimezone()
            offset = localized.strftime("%z")
            run_date = localized.strftime("%Y-%m-%d %H:%M:%S") + f" {offset[:3]}:{offset[3:]}"
        except ValueError:
            run_date = timestamp
        table.add_row(
            str(spin.number),
            ", ".join(player.name for player in spin.players),
            ", ".join(spin.away_players) if spin.away_players else "-",
            run_date,
        )

    console.print(table)


@spin_app.command("show", help="Show the full stored output for a specific spin.", no_args_is_help=True)
def show_spin(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
    spin_number: Annotated[int, typer.Argument(help="Spin number")],
) -> None:
    """Show the full stored output for a specific spin."""
    team = load_team(team_name)
    game_repo = get_repository_classes().game()
    game = game_repo.get_by_team_and_date(team.id, game_name)
    if game is None:
        typer.echo("No such game")
        raise typer.Exit()

    spin = next((item for item in game.lineup_spins if item.number == spin_number), None)
    if spin is None:
        typer.echo("No such spin")
        raise typer.Exit()

    console = Console()
    console.print(f"[bold]Run at[/bold]: {spin.created_at or 'unknown'}")
    console.print()

    solution_snapshot = spin.solution_snapshot
    if solution_snapshot:
        display_data = build_render_data_from_solution_snapshot(solution_snapshot)
        render_solution_display_data(display_data)
    else:
        typer.echo("No solution found.")

    if spin.config_snapshot:
        console = Console()
        console.print()
        console.print("[bold]Lineup config snapshot[/bold]")
        power_combos = spin.config_snapshot.get("power_combos", [])
        if power_combos:
            console.print("[bold]Power combos[/bold]")
            for combo in power_combos:
                console.print(f"- {' / '.join(combo)}")
        required_players = spin.config_snapshot.get("required_final_period_players", [])
        if required_players:
            console.print(f"[bold]Must be on at the end[/bold]: {', '.join(required_players)}")


@spin_app.command("run", help="Generate a new lineup spin for a team and game.", no_args_is_help=True)
def run_spin(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
    away_players: Annotated[list[str], typer.Option("--away", help="Player name(s) to exclude.", default_factory=list)],
    start_players: Annotated[
        list[str], typer.Option("--start", help="Player name(s) for the opening lineup.", default_factory=list)
    ],
) -> None:
    """Generate a new lineup spin for a team/game."""
    team = load_team(team_name)
    config = team.lineup_config or LineupConfig(team=team)
    game = solve_team_lineup(
        team,
        away_player_names=normalize_player_argument_values(away_players),
        requested_start_players=normalize_player_argument_values(start_players),
        config=config,
        game_repo=get_repository_classes().game(),
        game_date=game_name,
        render_output=False,
        player_console_colors=PLAYER_CONSOLE_COLORS,
    )
    if game is None:
        typer.echo("No solution found.")
        return

    spin = game.lineup_spins[-1]
    if spin.solution_snapshot:
        display_data = build_render_data_from_solution_snapshot(spin.solution_snapshot)
        render_solution_display_data(display_data, config_snapshot=spin.config_snapshot)


@spin_app.command("prune", help="Delete all spins for a team and game after confirmation.", no_args_is_help=True)
def prune_spins(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
) -> None:
    """Delete all spins for a team/game after confirmation."""
    team = load_team(team_name)
    game_repo = get_repository_classes().game()
    game = game_repo.get_by_team_and_date(team.id, game_name)
    if game is None:
        typer.echo("No such game")
        raise typer.Exit()

    confirm = typer.confirm("Are you sure?")
    if not confirm:
        typer.echo("Aborted")
        raise typer.Exit()

    game.lineup_spins = []
    game.selected_lineup_id = None
    game.renumber_spins()
    game_repo.save(game)
    typer.echo("Pruned spins")


@spin_app.command(
    "delete", help="Delete one or more spins for a team and game after confirmation.", no_args_is_help=True
)
def delete_spin(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
    spin_numbers: Annotated[list[int], typer.Argument(help="Spin number(s) to delete")],
) -> None:
    """Delete one or more spins for a team/game after confirmation."""
    team = load_team(team_name)
    game_repo = get_repository_classes().game()
    game = game_repo.get_by_team_and_date(team.id, game_name)
    if game is None:
        typer.echo("No such game")
        raise typer.Exit()

    matching_spins = [item for item in game.lineup_spins if item.number in spin_numbers]
    if not matching_spins:
        typer.echo("No such spin")
        raise typer.Exit()

    confirm = typer.confirm("Are you sure?")
    if not confirm:
        typer.echo("Aborted")
        raise typer.Exit()

    remaining_spins = [item for item in game.lineup_spins if item.number not in spin_numbers]
    game.lineup_spins = remaining_spins
    game.renumber_spins()
    if any(game.selected_lineup_id == spin.id for spin in matching_spins):
        game.selected_lineup_id = None
    game_repo.save(game)
    typer.echo("Deleted spin")


def main(argv: list[str] | None = None) -> None:
    """Run the CLI application."""
    if argv is None:
        app(prog_name="bball")
        return
    app(prog_name="bball", args=argv)


if __name__ == "__main__":
    main()
