from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Game, Player, Team


class PlayerRepository(ABC):
    @abstractmethod
    def get(self, player_id: str) -> Player | None:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Player]:
        raise NotImplementedError


class TeamRepository(ABC):
    @abstractmethod
    def get(self, team_id: str) -> Team | None:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Team]:
        raise NotImplementedError


class GameRepository(ABC):
    @abstractmethod
    def get(self, game_id: str) -> Game | None:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Game]:
        raise NotImplementedError


class InMemoryPlayerRepository(PlayerRepository):
    def __init__(self, players: list[Player] | None = None) -> None:
        self._players = {player.id: player for player in (players or [])}

    def get(self, player_id: str) -> Player | None:
        return self._players.get(player_id)

    def list(self) -> list[Player]:
        return list(self._players.values())


class InMemoryTeamRepository(TeamRepository):
    def __init__(self, teams: list[Team] | None = None) -> None:
        self._teams = {team.id: team for team in (teams or [])}

    def get(self, team_id: str) -> Team | None:
        return self._teams.get(team_id)

    def list(self) -> list[Team]:
        return list(self._teams.values())


class InMemoryGameRepository(GameRepository):
    def __init__(self, games: list[Game] | None = None) -> None:
        self._games = {game.id: game for game in (games or [])}

    def get(self, game_id: str) -> Game | None:
        return self._games.get(game_id)

    def list(self) -> list[Game]:
        return list(self._games.values())
