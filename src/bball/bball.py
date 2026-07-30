from .models import LineupConfig
from .solver import build_default_team, parse_arguments, solve_team_lineup


def main() -> None:
    """Run the full optimization workflow for the selected roster and constraints."""
    args = parse_arguments()
    team = build_default_team()
    config = team.lineup_config or LineupConfig(team=team)
    solve_team_lineup(
        team,
        away_player_names=args.away,
        requested_start_players=args.start,
        config=config,
    )


if __name__ == "__main__":
    main()
