from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Game, Player, Team

__all__ = ["GameRepository", "PlayerRepository", "TeamRepository"]


class PlayerRepository(ABC):
    @abstractmethod
    def get(self, player_id: str) -> Player | None:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Player]:
        raise NotImplementedError

    @abstractmethod
    def save(self, player: Player) -> None:
        raise NotImplementedError

    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def db_exists(self) -> bool:
        raise NotImplementedError


class TeamRepository(ABC):
    @abstractmethod
    def get(self, team_id: str) -> Team | None:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Team]:
        raise NotImplementedError

    @abstractmethod
    def save(self, team: Team) -> None:
        raise NotImplementedError

    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def db_exists(self) -> bool:
        raise NotImplementedError


class GameRepository(ABC):
    @abstractmethod
    def get(self, game_id: str) -> Game | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_team_and_date(self, team_id: str, date: str) -> Game | None:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Game]:
        raise NotImplementedError

    @abstractmethod
    def save(self, game: Game) -> None:
        raise NotImplementedError

    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def db_exists(self) -> bool:
        raise NotImplementedError
