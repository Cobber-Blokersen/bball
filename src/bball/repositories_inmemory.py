from __future__ import annotations

from .models import Game, Player, Team
from .repositories import GameRepository, PlayerRepository, TeamRepository


class InMemoryPlayerRepository(PlayerRepository):
    def __init__(self, players: list[Player] | None = None) -> None:
        self._players = {player.id: player for player in (players or [])}

    def get(self, player_id: str) -> Player | None:
        return self._players.get(player_id)

    def list(self) -> list[Player]:
        return list(self._players.values())

    def save(self, player: Player) -> None:
        self._players[player.id] = player

    def initialize(self) -> None:
        return None

    def reset(self) -> None:
        self._players.clear()

    def db_exists(self) -> bool:
        return True


class InMemoryTeamRepository(TeamRepository):
    def __init__(self, teams: list[Team] | None = None) -> None:
        self._teams = {team.id: team for team in (teams or [])}

    def get(self, user_id: str, team_id: str) -> Team | None:
        team = self._teams.get(team_id)
        if team and team.user_id == user_id:
            return team
        return None

    def list(self, user_id: str) -> list[Team]:
        return [team for team in self._teams.values() if team.user_id == user_id]

    def save(self, team: Team) -> None:
        self._teams[team.id] = team

    def delete(self, team_id: str) -> None:
        self._teams.pop(team_id, None)

    def initialize(self) -> None:
        return None

    def reset(self) -> None:
        self._teams.clear()

    def db_exists(self) -> bool:
        return True


class InMemoryGameRepository(GameRepository):
    def __init__(self, games: list[Game] | None = None) -> None:
        self._games = {game.id: game for game in (games or [])}

    def get(self, user_id: str, game_id: str) -> Game | None:
        game = self._games.get(game_id)
        if game and game.user_id == user_id:
            return game
        return None

    def get_by_team_and_date(self, user_id: str, team_id: str, date: str) -> Game | None:
        return next(
            (game for game in self._games.values() if game.user_id == user_id and game.team_id == team_id and game.date == date),
            None,
        )

    def list(self, user_id: str) -> list[Game]:
        return [game for game in self._games.values() if game.user_id == user_id]

    def save(self, game: Game) -> None:
        self._games[game.id] = game

    def delete(self, game_id: str) -> None:
        self._games.pop(game_id, None)

    def delete_by_team(self, team_id: str) -> None:
        self._games = {game_id: game for game_id, game in self._games.items() if game.team_id != team_id}

    def initialize(self) -> None:
        return None

    def reset(self) -> None:
        self._games.clear()

    def db_exists(self) -> bool:
        return True
