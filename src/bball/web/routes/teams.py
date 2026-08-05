"""User routes for managing teams and games."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ... import settings
from ...models import Player, Team
from ...repositories import GameRepository, TeamRepository
from ..auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/teams", tags=["teams"])


class PlayerResponse(BaseModel):
    """Response for a player."""

    id: str
    name: str


class TeamResponse(BaseModel):
    """Response for a team."""

    id: str
    name: str
    players: list[PlayerResponse]


class TeamCreateRequest(BaseModel):
    """Request to create a team."""

    name: str
    player_names: list[str]


class GameResponse(BaseModel):
    """Response for a game."""

    id: str
    team_id: str
    date: str


def get_repositories() -> tuple[TeamRepository, GameRepository]:
    """Get repository instances."""
    repo_classes = settings.get_repository_classes()
    return repo_classes.team(), repo_classes.game()


@router.get("", response_model=list[TeamResponse])
async def list_teams(current_user: CurrentUser = Depends(get_current_user)) -> list[TeamResponse]:
    """List all teams for the current user."""
    team_repo, _ = get_repositories()
    teams = team_repo.list(current_user.id)
    return [
        TeamResponse(
            id=t.id,
            name=t.name,
            players=[PlayerResponse(id=p.id, name=p.name) for p in t.players],
        )
        for t in teams
    ]


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    request: TeamCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> TeamResponse:
    """Create a new team."""
    team_repo, _ = get_repositories()
    players = [Player(name=name) for name in request.player_names]
    team = Team(user_id=current_user.id, name=request.name, players=players)
    team_repo.save(team)
    return TeamResponse(
        id=team.id,
        name=team.name,
        players=[PlayerResponse(id=p.id, name=p.name) for p in team.players],
    )


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> TeamResponse:
    """Get a specific team."""
    team_repo, _ = get_repositories()
    team = team_repo.get(current_user.id, team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return TeamResponse(
        id=team.id,
        name=team.name,
        players=[PlayerResponse(id=p.id, name=p.name) for p in team.players],
    )


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a team."""
    team_repo, game_repo = get_repositories()
    team = team_repo.get(current_user.id, team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    game_repo.delete_by_team(team_id)
    team_repo.delete(team_id)


@router.post("/{team_id}/players", status_code=status.HTTP_201_CREATED)
async def add_player(
    team_id: str,
    player_name: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> TeamResponse:
    """Add a player to a team."""
    team_repo, _ = get_repositories()
    team = team_repo.get(current_user.id, team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    if team.get_player_by_name(player_name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Player already exists")

    team.add_player(Player(name=player_name))
    team_repo.save(team)
    return TeamResponse(
        id=team.id,
        name=team.name,
        players=[PlayerResponse(id=p.id, name=p.name) for p in team.players],
    )


@router.delete("/{team_id}/players/{player_name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_player(
    team_id: str,
    player_name: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Remove a player from a team."""
    team_repo, _ = get_repositories()
    team = team_repo.get(current_user.id, team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    team.players = [p for p in team.players if p.name != player_name]
    team_repo.save(team)


@router.get("/{team_id}/games", response_model=list[GameResponse])
async def list_games(
    team_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[GameResponse]:
    """List games for a team."""
    team_repo, game_repo = get_repositories()
    team = team_repo.get(current_user.id, team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    games = [g for g in game_repo.list(current_user.id) if g.team_id == team_id]
    return [GameResponse(id=g.id, team_id=g.team_id, date=g.date) for g in games]
