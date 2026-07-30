from .solver import LineupConfig, build_default_team, parse_arguments, solve_team_lineup

TEAM_ID = "1463e55b-341c-4d75-a8ae-a70fc3fb36cc"
TEAM_NAME = "EDJBA Vikings U13 Girls 4 Winter 2026"
PLAYERS = [
    "Indie",
    "Scarlett",
    "Mila",
    "Katrina",
    "Annabelle",
    "Hannah",
    "Sanavi",
    "Bhakti",
]

PLAY_TIME_HISTORY = {
    "Indie": [4, 12, 5, 4],
    "Sanavi": [4, None, 5, 4],
    "Bhakti": [4, None, 5, 4],
    "Katrina": [4, 12, 5, 4],
    "Scarlett": [5, 12, 4, 5],
    "Mila": [5, 12, 4, 5],
    "Annabelle": [5, 12, 4, 5],
    "Hannah": [5, None, 4, 5],
}

POWER_COMBOS = [
    ["Mila", "Katrina"],
    ["Hannah", "Sanavi"],
    ["Indie", "Scarlett"],
]

MUST_BE_ON_IN_FINAL_PERIOD = ["Mila", "Katrina"]

PERIODS_PER_HALF = [6, 6]
ON_COURT_PER_PERIOD = 5
MINUTES_PER_HALF = 20


def main() -> None:
    """Run the full optimization workflow for the selected roster and constraints."""
    args = parse_arguments()
    team = build_default_team()
    config = LineupConfig(
        team=team,
        power_combos=POWER_COMBOS,
        required_final_period_players=MUST_BE_ON_IN_FINAL_PERIOD,
        periods_per_half=PERIODS_PER_HALF,
        on_court_per_period=ON_COURT_PER_PERIOD,
        minutes_per_half=MINUTES_PER_HALF,
    )
    solve_team_lineup(
        team,
        away_player_names=args.away,
        requested_start_players=args.start,
        config=config,
    )


if __name__ == "__main__":
    main()
