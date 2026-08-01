from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .repositories import GameRepository, PlayerRepository, TeamRepository

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "sqlite"
DB_PATH = DATA_DIR / "bball.sqlite3"
REPOSITORY_BACKEND = "sqlite"


def ensure_db_dir() -> None:
    """Ensure the database directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class RepositoryClasses:
    player: type[PlayerRepository]
    team: type[TeamRepository]
    game: type[GameRepository]


def get_repository_classes() -> RepositoryClasses:
    """Return repository classes configured for the active backend."""
    if REPOSITORY_BACKEND == "inmemory":
        module = import_module(f"{__package__}.repositories_inmemory")
        return RepositoryClasses(
            player=module.InMemoryPlayerRepository,
            team=module.InMemoryTeamRepository,
            game=module.InMemoryGameRepository,
        )

    module = import_module(f"{__package__}.repositories_sqlite")
    return RepositoryClasses(
        player=module.SQLitePlayerRepository,
        team=module.SQLiteTeamRepository,
        game=module.SQLiteGameRepository,
    )
