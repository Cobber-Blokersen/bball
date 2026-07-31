from __future__ import annotations

import argparse
import random
import uuid
from datetime import datetime
from typing import Any

from ortools.sat.python.cp_model import FEASIBLE, OPTIMAL, CpModel, CpSolver
from ortools.sat.python.cp_model_helper import CpSolverStatus
from rich.console import Console
from rich.table import Table

from .models import Game, LineupConfig, LineupSpin, Player, Team
from .repositories import GameRepository

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


def build_default_team() -> Team:
    players = [
        Player(name=name)
        for name in [
            "Indie",
            "Scarlett",
            "Mila",
            "Katrina",
            "Annabelle",
            "Hannah",
            "Sanavi",
            "Bhakti",
        ]
    ]
    return Team(
        id="1463e55b-341c-4d75-a8ae-a70fc3fb36cc",
        name="EDJBA Vikings U13 Girls 4 Winter 2026",
        players=players,
    )


def normalize_player_argument_values(argument_values: list[str]) -> list[str]:
    """Expand comma-delimited argument values and trim optional surrounding whitespace."""
    normalized_values = []
    for raw_value in argument_values:
        for candidate in raw_value.split(","):
            player_name = candidate.strip()
            if player_name:
                normalized_values.append(player_name)
    return normalized_values


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for this solver run."""
    parser = argparse.ArgumentParser(description="Solve the basketball lineup optimization problem")
    parser.add_argument(
        "--away",
        action="append",
        default=[],
        help="Player name(s) to exclude from this run; comma-delimited values and repeated flags are supported.",
    )
    parser.add_argument(
        "--start",
        action="append",
        default=[],
        help="Player name(s) for the opening lineup; comma-delimited values and repeated flags are supported.",
    )
    args = parser.parse_args()
    args.away = normalize_player_argument_values(args.away)
    args.start = normalize_player_argument_values(args.start)
    return args


def get_active_players(team: Team, away_player_names: list[str]) -> list[str]:
    """Return the roster of players still available for this run after removing away players."""
    away_player_set = set(away_player_names)
    team_player_names = {player.name for player in team.players}
    unknown_players = sorted(away_player_set - team_player_names)
    if unknown_players:
        raise ValueError(f"Unknown player name(s): {', '.join(unknown_players)}")
    return [player.name for player in team.players if player.name not in away_player_set]


def build_active_player_indices(active_players: list[str]) -> dict[str, int]:
    """Map each active player's name to their index in the reduced roster."""
    return {player_name: index for index, player_name in enumerate(active_players)}


def build_starting_lineup(
    active_players: list[str], requested_start_players: list[str], max_starters: int
) -> list[str]:
    """Build the opening-day starting lineup from requested starters and random fill-ins."""
    active_player_set = set(active_players)
    requested_starters = [
        player_name for player_name in dict.fromkeys(requested_start_players) if player_name in active_player_set
    ]

    starters = requested_starters[:max_starters]
    remaining_players = [player_name for player_name in active_players if player_name not in starters]
    if len(starters) < max_starters:
        random_fill = random.sample(
            remaining_players,
            k=min(max_starters - len(starters), len(remaining_players)),
        )
        starters.extend(random_fill)
    return starters


def filter_power_combos(active_players: list[str], power_combos: list[list[str]]) -> list[list[str]]:
    """Keep only power combos that are still meaningful with the active roster."""
    active_player_set = set(active_players)
    return [
        power_combo
        for power_combo in power_combos
        if len(power_combo) >= 2 and all(player_name in active_player_set for player_name in power_combo)
    ]


def filter_required_final_period_players(active_players: list[str], required_player_names: list[str]) -> list[str]:
    """Remove any final-period requirements that refer to away players."""
    active_player_set = set(active_players)
    return [player_name for player_name in required_player_names if player_name in active_player_set]


def build_player_index_by_name(player_names: list[str]) -> dict[str, int]:
    return {player_name: index for index, player_name in enumerate(player_names)}


def format_player_name(player_name: str, player_index_by_name: dict[str, int]) -> str:
    """Return a Rich-formatted player name using a stable color for that player."""
    if player_name in player_index_by_name:
        player_index = player_index_by_name[player_name]
        color = PLAYER_CONSOLE_COLORS[player_index % len(PLAYER_CONSOLE_COLORS)]
    else:
        color = "white"
    return f"[{color}]{player_name}[/{color}]"


