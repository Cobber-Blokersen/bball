from ortools.sat.python import cp_model
from rich.console import Console
from rich.table import Table

PLAYERS = ["Indie", "Scarlett", "Mila", "Katrina",
           "Annabelle", "Hannah", "Sanavi", "Bhakti"]

# NOTE TO SELF: This seems to weight the top power combo most highly. Urpie thinks she might actually like that,
# and would jiggle them weekly as she fancies.
POWER_COMBOS = [
    ["Mila", "Katrina"], #, "Hannah"],
    ["Hannah", "Sanavi"],
    ["Indie", "Scarlett"]
]

STARTING_LINEUP = ["Indie", "Hannah", "Bhakti", "Annabelle", "Sanavi"]
MUST_BE_ON_IN_FINAL_PERIOD = ["Mila", "Katrina"]

PLAYER_COLORS = [
    "red",
    "white",
    "cyan",
    "yellow",
    "green",
    "blue",
    "bright_magenta",
    "orange1",
]

PLAYER_INDEX_BY_NAME = {player_name: index for index, player_name in enumerate(PLAYERS)}


def format_player_name(player_name: str) -> str:
    if player_name in PLAYER_INDEX_BY_NAME:
        player_index = PLAYER_INDEX_BY_NAME[player_name]
        color = PLAYER_COLORS[player_index % len(PLAYER_COLORS)]
    else:
        color = "white"
    return f"[{color}]{player_name}[/{color}]"


def format_player_names(player_names: list[str]) -> str:
    return ", ".join(format_player_name(player_name) for player_name in sorted(player_names))


def build_model(num_players: int, num_periods: int):
    model = cp_model.CpModel()
    is_on_court = {}
    for player_idx in range(num_players):
        for period_idx in range(num_periods):
            is_on_court[(player_idx, period_idx)] = model.new_bool_var(
                f"on_court_p{player_idx}_t{period_idx}"
            )
    return model, is_on_court


def add_player_count_constraints(model, is_on_court, num_players: int, num_periods: int, on_court_per_period: int):
    for period_idx in range(num_periods):
        model.add(
            sum(is_on_court[(player_idx, period_idx)] for player_idx in range(num_players))
            == on_court_per_period
        )


def add_playtime_balance_constraints(model, is_on_court, num_players: int, num_periods: int, periods_per_half: int):
    total_periods_played = []
    for player_idx in range(num_players):
        total_periods_for_player = model.new_int_var(0, num_periods, f"total_p{player_idx}")
        model.add(
            total_periods_for_player
            == sum(is_on_court[(player_idx, period_idx)] for period_idx in range(num_periods))
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
                    playing_time_difference
                    == total_periods_played[player_idx_a] - total_periods_played[player_idx_b]
                )
                model.add(playing_time_difference <= 1)
                model.add(playing_time_difference >= -1)

    off_balance_penalties = []
    for player_idx in range(num_players):
        first_half_on = model.new_int_var(0, periods_per_half, f"first_half_on_p{player_idx}")
        second_half_on = model.new_int_var(0, periods_per_half, f"second_half_on_p{player_idx}")
        model.add(
            first_half_on
            == sum(is_on_court[(player_idx, period_idx)] for period_idx in range(periods_per_half))
        )
        model.add(
            second_half_on
            == sum(
                is_on_court[(player_idx, period_idx)]
                for period_idx in range(periods_per_half, num_periods)
            )
        )

        half_split_diff = model.new_int_var(
            -periods_per_half, periods_per_half, f"half_split_diff_p{player_idx}"
        )
        model.add(half_split_diff == first_half_on - second_half_on)

        half_split_abs_diff = model.new_int_var(
            0, periods_per_half, f"half_split_abs_diff_p{player_idx}"
        )
        model.add_abs_equality(half_split_abs_diff, half_split_diff)
        off_balance_penalties.append(half_split_abs_diff)

    return off_balance_penalties


def add_no_consecutive_off_constraints(model, is_on_court, num_players: int, num_periods: int):
    for player_idx in range(num_players):
        for period_idx in range(num_periods - 1):
            model.add(
                is_on_court[(player_idx, period_idx)]
                + is_on_court[(player_idx, period_idx + 1)]
                >= 1
            )


def add_starting_lineup_constraints(model, is_on_court, players: list[str]):
    for player_idx, player_name in enumerate(players):
        if player_name in STARTING_LINEUP:
            model.add(is_on_court[(player_idx, 0)] == 1)
        else:
            model.add(is_on_court[(player_idx, 0)] == 0)


def add_final_period_constraints(model, is_on_court, player_indices: dict[str, int], num_periods: int):
    required_player_indices = [player_indices[player_name] for player_name in MUST_BE_ON_IN_FINAL_PERIOD]
    required_player_vars = [is_on_court[(player_idx, num_periods - 1)] for player_idx in required_player_indices]
    model.add(sum(required_player_vars) >= 1)


