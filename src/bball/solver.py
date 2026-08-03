from __future__ import annotations

import argparse
import random
import uuid
from datetime import UTC, datetime
from typing import Any

from ortools.sat.python.cp_model import FEASIBLE, OPTIMAL, CpModel, CpSolver
from ortools.sat.python.cp_model_helper import CpSolverStatus

from .models import Game, LineupConfig, LineupSpin, Player, Team
from .repositories import GameRepository


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
    active_players: list[str],
    requested_start_players: list[str],
    max_starters: int,
    forbidden_start_players: list[str] | None = None,
    power_combos: list[list[str]] | None = None,
) -> list[str]:
    """Build the opening-day starting lineup from requested starters, power combos, and random fill-ins."""
    active_player_set = set(active_players)
    forbidden_player_set = set(forbidden_start_players or [])
    requested_starters = [
        player_name
        for player_name in dict.fromkeys(requested_start_players)
        if player_name in active_player_set and player_name not in forbidden_player_set
    ]

    if requested_starters:
        starters = requested_starters[:max_starters]
    else:
        starters = []
        seen_starters: set[str] = set()
        if power_combos:
            for power_combo in power_combos:
                for player_name in power_combo:
                    if (
                        player_name in active_player_set
                        and player_name not in forbidden_player_set
                        and player_name not in seen_starters
                    ):
                        starters.append(player_name)
                        seen_starters.add(player_name)
                        if len(starters) >= max_starters:
                            break
                if len(starters) >= max_starters:
                    break

    remaining_players = [
        player_name
        for player_name in active_players
        if player_name not in starters and player_name not in forbidden_player_set
    ]
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


def filter_never_on_first_period_players(active_players: list[str], required_player_names: list[str]) -> list[str]:
    """Remove any opening-period restrictions that refer to away players."""
    active_player_set = set(active_players)
    return [player_name for player_name in required_player_names if player_name in active_player_set]


def build_player_index_by_name(player_names: list[str]) -> dict[str, int]:
    return {player_name: index for index, player_name in enumerate(player_names)}


def format_player_name(
    player_name: str,
    player_index_by_name: dict[str, int],
    player_console_colors: list[str] | None = None,
) -> str:
    """Return a Rich-formatted player name using a stable color for that player."""
    if player_name in player_index_by_name:
        player_index = player_index_by_name[player_name]
        color = player_console_colors[player_index % len(player_console_colors)] if player_console_colors else "white"
    else:
        color = "white"
    return f"[{color}]{player_name}[/{color}]"


def format_player_names(
    player_names: list[str],
    player_index_by_name: dict[str, int],
    player_console_colors: list[str] | None = None,
) -> str:
    """Format a list of player names for display in a single table cell."""
    return ", ".join(
        format_player_name(player_name, player_index_by_name, player_console_colors=player_console_colors)
        for player_name in sorted(player_names)
    )


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


def add_total_playtime_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    num_players: int,
    num_periods: int,
) -> list[Any]:
    """Track each player's total on-court periods for even rotation across the roster."""
    total_periods_played = []
    for player_idx in range(num_players):
        total_periods_for_player = model.new_int_var(0, num_periods, f"total_p{player_idx}")
        model.add(
            total_periods_for_player == sum(is_on_court[(player_idx, period_idx)] for period_idx in range(num_periods))
        )
        total_periods_played.append(total_periods_for_player)
    return total_periods_played


def add_pairwise_playtime_balance_constraints(
    model: CpModel,
    num_players: int,
    num_periods: int,
    total_periods_played: list[Any],
) -> None:
    """Keep every pair of players within one period of each other in total playing time."""
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


def add_half_split_balance_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    num_players: int,
    num_periods: int,
    periods_per_half: list[int],
) -> list[Any]:
    """Penalize uneven first-half versus second-half playtime for each player."""
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


def add_playtime_balance_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    num_players: int,
    num_periods: int,
    periods_per_half: list[int],
) -> list[Any]:
    """Balance total playtime and keep each half evenly distributed across the roster."""
    total_periods_played = add_total_playtime_constraints(model, is_on_court, num_players, num_periods)
    add_pairwise_playtime_balance_constraints(model, num_players, num_periods, total_periods_played)
    return add_half_split_balance_constraints(model, is_on_court, num_players, num_periods, periods_per_half)


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


def add_final_period_mandatory_player_constraints(
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


def add_never_on_first_constraints(
    model: CpModel,
    is_on_court: dict[tuple[int, int], Any],
    player_indices: dict[str, int],
    required_player_names: list[str],
) -> None:
    """Prevent designated players from being on court in the opening period."""
    if not required_player_names:
        return

    required_player_indices = [player_indices[player_name] for player_name in required_player_names]
    required_player_vars = [is_on_court[(player_idx, 0)] for player_idx in required_player_indices]
    model.add(sum(required_player_vars) == 0)


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
    player_console_colors: list[str] | None = None,
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
                format_player_names(on_court, player_index_by_name, player_console_colors=player_console_colors),
                format_player_names(off_court, player_index_by_name, player_console_colors=player_console_colors),
            )
        )
    return rows