def format_player_names(player_names: list[str], player_index_by_name: dict[str, int]) -> str:
    """Format a list of player names for display in a single table cell."""
    return ", ".join(format_player_name(player_name, player_index_by_name) for player_name in sorted(player_names))


def format_scoreboard_time(remaining_seconds: int) -> str:
    """Format a countdown time like the scoreboard, e.g. 20:00:00 or 0:00:00."""
    seconds = max(0, remaining_seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def build_period_start_times(periods_per_half: list[int], minutes_per_half: int) -> list[str]:
    """Calculate scoreboard countdown values for each period in each half."""
    first_half_period_seconds = minutes_per_half * 60 / periods_per_half[0]
    second_half_period_seconds = minutes_per_half * 60 / periods_per_half[1]

    period_start_times = []
    remaining_seconds = minutes_per_half * 60
    for _ in range(periods_per_half[0]):
        period_start_times.append(format_scoreboard_time(int(remaining_seconds)))
        remaining_seconds -= first_half_period_seconds

    remaining_seconds = minutes_per_half * 60
    for _ in range(periods_per_half[1]):
        period_start_times.append(format_scoreboard_time(int(remaining_seconds)))
        remaining_seconds -= second_half_period_seconds

    return period_start_times


def build_model(num_players: int, num_periods: int) -> tuple[CpModel, dict[tuple[int, int], Any]]:
    """Create the CP-SAT model and the boolean variables for each player-period pair."""
    model: CpModel = CpModel()
    is_on_court: dict[tuple[int, int], Any] = {}
    for player_idx in range(num_players):
        for period_idx in range(num_periods):
            is_on_court[(player_idx, period_idx)] = model.new_bool_var(f"on_court_p{player_idx}_t{period_idx}")
    return model, is_on_court


def add_player_count_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    num_players: int,
    num_periods: int,
    on_court_per_period: int,
) -> None:
    """Enforce that exactly one roster size of players is on court each period."""
    for period_idx in range(num_periods):
        model.add(
            sum(is_on_court[(player_idx, period_idx)] for player_idx in range(num_players)) == on_court_per_period
        )


def add_playtime_balance_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    num_players: int,
    num_periods: int,
    periods_per_half: list[int],
) -> list[Any]:
    """Balance total playing time across the roster and across the two (possibly uneven) halves."""
    total_periods_played = []
    for player_idx in range(num_players):
        total_periods_for_player = model.new_int_var(0, num_periods, f"total_p{player_idx}")
        model.add(
            total_periods_for_player == sum(is_on_court[(player_idx, period_idx)] for period_idx in range(num_periods))
        )
        total_periods_played.append(total_periods_for_player)

    for player_idx_a in range(num_players):
        for player_idx_b in range(num_players):
            if player_idx_a < player_idx_b:
                playing_time_difference = model.new_int_var(
                    -num_periods,
                    num_periods,
                    f"diff_{player_idx_a}_{player_idx_b}",
                )
                model.add(
                    playing_time_difference == total_periods_played[player_idx_a] - total_periods_played[player_idx_b]
                )
                model.add(playing_time_difference <= 1)
                model.add(playing_time_difference >= -1)

    first_half_periods = periods_per_half[0]
    second_half_periods = periods_per_half[1]
    second_half_start = first_half_periods

    off_balance_penalties = []
    for player_idx in range(num_players):
        first_half_on = model.new_int_var(0, first_half_periods, f"first_half_on_p{player_idx}")
        second_half_on = model.new_int_var(0, second_half_periods, f"second_half_on_p{player_idx}")
        model.add(
            first_half_on == sum(is_on_court[(player_idx, period_idx)] for period_idx in range(first_half_periods))
        )
        model.add(
            second_half_on
            == sum(is_on_court[(player_idx, period_idx)] for period_idx in range(second_half_start, num_periods))
        )

        half_split_diff = model.new_int_var(-num_periods, num_periods, f"half_split_diff_p{player_idx}")
        model.add(half_split_diff == first_half_on - second_half_on)

        half_split_abs_diff = model.new_int_var(0, num_periods, f"half_split_abs_diff_p{player_idx}")
        model.add_abs_equality(half_split_abs_diff, half_split_diff)
        off_balance_penalties.append(half_split_abs_diff)

    return off_balance_penalties


