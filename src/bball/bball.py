from ortools.sat.python import cp_model
from rich.console import Console
from rich.table import Table


def main():
    # --- Basic setup ---
    players = ["Indie", "Scarlett", "Mila", "Katrina",
               "Annabelle", "Hannah", "Sanavi", "Bhakti"]
        
    num_players = len(players)

    periods_per_half = 6  # or 5 – you can make this a parameter
    num_halves = 2
    num_periods = periods_per_half * num_halves

    on_court_per_period = 5

    # --- Model ---
    model = cp_model.CpModel()

    # is_on_court[(player_idx, period_idx)] = 1 when player is on court in that period.
    is_on_court = {}
    for player_idx in range(num_players):
        for period_idx in range(num_periods):
            is_on_court[(player_idx, period_idx)] = model.new_bool_var(
                f"on_court_p{player_idx}_t{period_idx}"
            )

    # --- Constraint: exactly 5 players on court each period ---
    for period_idx in range(num_periods):
        model.add(
            sum(is_on_court[(player_idx, period_idx)] for player_idx in range(num_players))
            == on_court_per_period
        )

    # --- Constraint: near-equal total playing time (difference ≤ 1 period) ---
    total_periods_played = []
    for player_idx in range(num_players):
        total_periods_for_player = model.new_int_var(
            0, num_periods, f"total_p{player_idx}"
        )
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

    # --- Constraint: no player off court for consecutive periods ---
    # Off court means is_on_court[(player_idx, period_idx)] == 0.
    # Enforce: not (off at period_idx and off at period_idx + 1).
    for player_idx in range(num_players):
        for period_idx in range(num_periods - 1):
            # At least one adjacent period must be ON court.
            model.add(
                is_on_court[(player_idx, period_idx)]
                + is_on_court[(player_idx, period_idx + 1)]
                >= 1
            )

    # --- Starting lineup: Period 0 (first period) ---
    # Start on: Indie(0), Scarlett(1), Mila(2), Annabelle(4), Sanavi(6)
    # starting_lineup = ["Indie", "Scarlett", "Mila", "Annabelle", "Sanavi"]
    starting_lineup = ["Katrina", "Bhakti", "Indie", "Scarlett", "Sanavi"]
    for player_idx, player_name in enumerate(players):
        if player_name in starting_lineup:
            model.add(is_on_court[(player_idx, 0)] == 1)
        else:
            model.add(is_on_court[(player_idx, 0)] == 0)

    # --- Mila must be on court in final period ---
    mila_index = players.index("Mila")
    model.add(is_on_court[(mila_index, num_periods - 1)] == 1)

    # --- Players who start OFF in Period 0 must not also start OFF in first period of second half ---
    # First period of second half = period periods_per_half
    second_half_start = periods_per_half
    for player_idx in range(num_players):
        # If off at period 0, then must be on at the second-half start.
        # is_on_court[player_idx,0] == 0 => is_on_court[player_idx,second_half_start] == 1
        model.add_bool_or(
            [is_on_court[(player_idx, 0)], is_on_court[(player_idx, second_half_start)]]
        )

    # --- Players who start OFF at start must not also be OFF at end ---
    for player_idx in range(num_players):
        # is_on_court[player_idx,0] == 0 => is_on_court[player_idx,last] == 1
        model.add_bool_or(
            [is_on_court[(player_idx, 0)], is_on_court[(player_idx, num_periods - 1)]]
        )

    # --- Objective term 1: maximise periods where Mila and Katrina are on together ---
    katrina_index = players.index("Katrina")
    mila_katrina_together_flags = []
    for period_idx in range(num_periods):
        mila_katrina_both_on = model.new_bool_var(f"mila_kat_t{period_idx}")
        # mila_katrina_both_on == 1 iff Mila and Katrina are both on court.
        model.add(
            is_on_court[(mila_index, period_idx)] + is_on_court[(katrina_index, period_idx)]
            == 2
        ).only_enforce_if(mila_katrina_both_on)
        model.add(
            is_on_court[(mila_index, period_idx)] + is_on_court[(katrina_index, period_idx)]
            != 2
        ).only_enforce_if(mila_katrina_both_on.Not())
        mila_katrina_together_flags.append(mila_katrina_both_on)

    # --- Objective term 3: prefer Hannah and Sanavi on court together ---
    hannah_index = players.index("Hannah")
    sanavi_index = players.index("Sanavi")
    hannah_sanavi_together_flags = []
    for period_idx in range(num_periods):
        hannah_sanavi_both_on = model.new_bool_var(f"han_san_t{period_idx}")
        model.add(
            is_on_court[(hannah_index, period_idx)] + is_on_court[(sanavi_index, period_idx)]
            == 2
        ).only_enforce_if(hannah_sanavi_both_on)
        model.add(
            is_on_court[(hannah_index, period_idx)] + is_on_court[(sanavi_index, period_idx)]
            != 2
        ).only_enforce_if(hannah_sanavi_both_on.Not())
        hannah_sanavi_together_flags.append(hannah_sanavi_both_on)

    # --- Objective term 2: balance each player's off-court periods across halves ---
    # Minimising |off_first_half - off_second_half| is equivalent to minimising
    # |on_first_half - on_second_half| because each half has the same number of periods.
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

    # Weighted objective:
    # 1) prioritise balanced off-court splits across halves,
    # 2) use Mila+Katrina together as a secondary preference,
    # 3) use Hannah+Sanavi together as a tertiary preference.
    
    primary_weight = 100
    secondary_weight = 5
    tertiary_weight = 1
    model.maximize(
        primary_weight * (-sum(off_balance_penalties))
        + secondary_weight * sum(mila_katrina_together_flags)
        + tertiary_weight * sum(hannah_sanavi_together_flags)
    )

    # --- Solve ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0  # tweak if needed
    status = solver.solve(model)

    console = Console(force_terminal=True, color_system="truecolor")

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        console.print(f"[bold green]Status:[/bold green] {solver.StatusName(status)}")
        console.print()

        # First half
        first_table = Table(show_header=True, header_style="bold cyan", border_style="blue")
        first_table.add_column("Period", style="dim", width=6)
        first_table.add_column("On Court", style="green")
        first_table.add_column("Off Court", style="red")

        for period_idx in range(periods_per_half):
            on_court = []
            off_court = []
            for player_idx, player_name in enumerate(players):
                if solver.Value(is_on_court[(player_idx, period_idx)]) == 1:
                    on_court.append(player_name)
                else:
                    off_court.append(player_name)

            on_court.sort()
            off_court.sort()

            first_table.add_row(
                str(period_idx + 1), ", ".join(on_court), ", ".join(off_court)
            )

        console.print("[bold cyan]── First Half ──[/bold cyan]")
        console.print(first_table)
        console.print()

        # Second half
        second_table = Table(show_header=True, header_style="bold cyan", border_style="blue")
        second_table.add_column("Period", style="dim", width=6)
        second_table.add_column("On Court", style="green")
        second_table.add_column("Off Court", style="red")

        for period_idx in range(periods_per_half, num_periods):
            on_court = []
            off_court = []
            for player_idx, player_name in enumerate(players):
                if solver.Value(is_on_court[(player_idx, period_idx)]) == 1:
                    on_court.append(player_name)
                else:
                    off_court.append(player_name)

            on_court.sort()
            off_court.sort()

            second_table.add_row(
                str(period_idx + 1), ", ".join(on_court), ", ".join(off_court)
            )

        console.print("[bold cyan]── Second Half ──[/bold cyan]")
        console.print(second_table)
    else:
        print("No solution found.")


if __name__ == "__main__":
    main()
