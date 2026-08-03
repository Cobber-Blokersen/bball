from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from . import settings
from .models import LineupConfig, Player, Team, get_boolean_preference_definitions
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
never_on_first_app = typer.Typer(help="Opening-lineup rule commands", no_args_is_help=True)
game_app = typer.Typer(help="Game-related commands", no_args_is_help=True)
spin_app = typer.Typer(help="Spin-related commands", no_args_is_help=True)
system_app = typer.Typer(help="System maintenance commands", no_args_is_help=True)

app.add_typer(team_app, name="team")
team_app.add_typer(rule_app, name="rule")
rule_app.add_typer(power_combo_app, name="power-combo")
rule_app.add_typer(cleanup_app, name="cleanup")
rule_app.add_typer(never_on_first_app, name="never-on-first")
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


def format_player_name_for_display(
    player_name: str,
    player_index_by_name: dict[str, int],
    highlighted_player_names: set[str] | None = None,
) -> str:
    """Return a Rich-formatted player name using a stable color, optionally with reverse-video highlighting."""
    if player_name in player_index_by_name:
        player_index = player_index_by_name[player_name]
        color = PLAYER_CONSOLE_COLORS[player_index % len(PLAYER_CONSOLE_COLORS)]
    else:
        color = "white"

    if highlighted_player_names and player_name in highlighted_player_names:
        return f"[{color} reverse]{player_name}[/{color} reverse]"
    return f"[{color}]{player_name}[/{color}]"


def format_player_names_for_display(
    player_names: list[str],
    player_index_by_name: dict[str, int],
    highlighted_player_names: set[str] | None = None,
) -> str:
    """Format a list of player names for display in a single table cell."""
    return ", ".join(
        format_player_name_for_display(
            player_name,
            player_index_by_name,
            highlighted_player_names=highlighted_player_names,
        )
        for player_name in sorted(player_names)
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


def validate_players_are_team_members(team: Team, player_names: list[str]) -> None:
    """Reject any requested player names that are not currently on the team's roster."""
    known_player_names = {player.name for player in team.players}
    unknown_players = [player_name for player_name in player_names if player_name not in known_player_names]
    if unknown_players:
        typer.echo(f"Unknown player{'s' if len(unknown_players) != 1 else ''}: {', '.join(unknown_players)}")
        raise typer.Exit(code=1)


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

    if config.never_on_first_period_players:
        table.add_row("Never on at the start", ", ".join(config.never_on_first_period_players))
    else:
        table.add_row("Never on at the start", "(none)")

    console.print(table)


def render_solution_display_data(
    display_data: dict[str, Any],
    config_snapshot: dict[str, Any] | None = None,
    stats_rows: list[tuple[str, str, int]] | None = None,
    highlighted_player_names: set[str] | None = None,
) -> None:
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
            never_on_first_players = config_snapshot.get("never_on_first_period_players", [])
            if never_on_first_players:
                console.print(f"[bold]Never on at the start[/bold]: {', '.join(never_on_first_players)}")

        if stats_rows:
            console.print()
            console.print("[bold]Co-play stats[/bold]")
            stats_table = Table(show_header=True, header_style="bold cyan", border_style="blue")
            stats_table.add_column("Players")
            stats_table.add_column("Count")
            for player_pair, _, count in stats_rows:
                stats_table.add_row(player_pair, str(count))
            console.print(stats_table)
    else:
        console.print("No solution found.")


def build_render_data_from_solution_snapshot(
    solution_snapshot: dict[str, Any],
    highlighted_player_names: set[str] | None = None,
) -> dict[str, Any]:
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
            format_player_names_for_display(
                on_court,
                player_index_by_name,
                highlighted_player_names=highlighted_player_names,
            ),
            format_player_names_for_display(
                off_court,
                player_index_by_name,
                highlighted_player_names=highlighted_player_names,
            ),
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
            (
                format_player_name_for_display(
                    player_name,
                    player_index_by_name,
                    highlighted_player_names=highlighted_player_names,
                ),
                str(on_count),
                str(off_count),
            )
        )

    return {
        "status": status,
        "first_half_rows": first_half_rows,
        "second_half_rows": second_half_rows,
        "summary_rows": summary_rows,
    }