def add_no_consecutive_off_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    num_players: int,
    num_periods: int,
) -> None:
    """Prevent any player from being off court in two consecutive periods."""
    for player_idx in range(num_players):
        for period_idx in range(num_periods - 1):
            model.add(is_on_court[(player_idx, period_idx)] + is_on_court[(player_idx, period_idx + 1)] >= 1)


def add_starting_lineup_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    players: list[str],
    starting_lineup: list[str],
) -> None:
    """Force the opening-period lineup to match the selected starting lineup."""
    preferred_starting_player_set = set(starting_lineup)
    for player_idx, player_name in enumerate(players):
        model.add(is_on_court[(player_idx, 0)] == int(player_name in preferred_starting_player_set))


def add_final_period_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    player_indices: dict[str, int],
    num_periods: int,
    required_player_names: list[str],
) -> None:
    """Require at least one designated player to be on court in the final period."""
    if not required_player_names:
        return

    required_player_indices = [player_indices[player_name] for player_name in required_player_names]
    required_player_vars = [is_on_court[(player_idx, num_periods - 1)] for player_idx in required_player_indices]
    model.add(sum(required_player_vars) >= 1)


def add_transition_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    num_players: int,
    num_periods: int,
    periods_per_half: list[int],
) -> None:
    """Link the start of the second half and the end of the game to the opening-period state."""
    second_half_start = periods_per_half[0]
    for player_idx in range(num_players):
        model.add_bool_or([is_on_court[(player_idx, 0)], is_on_court[(player_idx, second_half_start)]])

    for player_idx in range(num_players):
        model.add_bool_or([is_on_court[(player_idx, 0)], is_on_court[(player_idx, num_periods - 1)]])


def add_power_combo_objective(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    power_combos: list[list[str]],
    player_indices: dict[str, int],
    num_periods: int,
) -> list[Any]:
    """Add objective variables that reward periods where any configured power combo is fully on court."""
    power_combo_together_flags = []
    for combo_index, power_combo in enumerate(power_combos):
        combo_flags = []
        combo_player_indices = [player_indices[player_name] for player_name in power_combo]
        for period_idx in range(num_periods):
            combo_on = model.new_bool_var(f"power_combo_{combo_index}_t{period_idx}")
            players_on = sum(is_on_court[(player_idx, period_idx)] for player_idx in combo_player_indices)
            model.add(players_on == len(power_combo)).only_enforce_if(combo_on)
            model.add(players_on != len(power_combo)).only_enforce_if(combo_on.Not())
            combo_flags.append(combo_on)
        power_combo_together_flags.append(combo_flags)

    power_combo_period_flags = []
    for period_idx in range(num_periods):
        period_power_combo = model.new_bool_var(f"period_power_combo_t{period_idx}")
        combo_flags_for_period = [combo_flags[period_idx] for combo_flags in power_combo_together_flags]
        model.add(sum(combo_flags_for_period) >= 1).only_enforce_if(period_power_combo)
        model.add(sum(combo_flags_for_period) == 0).only_enforce_if(period_power_combo.Not())
        power_combo_period_flags.append(period_power_combo)

    return power_combo_period_flags


def set_objective(
    model: CpModel,
    off_balance_penalties: list[Any],
    power_combo_period_flags: list[Any],
) -> None:
    """Set the weighted objective for balance and preferred power-combo periods."""
    primary_weight = 100
    secondary_weight = 5
    model.maximize(primary_weight * (-sum(off_balance_penalties)) + secondary_weight * sum(power_combo_period_flags))


def solve_model(model: CpModel, time_limit: float = 60.0) -> tuple[CpSolver, CpSolverStatus]:
    """Solve the CP-SAT model and return the solver plus the resulting status."""
    solver = CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    status = solver.solve(model)
    return solver, status