def add_transition_constraints(model, is_on_court, num_players: int, num_periods: int, periods_per_half: int):
    second_half_start = periods_per_half
    for player_idx in range(num_players):
        model.add_bool_or(
            [is_on_court[(player_idx, 0)], is_on_court[(player_idx, second_half_start)]]
        )

    for player_idx in range(num_players):
        model.add_bool_or(
            [is_on_court[(player_idx, 0)], is_on_court[(player_idx, num_periods - 1)]]
        )


def add_power_combo_objective(model, is_on_court, power_combos: list[list[str]], player_indices: dict[str, int], num_periods: int):
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


def set_objective(model, off_balance_penalties, power_combo_period_flags):
    primary_weight = 100
    secondary_weight = 5
    model.maximize(
        primary_weight * (-sum(off_balance_penalties))
        + secondary_weight * sum(power_combo_period_flags)
    )


def solve_model(model, time_limit: float = 60.0):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    status = solver.solve(model)
    return solver, status


def build_period_rows(solver, is_on_court, players: list[str], num_periods: int, periods_per_half: int, start_period: int):
    rows = []
    for period_idx in range(start_period, start_period + periods_per_half):
        on_court = []
        off_court = []
        for player_idx, player_name in enumerate(players):
            if solver.Value(is_on_court[(player_idx, period_idx)]) == 1:
                on_court.append(player_name)
            else:
                off_court.append(player_name)

        on_court.sort()
        off_court.sort()
        rows.append((str(period_idx + 1), format_player_names(on_court), format_player_names(off_court)))
    return rows


def render_solution(solver, status, is_on_court, players: list[str], periods_per_half: int, num_periods: int):
    console = Console(force_terminal=True, color_system="truecolor")
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        console.print(f"[bold green]Status:[/bold green] {solver.StatusName(status)}")
        console.print()

        first_table = Table(show_header=True, header_style="bold cyan", border_style="blue")
        first_table.add_column("Period", style="dim", width=6)
        first_table.add_column("On Court", style="green")
        first_table.add_column("Off Court", style="red")

        for period, on_court, off_court in build_period_rows(solver, is_on_court, players, num_periods, periods_per_half, 0):
            first_table.add_row(period, on_court, off_court)

        console.print("[bold cyan]── First Half ──[/bold cyan]")
        console.print(first_table)
        console.print()

        second_table = Table(show_header=True, header_style="bold cyan", border_style="blue")
        second_table.add_column("Period", style="dim", width=6)
        second_table.add_column("On Court", style="green")
        second_table.add_column("Off Court", style="red")

        for period, on_court, off_court in build_period_rows(solver, is_on_court, players, num_periods, periods_per_half, periods_per_half):
            second_table.add_row(period, on_court, off_court)

        console.print("[bold cyan]── Second Half ──[/bold cyan]")
        console.print(second_table)
        console.print()

        summary_table = Table(show_header=True, header_style="bold cyan", border_style="blue")
        summary_table.add_column("Player", style="bold white")
        summary_table.add_column("On Count", style="green")
        summary_table.add_column("Off Count", style="red")

        for player_idx, player_name in enumerate(players):
            on_count = 0
            off_count = 0
            for period_idx in range(num_periods):
                if solver.Value(is_on_court[(player_idx, period_idx)]) == 1:
                    on_count += 1
                else:
                    off_count += 1

            summary_table.add_row(format_player_name(player_name), str(on_count), str(off_count))

        console.print("[bold cyan]── Player Summary ──[/bold cyan]")
        console.print(summary_table)
    else:
        print("No solution found.")


def main():
    num_players = len(PLAYERS)
    periods_per_half = 6
    num_halves = 2
    num_periods = periods_per_half * num_halves
    on_court_per_period = 5

    model, is_on_court = build_model(num_players, num_periods)
    add_player_count_constraints(model, is_on_court, num_players, num_periods, on_court_per_period)
    off_balance_penalties = add_playtime_balance_constraints(model, is_on_court, num_players, num_periods, periods_per_half)
    add_no_consecutive_off_constraints(model, is_on_court, num_players, num_periods)
    add_starting_lineup_constraints(model, is_on_court, PLAYERS)
    add_final_period_constraints(model, is_on_court, PLAYER_INDEX_BY_NAME, num_periods)
    add_transition_constraints(model, is_on_court, num_players, num_periods, periods_per_half)
    power_combo_period_flags = add_power_combo_objective(model, is_on_court, POWER_COMBOS, PLAYER_INDEX_BY_NAME, num_periods)
    set_objective(model, off_balance_penalties, power_combo_period_flags)

    solver, status = solve_model(model)
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        render_solution(solver, status, is_on_court, PLAYERS, periods_per_half, num_periods)
    else:
        print("No solution found.")


if __name__ == "__main__":
    main()
