from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from .models import LineupConfig, Team
from .repositories import SQLiteGameRepository, SQLiteTeamRepository
from .solver import normalize_player_argument_values, solve_team_lineup

app = typer.Typer(help="Basketball lineup optimizer and manager")
team_app = typer.Typer(help="Team-related commands")
game_app = typer.Typer(help="Game-related commands")
spin_app = typer.Typer(help="Spin-related commands")

app.add_typer(team_app, name="team")
app.add_typer(game_app, name="game")
game_app.add_typer(spin_app, name="spin")


def show_help_if_no_subcommand(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def root_callback(ctx: typer.Context) -> None:
    """Basketball lineup optimizer and manager."""
    show_help_if_no_subcommand(ctx)


@team_app.callback(invoke_without_command=True)
def team_callback(ctx: typer.Context) -> None:
    """Team-related commands."""
    show_help_if_no_subcommand(ctx)


@game_app.callback(invoke_without_command=True)
def game_callback(ctx: typer.Context) -> None:
    """Game-related commands."""
    show_help_if_no_subcommand(ctx)


@spin_app.callback(invoke_without_command=True)
def spin_callback(ctx: typer.Context) -> None:
    """Spin-related commands."""
    show_help_if_no_subcommand(ctx)


def load_team(team_name: str) -> Team:
    repo = SQLiteTeamRepository()
    for team in repo.list():
        if team.name == team_name:
            return team
    raise KeyError(f"Unknown team: {team_name}")


def render_solution_display_data(display_data: dict[str, Any]) -> None:
    """Render the solved schedule and summary tables to the console from precomputed display data."""
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
    else:
        typer.echo("No solution found.")


@team_app.command("list")
def list_teams(
    team_filter: Annotated[str | None, typer.Option("--team", help="Optional team name filter")] = None,
) -> None:
    team_repo = SQLiteTeamRepository()
    console = Console()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Name")
    table.add_column("Players")
    for team in team_repo.list():
        if team_filter and team_filter not in team.name:
            continue
        table.add_row(team.name, ", ".join(player.name for player in team.players))
    console.print(table)


@team_app.command("show")
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


@game_app.command("list")
def list_games(team_name: Annotated[str, typer.Argument(help="Team name")]) -> None:
    """List games recorded for a team."""
    team = load_team(team_name)
    game_repo = SQLiteGameRepository()
    console = Console()
    for game in game_repo.list():
        if game.team_id == team.id:
            console.print(game.date or "(no date)")


@spin_app.command("list")
def list_spins(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
) -> None:
    """List the recorded spins for a team/game."""
    team = load_team(team_name)
    game_repo = SQLiteGameRepository()
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
                parsed = parsed.replace(tzinfo=timezone.utc)
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


@spin_app.command("show")
def show_spin(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
    spin_number: Annotated[int, typer.Argument(help="Spin number")],
) -> None:
    """Show the full stored output for a specific spin."""
    team = load_team(team_name)
    game_repo = SQLiteGameRepository()
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

    display_data = spin.display_data or {
        "status": "OPTIMAL",
        "first_half_rows": [],
        "second_half_rows": [],
        "summary_rows": [],
    }
    render_solution_display_data(display_data)

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


@spin_app.command("run")
def run_spin(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
    away_players: Annotated[list[str], typer.Option("--away", help="Player name(s) to exclude.")] = [],
    start_players: Annotated[list[str], typer.Option("--start", help="Player name(s) for the opening lineup.")] = [],
) -> None:
    """Generate a new lineup spin for a team/game."""
    team = load_team(team_name)
    config = team.lineup_config or LineupConfig(team=team)
    solve_team_lineup(
        team,
        away_player_names=normalize_player_argument_values(away_players),
        requested_start_players=normalize_player_argument_values(start_players),
        config=config,
        game_repo=SQLiteGameRepository(),
        game_date=game_name,
        render_output=True,
    )


@spin_app.command("prune")
def prune_spins(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
) -> None:
    """Delete all spins for a team/game after confirmation."""
    team = load_team(team_name)
    game_repo = SQLiteGameRepository()
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


@spin_app.command("delete")
def delete_spin(
    team_name: Annotated[str, typer.Argument(help="Team name")],
    game_name: Annotated[str, typer.Argument(help="Game identifier")],
    spin_numbers: Annotated[list[int], typer.Argument(help="Spin number(s) to delete")],
) -> None:
    """Delete one or more spins for a team/game after confirmation."""
    team = load_team(team_name)
    game_repo = SQLiteGameRepository()
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
    if argv is None:
        app(prog_name="bball")
        return
    app(prog_name="bball", args=argv)


if __name__ == "__main__":
    main()