def build_period_rows(  # noqa: PLR0917
    solver: CpSolver,
    is_on_court: dict[tuple[int, int], Any],
    players: list[str],
    periods_in_section: int,
    start_period: int,
    period_start_times: list[str],
    player_index_by_name: dict[str, int],
) -> list[tuple[str, str, str, str]]:
    """Build the display rows for a contiguous section of the schedule."""
    rows = []
    for period_idx in range(start_period, start_period + periods_in_section):
        on_court = []
        off_court = []
        for player_idx, player_name in enumerate(players):
            if solver.Value(is_on_court[(player_idx, period_idx)]) == 1:
                on_court.append(player_name)
            else:
                off_court.append(player_name)

        on_court.sort()
        off_court.sort()
        rows.append(
            (
                str(period_idx + 1),
                period_start_times[period_idx],
                format_player_names(on_court, player_index_by_name),
                format_player_names(off_court, player_index_by_name),
            )
        )
    return rows


def build_solution_display_data(  # noqa: PLR0917
    solver: CpSolver,
    status: CpSolverStatus,
    is_on_court: dict[tuple[int, int], Any],
    players: list[str],
    periods_per_half: list[int],
    num_periods: int,
    minutes_per_half: int,
) -> dict[str, Any]:
    """Build the display rows used to render a solved schedule and summary tables."""
    player_index_by_name = build_player_index_by_name(players)
    if status not in (OPTIMAL, FEASIBLE):
        return {"status": solver.StatusName(status), "first_half_rows": [], "second_half_rows": [], "summary_rows": []}

    period_start_times = build_period_start_times(periods_per_half, minutes_per_half)
    first_half_rows = [
        row
        for row in build_period_rows(
            solver,
            is_on_court,
            players,
            periods_per_half[0],
            0,
            period_start_times,
            player_index_by_name,
        )
    ]

    second_half_rows = []
    second_half_start = periods_per_half[0]
    second_half_rows.extend(
        build_period_rows(
            solver,
            is_on_court,
            players,
            periods_per_half[1],
            second_half_start,
            period_start_times,
            player_index_by_name,
        )
    )

    summary_rows = []
    for player_idx, player_name in enumerate(players):
        on_count = 0
        off_count = 0
        for period_idx in range(num_periods):
            if solver.Value(is_on_court[(player_idx, period_idx)]) == 1:
                on_count += 1
            else:
                off_count += 1

        summary_rows.append((format_player_name(player_name, player_index_by_name), str(on_count), str(off_count)))

    return {
        "status": solver.StatusName(status),
        "first_half_rows": first_half_rows,
        "second_half_rows": second_half_rows,
        "summary_rows": summary_rows,
    }


def render_solution_display_data(display_data: dict[str, Any], config_snapshot: dict[str, Any] | None = None) -> None:
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
        print("No solution found.")


def render_solution(  # noqa: PLR0917
    solver: CpSolver,
    status: CpSolverStatus,
    is_on_court: dict[tuple[int, int], Any],
    players: list[str],
    periods_per_half: list[int],
    num_periods: int,
    minutes_per_half: int,
    config_snapshot: dict[str, Any] | None = None,
) -> None:
    """Render the solved schedule and summary tables to the console."""
    display_data = build_solution_display_data(
        solver,
        status,
        is_on_court,
        players,
        periods_per_half,
        num_periods,
        minutes_per_half,
    )
    render_solution_display_data(display_data, config_snapshot=config_snapshot)