def build_solution_snapshot(  # noqa: PLR0917
    solver: CpSolver,
    status: CpSolverStatus,
    is_on_court: dict[tuple[int, int], Any],
    players: list[str],
    periods_per_half: list[int],
    num_periods: int,
    minutes_per_half: int,
) -> dict[str, Any]:
    """Build a structured snapshot of the solved assignments for persistence and later re-rendering."""
    # player_index_by_name = build_player_index_by_name(players)
    if status not in (OPTIMAL, FEASIBLE):
        return {
            "status": solver.StatusName(status),
            "players": players,
            "periods_per_half": list(periods_per_half),
            "period_start_times": [],
            "player_periods": [],
        }

    period_start_times = build_period_start_times(periods_per_half, minutes_per_half)
    player_periods = []
    for player_idx, player_name in enumerate(players):
        player_periods.append(
            {
                "player": player_name,
                "on": [bool(solver.Value(is_on_court[(player_idx, period_idx)])) for period_idx in range(num_periods)],
            }
        )

    return {
        "status": solver.StatusName(status),
        "players": players,
        "periods_per_half": list(periods_per_half),
        "period_start_times": period_start_times,
        "player_periods": player_periods,
    }


def solve_team_lineup(  # noqa: PLR0917
    team: Team,
    away_player_names: list[str] | None = None,
    requested_start_players: list[str] | None = None,
    config: LineupConfig | None = None,
    game_repo: GameRepository | None = None,
    game_date: str | None = None,
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
    never_on_first_period_players = filter_never_on_first_period_players(
        active_players, config.never_on_first_period_players
    )
    starting_lineup = build_starting_lineup(
        active_players,
        requested_start_players,
        config.on_court_per_period,
        forbidden_start_players=never_on_first_period_players,
        power_combos=active_power_combos,
    )

    if len(config.periods_per_half) != 2:
        raise ValueError("periods_per_half must contain exactly two entries, e.g. [6, 6] or [6, 5].")

    num_players = len(active_players)
    num_periods = sum(config.periods_per_half)

    model, is_on_court = build_model(num_players, num_periods)

    # Mandatory constraint - alters feasibility of the model, so must be added first
    add_player_count_constraints(model, is_on_court, num_players, num_periods, config.on_court_per_period)

    total_periods_played = add_total_playtime_constraints(model, is_on_court, num_players, num_periods)
    add_pairwise_playtime_balance_constraints(model, num_players, num_periods, total_periods_played)

    off_balance_penalties: list[Any] = []

    if config.boolean_preferences["half_split_balance"]:
        off_balance_penalties = add_half_split_balance_constraints(
            model, is_on_court, num_players, num_periods, config.periods_per_half
        )

    if config.boolean_preferences["no_consecutive_off"]:
        add_no_consecutive_off_constraints(model, is_on_court, num_players, num_periods)

    # No config preference required - just don't add starting players if none are specified
    add_starting_lineup_constraints(model, is_on_court, active_players, starting_lineup)

    # No config preference required - just don't add final-period requirements if none are specified
    add_final_period_mandatory_player_constraints(
        model,
        is_on_court,
        active_player_indices,
        num_periods,
        required_final_period_players,
    )

    add_never_on_first_constraints(
        model,
        is_on_court,
        active_player_indices,
        never_on_first_period_players,
    )

    if config.boolean_preferences["transition_constraints"]:
        add_transition_constraints(model, is_on_court, num_players, num_periods, config.periods_per_half)

    if config.boolean_preferences["power_combo_objective"]:
        power_combo_period_flags = add_power_combo_objective(
            model, is_on_court, active_power_combos, active_player_indices, num_periods
        )
    else:
        power_combo_period_flags = []

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
            solution_snapshot = build_solution_snapshot(
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
                created_at=datetime.now(UTC).isoformat(),
                solution_snapshot=solution_snapshot,
                config_snapshot={
                    "power_combos": active_power_combos,
                    "required_final_period_players": required_final_period_players,
                    "never_on_first_period_players": never_on_first_period_players,
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
            solution_snapshot = build_solution_snapshot(
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
                created_at=datetime.now(UTC).isoformat(),
                solution_snapshot=solution_snapshot,
                config_snapshot={
                    "power_combos": active_power_combos,
                    "required_final_period_players": required_final_period_players,
                    "never_on_first_period_players": never_on_first_period_players,
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

        return game

    return None
