from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime

from .models import Game, LineupConfig, LineupSpin, Player, Team
from .settings import DB_PATH, ensure_db_dir


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


class GameRepository(ABC):
    @abstractmethod
    def get(self, game_id: str) -> Game | None:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Game]:
        raise NotImplementedError

    @abstractmethod
    def save(self, game: Game) -> None:
        raise NotImplementedError


class InMemoryPlayerRepository(PlayerRepository):
    def __init__(self, players: list[Player] | None = None) -> None:
        self._players = {player.id: player for player in (players or [])}

    def get(self, player_id: str) -> Player | None:
        return self._players.get(player_id)

    def list(self) -> list[Player]:
        return list(self._players.values())

    def save(self, player: Player) -> None:
        self._players[player.id] = player


class InMemoryTeamRepository(TeamRepository):
    def __init__(self, teams: list[Team] | None = None) -> None:
        self._teams = {team.id: team for team in (teams or [])}

    def get(self, team_id: str) -> Team | None:
        return self._teams.get(team_id)

    def list(self) -> list[Team]:
        return list(self._teams.values())

    def save(self, team: Team) -> None:
        self._teams[team.id] = team


class InMemoryGameRepository(GameRepository):
    def __init__(self, games: list[Game] | None = None) -> None:
        self._games = {game.id: game for game in (games or [])}

    def get(self, game_id: str) -> Game | None:
        return self._games.get(game_id)

    def list(self) -> list[Game]:
        return list(self._games.values())

    def save(self, game: Game) -> None:
        self._games[game.id] = game


class SQLitePlayerRepository(PlayerRepository):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        ensure_db_dir()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS players (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
            conn.commit()

    def get(self, player_id: str) -> Player | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT id, name FROM players WHERE id = ?", (player_id,)).fetchone()
        if row:
            return Player(id=row[0], name=row[1])
        return None

    def list(self) -> list[Player]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT id, name FROM players ORDER BY name").fetchall()
        return [Player(id=row[0], name=row[1]) for row in rows]

    def save(self, player: Player) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO players (id, name) VALUES (?, ?)", (player.id, player.name))
            conn.commit()


class SQLiteTeamRepository(TeamRepository):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        ensure_db_dir()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS teams (id TEXT PRIMARY KEY, name TEXT NOT NULL, players_json TEXT NOT NULL, config_json TEXT)"
            )
            conn.commit()

    def get(self, team_id: str) -> Team | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, name, players_json, config_json FROM teams WHERE id = ?",
                (team_id,),
            ).fetchone()
        if not row:
            return None
        _, name, players_json, config_json = row
        players_data = json.loads(players_json)
        players = [Player(id=item["id"], name=item["name"]) for item in players_data]
        team = Team(id=team_id, name=name, players=players)
        if config_json:
            config_data = json.loads(config_json)
            team.lineup_config = LineupConfig(
                team=team,
                power_combos=[list(combo) for combo in config_data.get("power_combos", [])],
                required_final_period_players=list(config_data.get("required_final_period_players", [])),
                periods_per_half=list(config_data.get("periods_per_half", [6, 6])),
                on_court_per_period=config_data.get("on_court_per_period", 5),
                minutes_per_half=config_data.get("minutes_per_half", 20),
            )
        else:
            team.lineup_config = None
        return team

    def list(self) -> list[Team]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT id, name, players_json, config_json FROM teams ORDER BY name").fetchall()
        teams: list[Team] = []
        for team_id, name, players_json, config_json in rows:
            players_data = json.loads(players_json)
            players = [Player(id=item["id"], name=item["name"]) for item in players_data]
            team = Team(id=team_id, name=name, players=players)
            if config_json:
                config_data = json.loads(config_json)
                team.lineup_config = LineupConfig(
                    team=team,
                    power_combos=[list(combo) for combo in config_data.get("power_combos", [])],
                    required_final_period_players=list(config_data.get("required_final_period_players", [])),
                    periods_per_half=list(config_data.get("periods_per_half", [6, 6])),
                    on_court_per_period=config_data.get("on_court_per_period", 5),
                    minutes_per_half=config_data.get("minutes_per_half", 20),
                )
            else:
                team.lineup_config = None
            teams.append(team)
        return teams

    def save(self, team: Team) -> None:
        with sqlite3.connect(self.db_path) as conn:
            config = team.lineup_config
            config_payload = None
            if config is not None:
                config_payload = json.dumps(
                    {
                        "power_combos": config.power_combos,
                        "required_final_period_players": config.required_final_period_players,
                        "periods_per_half": config.periods_per_half,
                        "on_court_per_period": config.on_court_per_period,
                        "minutes_per_half": config.minutes_per_half,
                    }
                )
            conn.execute(
                "INSERT OR REPLACE INTO teams (id, name, players_json, config_json) VALUES (?, ?, ?, ?)",
                (
                    team.id,
                    team.name,
                    json.dumps([{"id": player.id, "name": player.name} for player in team.players]),
                    config_payload,
                ),
            )
            conn.commit()