def solve_team_lineup(  # noqa: PLR0917
    team: Team,
    away_player_names: list[str] | None = None,
    requested_start_players: list[str] | None = None,
    config: LineupConfig | None = None,
    game_repo: GameRepository | None = None,
    game_date: str | None = None,
    render_output: bool = True,
) -> Game | None:
    """Solve a lineup for a team and persist a simple game-day lineup spin."""
    away_player_names = away_player_names or []
    requested_start_players = requested_start_players or []

    if config is None:
        config = team.lineup_config or LineupConfig(team=team)

    active_players = get_active_players(team, away_player_names)
    active_player_indices = build_active_player_indices(active_players)
    active_power_combos = filter_power_combos(active_players, config.power_combos)
    required_final_period_players = filter_required_final_period_players(
        active_players, config.required_final_period_players
    )
    starting_lineup = build_starting_lineup(active_players, requested_start_players, config.on_court_per_period)

    if len(config.periods_per_half) != 2:
        raise ValueError("periods_per_half must contain exactly two entries, e.g. [6, 6] or [6, 5].")

    num_players = len(active_players)
    num_periods = sum(config.periods_per_half)

    model, is_on_court = build_model(num_players, num_periods)
    add_player_count_constraints(model, is_on_court, num_players, num_periods, config.on_court_per_period)
    off_balance_penalties = add_playtime_balance_constraints(
        model, is_on_court, num_players, num_periods, config.periods_per_half
    )
    add_no_consecutive_off_constraints(model, is_on_court, num_players, num_periods)
    add_starting_lineup_constraints(model, is_on_court, active_players, starting_lineup)
    add_final_period_constraints(
        model,
        is_on_court,
        active_player_indices,
        num_periods,
        required_final_period_players,
    )
    add_transition_constraints(model, is_on_court, num_players, num_periods, config.periods_per_half)
    power_combo_period_flags = add_power_combo_objective(
        model, is_on_court, active_power_combos, active_player_indices, num_periods
    )
    set_objective(model, off_balance_penalties, power_combo_period_flags)

    solver, status = solve_model(model)
    if status in (OPTIMAL, FEASIBLE):
        opening_lineup = [
            player_name
            for player_idx, player_name in enumerate(active_players)
            if solver.Value(is_on_court[(player_idx, 0)]) == 1
        ]
        opening_lineup.sort()

        if game_repo is not None and game_date:
            game = game_repo.get_by_team_and_date(team.id, game_date)
            if game is None:
                game = Game(
                    id=str(uuid.uuid4()),
                    team_id=team.id,
                    date=game_date,
                    lineup_spins=[],
                    selected_lineup_id=None,
                )
            spin_number = game.get_next_spin_number()
            display_data = build_solution_display_data(
                solver,
                status,
                is_on_court,
                active_players,
                config.periods_per_half,
                num_periods,
                config.minutes_per_half,
            )
            spin = LineupSpin(
                id=str(uuid.uuid4()),
                number=spin_number,
                players=[Player(name=player_name) for player_name in opening_lineup],
                created_at=datetime.utcnow().isoformat(),
                display_data=display_data,
                config_snapshot={
                    "power_combos": active_power_combos,
                    "required_final_period_players": required_final_period_players,
                    "periods_per_half": list(config.periods_per_half),
                    "on_court_per_period": config.on_court_per_period,
                    "minutes_per_half": config.minutes_per_half,
                },
                away_players=list(away_player_names),
            )
            game.add_spin(spin)
            game.selected_lineup_id = spin.id
            game_repo.save(game)
        else:
            display_data = build_solution_display_data(
                solver,
                status,
                is_on_court,
                active_players,
                config.periods_per_half,
                num_periods,
                config.minutes_per_half,
            )
            spin = LineupSpin(
                id=str(uuid.uuid4()),
                number=1,
                players=[Player(name=player_name) for player_name in opening_lineup],
                created_at=datetime.utcnow().isoformat(),
                display_data=display_data,
                config_snapshot={
                    "power_combos": active_power_combos,
                    "required_final_period_players": required_final_period_players,
                    "periods_per_half": list(config.periods_per_half),
                    "on_court_per_period": config.on_court_per_period,
                    "minutes_per_half": config.minutes_per_half,
                },
                away_players=list(away_player_names),
            )
            game = Game(
                id=str(uuid.uuid4()),
                team_id=team.id,
                date=game_date or "",
                lineup_spins=[spin],
                selected_lineup_id=spin.id,
            )
            if game_repo is not None:
                game_repo.save(game)

        if render_output:
            render_solution(
                solver,
                status,
                is_on_court,
                active_players,
                config.periods_per_half,
                num_periods,
                config.minutes_per_half,
                config_snapshot={
                    "power_combos": active_power_combos,
                    "required_final_period_players": required_final_period_players,
                    "periods_per_half": list(config.periods_per_half),
                    "on_court_per_period": config.on_court_per_period,
                    "minutes_per_half": config.minutes_per_half,
                },
            )
        return game

    return None
