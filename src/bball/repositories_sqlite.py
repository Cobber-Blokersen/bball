from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import settings
from .models import (
    NO_CONSECUTIVE_OFF_MODE_DEFAULT,
    TRANSITION_CONSTRAINTS_MODE_DEFAULT,
    Game,
    LineupConfig,
    LineupSpin,
    Player,
    Team,
    User,
    build_default_boolean_preferences,
)
from .repositories import GameRepository, PlayerRepository, TeamRepository, UserRepository


def _deserialize_config(team: Team, config_data: dict[str, Any]) -> LineupConfig:
    """Rebuild a LineupConfig from persisted data, migrating legacy boolean preferences."""
    boolean_preferences = {
        **build_default_boolean_preferences(),
        **config_data.get("boolean_preferences", {}),
    }
    no_consecutive_off_mode = config_data.get("no_consecutive_off_mode")
    if no_consecutive_off_mode is None:
        if "no_consecutive_off" in boolean_preferences:
            no_consecutive_off_mode = "enforced" if boolean_preferences["no_consecutive_off"] else "off"
        else:
            no_consecutive_off_mode = NO_CONSECUTIVE_OFF_MODE_DEFAULT
    boolean_preferences.pop("no_consecutive_off", None)

    transition_constraints_mode = config_data.get("transition_constraints_mode")
    if transition_constraints_mode is None:
        if "transition_constraints" in boolean_preferences:
            transition_constraints_mode = "enforced" if boolean_preferences["transition_constraints"] else "off"
        else:
            transition_constraints_mode = TRANSITION_CONSTRAINTS_MODE_DEFAULT
    boolean_preferences.pop("transition_constraints", None)

    return LineupConfig(
        team=team,
        power_combos=[list(combo) for combo in config_data.get("power_combos", [])],
        required_final_period_players=list(config_data.get("required_final_period_players", [])),
        never_on_first_period_players=list(config_data.get("never_on_first_period_players", [])),
        periods_per_half=list(config_data.get("periods_per_half", [6, 6])),
        on_court_per_period=config_data.get("on_court_per_period", 5),
        minutes_per_half=config_data.get("minutes_per_half", 20),
        boolean_preferences=boolean_preferences,
        no_consecutive_off_mode=no_consecutive_off_mode,
        transition_constraints_mode=transition_constraints_mode,
    )