class SQLiteGameRepository(GameRepository):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        ensure_db_dir()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, team_id TEXT NOT NULL, date TEXT NOT NULL, lineup_spins_json TEXT NOT NULL, selected_lineup_id TEXT)"
            )
            conn.commit()

    def get(self, game_id: str) -> Game | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, team_id, date, lineup_spins_json, selected_lineup_id FROM games WHERE id = ?",
                (game_id,),
            ).fetchone()
        if not row:
            return None
        game_id, team_id, date, lineup_spins_json, selected_lineup_id = row
        spins_data = json.loads(lineup_spins_json)
        spins = [
            LineupSpin(
                id=item["id"],
                number=item.get("number", 1),
                players=[Player(id=player["id"], name=player["name"]) for player in item.get("players", [])],
                created_at=item.get("created_at"),
                display_data=item.get("display_data"),
                config_snapshot=item.get("config_snapshot"),
                away_players=item.get("away_players", []),
            )
            for item in spins_data
        ]
        return Game(id=game_id, team_id=team_id, date=date, lineup_spins=spins, selected_lineup_id=selected_lineup_id)

    def get_by_team_and_date(self, team_id: str, date: str) -> Game | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, team_id, date, lineup_spins_json, selected_lineup_id FROM games WHERE team_id = ? AND date = ?",
                (team_id, date),
            ).fetchone()
        if not row:
            return None
        game_id, team_id, date, lineup_spins_json, selected_lineup_id = row
        spins_data = json.loads(lineup_spins_json)
        spins = [
            LineupSpin(
                id=item["id"],
                number=item.get("number", 1),
                players=[Player(id=player["id"], name=player["name"]) for player in item.get("players", [])],
                created_at=item.get("created_at"),
                display_data=item.get("display_data"),
                config_snapshot=item.get("config_snapshot"),
                away_players=item.get("away_players", []),
            )
            for item in spins_data
        ]
        return Game(id=game_id, team_id=team_id, date=date, lineup_spins=spins, selected_lineup_id=selected_lineup_id)

    def list(self) -> list[Game]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT id, team_id, date, lineup_spins_json, selected_lineup_id FROM games ORDER BY date").fetchall()
        games: list[Game] = []
        for game_id, team_id, date, lineup_spins_json, selected_lineup_id in rows:
            spins_data = json.loads(lineup_spins_json)
            spins = [
                LineupSpin(
                    id=item["id"],
                    number=item.get("number", 1),
                    players=[Player(id=player["id"], name=player["name"]) for player in item.get("players", [])],
                    created_at=item.get("created_at"),
                    display_data=item.get("display_data"),
                    config_snapshot=item.get("config_snapshot"),
                    away_players=item.get("away_players", []),
                )
                for item in spins_data
            ]
            games.append(Game(id=game_id, team_id=team_id, date=date, lineup_spins=spins, selected_lineup_id=selected_lineup_id))
        return games

    def save(self, game: Game) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO games (id, team_id, date, lineup_spins_json, selected_lineup_id) VALUES (?, ?, ?, ?, ?)",
                (
                    game.id,
                    game.team_id,
                    game.date,
                    json.dumps(
                        [
                            {
                                "id": spin.id,
                                "number": spin.number,
                                "players": [{"id": player.id, "name": player.name} for player in spin.players],
                                "created_at": spin.created_at or datetime.utcnow().isoformat(),
                                "display_data": spin.display_data,
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
