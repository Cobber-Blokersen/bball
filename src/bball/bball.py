from ortools.sat.python import cp_model


def main():
    # --- Basic setup ---
    players = ["Indie", "Scarlett", "Mila", "Katrina",
               "Annabelle", "Hannah", "Sanavi", "Bhakti"]
    num_players = len(players)

    periods_per_half = 4  # or 5 – you can make this a parameter
    num_halves = 2
    num_periods = periods_per_half * num_halves

    on_court_per_period = 5

    # --- Model ---
    model = cp_model.CpModel()

    # x[p][t] = 1 if player p is ON court in period t, else 0
    x = {}
    for p in range(num_players):
        for t in range(num_periods):
            x[(p, t)] = model.NewBoolVar(f"x_p{p}_t{t}")

    # --- Constraint: exactly 5 players on court each period ---
    for t in range(num_periods):
        model.Add(sum(x[(p, t)] for p in range(num_players)) == on_court_per_period)

    # --- Constraint: near-equal total playing time (difference ≤ 1 period) ---
    total_periods_played = []
    for p in range(num_players):
        total = model.NewIntVar(0, num_periods, f"total_p{p}")
        model.Add(total == sum(x[(p, t)] for t in range(num_periods)))
        total_periods_played.append(total)

    for p1 in range(num_players):
        for p2 in range(num_players):
            if p1 < p2:
                diff = model.NewIntVar(-num_periods, num_periods, f"diff_{p1}_{p2}")
                model.Add(diff == total_periods_played[p1] - total_periods_played[p2])
                model.Add(diff <= 1)
                model.Add(diff >= -1)

    # --- Constraint: no player off court for consecutive periods ---
    # Off court means x[p, t] == 0, so we enforce: not (off at t and off at t+1)
    for p in range(num_players):
        for t in range(num_periods - 1):
            # x[p,t] + x[p,t+1] >= 1  (at least one of the two is ON)
            model.Add(x[(p, t)] + x[(p, t + 1)] >= 1)

    # --- Starting lineup: Period 0 (first period) ---
    # Start on: Indie(0), Scarlett(1), Mila(2), Annabelle(4), Sanavi(6)
    start_on = ["Indie", "Scarlett", "Mila", "Annabelle", "Sanavi"]
    for p, name in enumerate(players):
        if name in start_on:
            model.Add(x[(p, 0)] == 1)
        else:
            model.Add(x[(p, 0)] == 0)

    # --- Mila must be on court in final period ---
    mila_index = players.index("Mila")
    model.Add(x[(mila_index, num_periods - 1)] == 1)

    # --- Players who start OFF in Period 0 must not also start OFF in first period of second half ---
    # First period of second half = period periods_per_half
    second_half_start = periods_per_half
    for p in range(num_players):
        # If off at t=0, then must be on at second_half_start
        # x[p,0] == 0 => x[p, second_half_start] == 1
        # Use implication: (x[p,0] == 0) => (x[p, second_half_start] == 1)
        # In CP-SAT: (x[p,0] == 1) OR (x[p, second_half_start] == 1)
        model.AddBoolOr([x[(p, 0)], x[(p, second_half_start)]])

    # --- Players who start OFF at start must not also be OFF at end ---
    for p in range(num_players):
        # x[p,0] == 0 => x[p, last] == 1
        model.AddBoolOr([x[(p, 0)], x[(p, num_periods - 1)]])

    # --- Objective: maximise periods where Mila and Katrina are on together ---
    kat_index = players.index("Katrina")
    together_vars = []
    for t in range(num_periods):
        both_on = model.NewBoolVar(f"mila_kat_t{t}")
        # both_on == 1 iff Mila and Katrina both on
        model.Add(x[(mila_index, t)] + x[(kat_index, t)] == 2).OnlyEnforceIf(both_on)
        model.Add(x[(mila_index, t)] + x[(kat_index, t)] != 2).OnlyEnforceIf(both_on.Not())
        together_vars.append(both_on)

    model.Maximize(sum(together_vars))

    # --- Solve ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0  # tweak if needed
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f"Status: {solver.StatusName(status)}")
        print()

        # Build table: Period | On Court | Off Court
        for t in range(num_periods):
            on_court = []
            off_court = []
            for p, name in enumerate(players):
                if solver.Value(x[(p, t)]) == 1:
                    on_court.append(name)
                else:
                    off_court.append(name)

            on_court.sort()
            off_court.sort()

            print(f"Period {t + 1}:")
            print(f"  On Court : {', '.join(on_court)}")
            print(f"  Off Court: {', '.join(off_court)}")
            print()
    else:
        print("No solution found.")


if __name__ == "__main__":
    main()