class SQLiteUserRepository(UserRepository):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or settings.DB_PATH)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        for _ in range(20):
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.execute("PRAGMA busy_timeout = 30000")
                conn.execute("PRAGMA journal_mode = WAL")
                return conn
            except sqlite3.OperationalError:
                time.sleep(0.25)
        return sqlite3.connect(self.db_path, timeout=30.0)

    def initialize(self) -> None:
        settings.ensure_db_dir()
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT NOT NULL, name TEXT NOT NULL, "
                "role TEXT NOT NULL, auth_type TEXT NOT NULL)"
            )
            conn.commit()

    def _init_db(self) -> None:
        self.initialize()

    def get(self, user_id: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, name, role, auth_type FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row:
            return User(id=row[0], email=row[1], name=row[2], role=row[3], auth_type=row[4])
        return None

    def list(self) -> list[User]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, email, name, role, auth_type FROM users ORDER BY name").fetchall()
        return [User(id=row[0], email=row[1], name=row[2], role=row[3], auth_type=row[4]) for row in rows]

    def save(self, user: User) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO users (id, email, name, role, auth_type) VALUES (?, ?, ?, ?, ?)",
                (user.id, user.email, user.name, user.role, user.auth_type),
            )
            conn.commit()

    def delete(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM users")
            conn.commit()

    def db_exists(self) -> bool:
        return Path(self.db_path).exists()


class SQLitePlayerRepository(PlayerRepository):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or settings.DB_PATH)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        for _ in range(20):
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.execute("PRAGMA busy_timeout = 30000")
                conn.execute("PRAGMA journal_mode = WAL")
                return conn
            except sqlite3.OperationalError:
                time.sleep(0.25)
        return sqlite3.connect(self.db_path, timeout=30.0)

    def initialize(self) -> None:
        settings.ensure_db_dir()
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS players (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
            conn.commit()

    def _init_db(self) -> None:
        self.initialize()

    def get(self, player_id: str) -> Player | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id, name FROM players WHERE id = ?", (player_id,)).fetchone()
        if row:
            return Player(id=row[0], name=row[1])
        return None

    def list(self) -> list[Player]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, name FROM players ORDER BY name").fetchall()
        return [Player(id=row[0], name=row[1]) for row in rows]

    def save(self, player: Player) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO players (id, name) VALUES (?, ?)", (player.id, player.name))
            conn.commit()

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM players")
            conn.commit()

    def db_exists(self) -> bool:
        return Path(self.db_path).exists()


class SQLiteTeamRepository(TeamRepository):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or settings.DB_PATH)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        for _ in range(20):
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.execute("PRAGMA busy_timeout = 30000")
                conn.execute("PRAGMA journal_mode = WAL")
                return conn
            except sqlite3.OperationalError:
                time.sleep(0.25)
        return sqlite3.connect(self.db_path, timeout=30.0)

    def initialize(self) -> None:
        settings.ensure_db_dir()
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS teams (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, "
                "players_json TEXT NOT NULL, config_json TEXT)"
            )
            # Add user_id column to existing tables for backward compatibility
            cursor = conn.execute("PRAGMA table_info(teams)")
            columns = {row[1] for row in cursor.fetchall()}
            if "user_id" not in columns:
                conn.execute("ALTER TABLE teams ADD COLUMN user_id TEXT DEFAULT ''")
            conn.commit()

    def _init_db(self) -> None:
        self.initialize()

    def get(self, user_id: str, team_id: str) -> Team | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, name, players_json, config_json FROM teams WHERE id = ? AND user_id = ?",
                (team_id, user_id),
            ).fetchone()
        if not row:
            return None
        team_id, returned_user_id, name, players_json, config_json = row
        players_data = json.loads(players_json)
        players = [Player(id=item["id"], name=item["name"]) for item in players_data]
        team = Team(id=team_id, user_id=returned_user_id, name=name, players=players)
        team.lineup_config = _deserialize_config(team, json.loads(config_json)) if config_json else None
        return team

    def list(self, user_id: str) -> list[Team]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, name, players_json, config_json FROM teams WHERE user_id = ? ORDER BY name",
                (user_id,),
            ).fetchall()
        teams: list[Team] = []
        for team_id, returned_user_id, name, players_json, config_json in rows:
            players_data = json.loads(players_json)
            players = [Player(id=item["id"], name=item["name"]) for item in players_data]
            team = Team(id=team_id, user_id=returned_user_id, name=name, players=players)
            team.lineup_config = _deserialize_config(team, json.loads(config_json)) if config_json else None
            teams.append(team)
        return teams

    def save(self, team: Team) -> None:
        with self._connect() as conn:
            config = team.lineup_config
            config_payload = None
            if config is not None:
                config_payload = json.dumps(
                    {
                        "power_combos": config.power_combos,
                        "required_final_period_players": config.required_final_period_players,
                        "never_on_first_period_players": config.never_on_first_period_players,
                        "periods_per_half": config.periods_per_half,
                        "on_court_per_period": config.on_court_per_period,
                        "minutes_per_half": config.minutes_per_half,
                        "boolean_preferences": config.boolean_preferences,
                        "no_consecutive_off_mode": config.no_consecutive_off_mode,
                        "transition_constraints_mode": config.transition_constraints_mode,
                    }
                )
            conn.execute(
                "INSERT OR REPLACE INTO teams (id, user_id, name, players_json, config_json) VALUES (?, ?, ?, ?, ?)",
                (
                    team.id,
                    team.user_id,
                    team.name,
                    json.dumps([{"id": player.id, "name": player.name} for player in team.players]),
                    config_payload,
                ),
            )
            conn.commit()

    def delete(self, team_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
            conn.commit()

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM teams")
            conn.commit()

    def db_exists(self) -> bool:
        return Path(self.db_path).exists()


class SQLiteGameRepository(GameRepository):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or settings.DB_PATH)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        for _ in range(20):
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.execute("PRAGMA busy_timeout = 30000")
                conn.execute("PRAGMA journal_mode = WAL")
                return conn
            except sqlite3.OperationalError:
                time.sleep(0.25)
        return sqlite3.connect(self.db_path, timeout=30.0)

    def initialize(self) -> None:
        settings.ensure_db_dir()
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, team_id TEXT NOT NULL, date TEXT NOT NULL, "
                "lineup_spins_json TEXT NOT NULL, selected_lineup_id TEXT)"
            )
            # Add user_id column to existing tables for backward compatibility
            cursor = conn.execute("PRAGMA table_info(games)")
            columns = {row[1] for row in cursor.fetchall()}
            if "user_id" not in columns:
                conn.execute("ALTER TABLE games ADD COLUMN user_id TEXT DEFAULT ''")
            conn.commit()

    def _init_db(self) -> None:
        self.initialize()

    def get(self, user_id: str, game_id: str) -> Game | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, team_id, date, lineup_spins_json, selected_lineup_id FROM games WHERE id = ? AND user_id = ?",
                (game_id, user_id),
            ).fetchone()
        if not row:
            return None
        game_id, returned_user_id, team_id, date, lineup_spins_json, selected_lineup_id = row
        spins_data = json.loads(lineup_spins_json)
        spins = [
            LineupSpin(
                id=item["id"],
                number=item.get("number", 1),
                players=[Player(id=player["id"], name=player["name"]) for player in item.get("players", [])],
                created_at=item.get("created_at"),
                solution_snapshot=item.get("solution_snapshot"),
                config_snapshot=item.get("config_snapshot"),
                away_players=item.get("away_players", []),
            )
            for item in spins_data
        ]
        return Game(
            id=game_id,
            user_id=returned_user_id,
            team_id=team_id,
            date=date,
            lineup_spins=spins,
            selected_lineup_id=selected_lineup_id,
        )

    def get_by_team_and_date(self, user_id: str, team_id: str, date: str) -> Game | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, team_id, date, lineup_spins_json, selected_lineup_id "
                "FROM games WHERE user_id = ? AND team_id = ? AND date = ?",
                (user_id, team_id, date),
            ).fetchone()
        if not row:
            return None
        game_id, returned_user_id, team_id, date, lineup_spins_json, selected_lineup_id = row
        spins_data = json.loads(lineup_spins_json)
        spins = [
            LineupSpin(
                id=item["id"],
                number=item.get("number", 1),
                players=[Player(id=player["id"], name=player["name"]) for player in item.get("players", [])],
                created_at=item.get("created_at"),
                solution_snapshot=item.get("solution_snapshot"),
                config_snapshot=item.get("config_snapshot"),
                away_players=item.get("away_players", []),
            )
            for item in spins_data
        ]
        return Game(
            id=game_id,
            user_id=returned_user_id,
            team_id=team_id,
            date=date,
            lineup_spins=spins,
            selected_lineup_id=selected_lineup_id,
        )

    def list(self, user_id: str) -> list[Game]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, team_id, date, lineup_spins_json, selected_lineup_id FROM games WHERE user_id = ? ORDER BY date",
                (user_id,),
            ).fetchall()
        games: list[Game] = []
        for game_id, returned_user_id, team_id, date, lineup_spins_json, selected_lineup_id in rows:
            spins_data = json.loads(lineup_spins_json)
            spins = [
                LineupSpin(
                    id=item["id"],
                    number=item.get("number", 1),
                    players=[Player(id=player["id"], name=player["name"]) for player in item.get("players", [])],
                    created_at=item.get("created_at"),
                    solution_snapshot=item.get("solution_snapshot"),
                    config_snapshot=item.get("config_snapshot"),
                    away_players=item.get("away_players", []),
                )
                for item in spins_data
            ]
            games.append(
                Game(
                    id=game_id,
                    user_id=returned_user_id,
                    team_id=team_id,
                    date=date,
                    lineup_spins=spins,
                    selected_lineup_id=selected_lineup_id,
                )
            )
        return games

    def save(self, game: Game) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO games (id, user_id, team_id, date, lineup_spins_json, selected_lineup_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    game.id,
                    game.user_id,
                    game.team_id,
                    game.date,
                    json.dumps(
                        [
                            {
                                "id": spin.id,
                                "number": spin.number,
                                "players": [{"id": player.id, "name": player.name} for player in spin.players],
                                "created_at": spin.created_at or datetime.now(UTC).isoformat(),
                                "solution_snapshot": spin.solution_snapshot,
                                "config_snapshot": spin.config_snapshot,
                                "away_players": spin.away_players,
                            }
                            for spin in game.lineup_spins
                        ]
                    ),
                    game.selected_lineup_id,
                ),
            )
            conn.commit()

    def delete(self, game_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
            conn.commit()

    def delete_by_team(self, team_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM games WHERE team_id = ?", (team_id,))
            conn.commit()

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM games")
            conn.commit()

    def db_exists(self) -> bool:
        return Path(self.db_path).exists()