def build_co_play_stats(solution_snapshot: dict[str, Any]) -> list[tuple[str, str, int]]:
    """Return player-pair co-play counts sorted by descending frequency."""
    player_periods = solution_snapshot.get("player_periods", [])
    if not player_periods:
        return []

    player_names = [player_period.get("player", "") for player_period in player_periods]
    pair_counts: dict[tuple[str, str], int] = {}

    for period_idx in range(len(player_periods[0].get("on", []))):
        on_court_players = [
            player_name
            for player_period in player_periods
            if bool(player_period.get("on", [False])[period_idx])
            for player_name in [player_period.get("player", "")]
        ]
        if len(on_court_players) < 2:
            continue
        for index, player_name in enumerate(on_court_players):
            for other_player in on_court_players[index + 1 :]:
                pair = tuple(sorted((player_name, other_player)))
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

    return [
        (f"{left} / {right}", "", count)
        for (left, right), count in sorted(pair_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    ]


@team_app.command("add", help="Create a new team with the provided players.", no_args_is_help=True)
def add_team(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    player_names: Annotated[list[str], typer.Argument(help="Player names to add to the team")],
) -> None:
    """Create a new team with the provided players."""
    if len(player_names) == 1 and "," in player_names[0]:
        player_names = normalize_player_argument_values(player_names)
    team_repo = get_repository_classes().team()
    team = Team(name=team_name, players=[Player(name=player_name) for player_name in player_names])
    team_repo.save(team)
    typer.echo(f"Created team {team.name}")


@team_app.command("remove", help="Remove a team and all associated config and games.", no_args_is_help=True)
def remove_team(
    team_name: Annotated[str, typer.Argument(help="Team name")],
) -> None:
    """Delete a team after confirmation, including its config and games."""
    team = load_team(team_name)
    confirm = typer.confirm("Are you sure?")
    if not confirm:
        typer.echo("Aborted")
        raise typer.Exit()

    team_repo = get_repository_classes().team()
    game_repo = get_repository_classes().game()
    game_repo.delete_by_team(team.id)
    team_repo.delete(team.id)

    typer.echo(f"Removed team {team.name}")


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

    if config.never_on_first_period_players:
        required_players = ", ".join(config.never_on_first_period_players)
        console.print(f"\n[bold]Never on at the start[/bold]: {required_players}")


@team_app.command("preference-list", help="List the team's configurable lineup preferences.", no_args_is_help=True)
def list_team_preferences(team_name: Annotated[str, typer.Argument(help="Team name")]) -> None:
    """Show all configurable boolean lineup preferences for a team."""
    team = load_team(team_name)
    config = team.lineup_config or LineupConfig(team=team)

    console = Console()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Preference Key")
    table.add_column("Enabled")
    table.add_column("Description")

    for definition in get_boolean_preference_definitions():
        enabled = config.boolean_preferences.get(definition.key, definition.default_enabled)
        table.add_row(
            definition.key,
            "yes" if enabled else "no",
            definition.detailed_description,
        )

    console.print(table)


@team_app.command("preference-toggle", help="Enable or disable a team lineup preference.", no_args_is_help=True)
def toggle_team_preference(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    preference_key: Annotated[str, typer.Argument(help="Preference key")],
    enable: Annotated[bool, typer.Option("--enable", help="Enable the preference")] = False,
    disable: Annotated[bool, typer.Option("--disable", help="Disable the preference")] = False,
) -> None:
    """Toggle a team-specific boolean lineup preference."""
    team = load_team(team_name)
    team_repo = get_repository_classes().team()
    config = team.lineup_config or LineupConfig(team=team)

    definitions_by_key = {definition.key: definition for definition in get_boolean_preference_definitions()}
    if preference_key not in definitions_by_key:
        available = ", ".join(sorted(definitions_by_key))
        raise typer.BadParameter(f"Unknown preference key. Available options: {available}")

    current_value = config.boolean_preferences.get(preference_key, definitions_by_key[preference_key].default_enabled)
    if enable and disable:
        raise typer.BadParameter("Use either --enable or --disable, not both")
    if enable:
        new_value = True
    elif disable:
        new_value = False
    else:
        new_value = not current_value

    config.boolean_preferences[preference_key] = new_value
    team.lineup_config = config
    team_repo.save(team)

    state = "enabled" if new_value else "disabled"
    typer.echo(f"{definitions_by_key[preference_key].name}: {state}")


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
    validate_players_are_team_members(team, combo)
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


@never_on_first_app.command("list", help="List the players who should never start the game.", no_args_is_help=True)
def list_never_on_first_players(team_name: Annotated[str, typer.Argument(help="Team name")]) -> None:
    """List the players who should never start the game."""
    team = load_team(team_name)
    config = team.lineup_config or LineupConfig(team=team)

    console = Console()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#")
    table.add_column("Player")
    for index, player_name in enumerate(config.never_on_first_period_players, start=1):
        table.add_row(str(index), player_name)
    if not config.never_on_first_period_players:
        table.add_row("-", "(none)")
    console.print(table)


@never_on_first_app.command("add", help="Add players who should never start the game.", no_args_is_help=True)
def add_never_on_first_players(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    player_names: Annotated[list[str], typer.Argument(help="Players who should never start the game")],
) -> None:
    """Add players who should never be on court in the opening period."""
    team = load_team(team_name)
    team_repo = get_repository_classes().team()
    config = team.lineup_config or LineupConfig(team=team)

    normalized_player_names = normalize_player_input(player_names)
    validate_players_are_team_members(team, normalized_player_names)
    for player_name in normalized_player_names:
        if player_name not in config.never_on_first_period_players:
            config.never_on_first_period_players.append(player_name)

    team.lineup_config = config
    team_repo.save(team)
    typer.echo(f"Added never-on-first players to {team.name}")


@never_on_first_app.command("remove", help="Remove a never-on-first player by number.", no_args_is_help=True)
def remove_never_on_first_player(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    player_number: Annotated[int, typer.Argument(help="Never-on-first player number to remove")],
) -> None:
    """Remove a never-on-first player by its displayed number."""
    team = load_team(team_name)
    team_repo = get_repository_classes().team()
    config = team.lineup_config or LineupConfig(team=team)

    if player_number < 1 or player_number > len(config.never_on_first_period_players):
        typer.echo("No such never-on-first player")
        raise typer.Exit(code=1)

    del config.never_on_first_period_players[player_number - 1]
    team.lineup_config = config
    team_repo.save(team)
    typer.echo(f"Removed never-on-first player {player_number} from {team.name}")


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

    normalized_player_names = normalize_player_input(player_names)
    validate_players_are_team_members(team, normalized_player_names)
    for player_name in normalized_player_names:
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
    hl: Annotated[list[str], typer.Option("--hl", help="Player names to highlight in reverse colors.", default_factory=list)],
    stats: Annotated[bool, typer.Option("--stats", help="Show co-play statistics for the selected spin.")] = False,
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
        display_data = build_render_data_from_solution_snapshot(
            solution_snapshot,
            highlighted_player_names=set(normalize_player_argument_values(hl)),
        )
        stats_rows = build_co_play_stats(solution_snapshot) if stats else None
        highlighted_player_names = set(normalize_player_argument_values(hl))
        render_solution_display_data(
            display_data,
            stats_rows=stats_rows,
            highlighted_player_names=highlighted_player_names,
        )
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
        never_on_first_players = spin.config_snapshot.get("never_on_first_period_players", [])
        if never_on_first_players:
            console.print(f"[bold]Never on at the start[/bold]: {', '.join(never_on_first_players)}")


@spin_app.command("run", help="Generate a new lineup spin for a team and game.", no_args_is_help=True)
def run_spin(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
    away_players: Annotated[list[str], typer.Option("--away", help="Player name(s) to exclude.", default_factory=list)],
    start_players: Annotated[
        list[str], typer.Option("--start", help="Player name(s) for the opening lineup.", default_factory=list)
    ],
    hl: Annotated[list[str], typer.Option("--hl", help="Player names to highlight in reverse colors.", default_factory=list)],
) -> None:
    """Generate a new lineup spin for a team/game."""
    team = load_team(team_name)
    config = team.lineup_config or LineupConfig(team=team)

    normalized_start_players = normalize_player_argument_values(start_players)
    forbidden_start_players = set(config.never_on_first_period_players)
    conflicting_start_players = [player_name for player_name in normalized_start_players if player_name in forbidden_start_players]
    if conflicting_start_players:
        typer.echo(
            f"Cannot start the game with players who are marked never-on-first: {', '.join(conflicting_start_players)}"
        )
        raise typer.Exit(code=1)

    game = solve_team_lineup(
        team,
        away_player_names=normalize_player_argument_values(away_players),
        requested_start_players=normalized_start_players,
        config=config,
        game_repo=get_repository_classes().game(),
        game_date=game_name,
    )
    if game is None:
        typer.echo("No solution found.")
        return

    spin = game.lineup_spins[-1]
    if spin.solution_snapshot:
        display_data = build_render_data_from_solution_snapshot(
            spin.solution_snapshot,
            highlighted_player_names=set(normalize_player_argument_values(hl)),
        )
        highlighted_player_names = set(normalize_player_argument_values(hl))
        render_solution_display_data(
            display_data,
            config_snapshot=spin.config_snapshot,
            highlighted_player_names=highlighted_player_names,
        )


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
