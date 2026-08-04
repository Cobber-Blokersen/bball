"""HTML page routes — POST/Redirect/Get pattern throughout."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import settings
from ...models import BOOLEAN_PREFERENCE_DEFINITIONS, LineupConfig, Player, Team
from ...solver import solve_team_lineup
from ..auth import CurrentUser, get_current_user
from ..lineup_display import build_spin_display
from ..templating import jinja_env

router = APIRouter(tags=["pages"], include_in_schema=False)


def _repos():
    rc = settings.get_repository_classes()
    return rc.team(), rc.game()


def _render(template_name: str, **ctx: object) -> str:
    return jinja_env.get_template(template_name).render(**ctx)


def _ctx(current_user: CurrentUser, **extra: object) -> dict:
    return {"is_admin": current_user.is_admin, "user_name": current_user.name, **extra}


def _load_team(user_id: str, team_id: str) -> Team:
    team_repo, _ = _repos()
    team = team_repo.get(user_id, team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


# ---------------------------------------------------------------------------
# Teams list
# ---------------------------------------------------------------------------

@router.get("/teams", response_class=HTMLResponse)
async def teams_list(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    team_repo, _ = _repos()
    teams = team_repo.list(current_user.id)
    return _render("teams/list.html", teams=teams, **_ctx(current_user))


@router.post("/teams/new")
async def create_team(
    request: Request,
    name: str = Form(...),
    player_names: str = Form(""),
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    """Create team from HTML form; player_names is a comma-separated string."""
    team_repo, _ = _repos()
    players = [
        Player(name=n.strip())
        for n in player_names.split(",")
        if n.strip()
    ]
    team = Team(user_id=current_user.id, name=name.strip(), players=players)
    team_repo.save(team)
    return RedirectResponse(url=f"/teams/{team.id}", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Team detail
# ---------------------------------------------------------------------------

@router.get("/teams/{team_id}", response_class=HTMLResponse)
async def team_detail(
    team_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    team = _load_team(current_user.id, team_id)
    _, game_repo = _repos()
    games = sorted(
        [g for g in game_repo.list(current_user.id) if g.team_id == team_id],
        key=lambda g: g.date,
        reverse=True,
    )
    return _render("teams/detail.html", team=team, games=games, **_ctx(current_user))


@router.post("/teams/{team_id}/players/add")
async def add_player(
    team_id: str,
    player_name: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    name = player_name.strip()
    if name and not team.get_player_by_name(name):
        team.add_player(Player(name=name))
        team_repo.save(team)
    return RedirectResponse(url=f"/teams/{team_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/teams/{team_id}/players/{player_name}/remove")
async def remove_player(
    team_id: str,
    player_name: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    team.players = [p for p in team.players if p.name != player_name]
    team_repo.save(team)
    return RedirectResponse(url=f"/teams/{team_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/teams/{team_id}/delete")
async def delete_team(
    team_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, game_repo = _repos()
    team = team_repo.get(current_user.id, team_id)
    if team:
        game_repo.delete_by_team(team_id)
        team_repo.delete(team_id)
    return RedirectResponse(url="/teams", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------

@router.get("/games", response_class=HTMLResponse)
async def games_index(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    from datetime import date
    team_repo, game_repo = _repos()
    teams = team_repo.list(current_user.id)
    all_games = game_repo.list(current_user.id)
    games_by_team = {
        team.id: sorted(
            [g for g in all_games if g.team_id == team.id],
            key=lambda g: g.date,
            reverse=True,
        )
        for team in teams
    }
    return _render(
        "games/index.html",
        teams=teams,
        games_by_team=games_by_team,
        today=date.today().isoformat(),
        **_ctx(current_user),
    )


@router.post("/teams/{team_id}/games/new")
async def new_game(
    team_id: str,
    date: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    _load_team(current_user.id, team_id)  # ownership check
    return RedirectResponse(
        url=f"/teams/{team_id}/games/{date.strip()}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/teams/{team_id}/games/{date}/delete")
async def delete_game(
    team_id: str,
    date: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    _, game_repo = _repos()
    game = game_repo.get_by_team_and_date(current_user.id, team_id, date)
    if game:
        game_repo.delete(game.id)
    return RedirectResponse(url="/games", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/teams/{team_id}/games/{date}", response_class=HTMLResponse)
async def game_detail(
    team_id: str,
    date: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    team = _load_team(current_user.id, team_id)
    _, game_repo = _repos()
    game = game_repo.get_by_team_and_date(current_user.id, team_id, date)
    spins = game.lineup_spins if game else []
    last_start_names = [p.name for p in spins[-1].players] if spins else []
    last_away_names = spins[-1].away_players if spins else []
    on_court = team.lineup_config.on_court_per_period if team.lineup_config else 5
    return _render(
        "games/detail.html",
        team=team,
        date=date,
        spins=spins,
        on_court_per_period=on_court,
        last_start_names=last_start_names,
        last_away_names=last_away_names,
        request_query_no_solution=request.query_params.get("no_solution"),
        **_ctx(current_user),
    )


@router.post("/teams/{team_id}/games/{date}/spin")
def run_spin(
    team_id: str,
    date: str,
    away_players: str = Form(""),
    start_players: str = Form(""),
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    """Synchronous so CP-SAT doesn't block the event loop."""
    team = _load_team(current_user.id, team_id)
    _, game_repo = _repos()
    away_list = [n.strip() for n in away_players.split(",") if n.strip()]
    start_list = [n.strip() for n in start_players.split(",") if n.strip()]
    game = solve_team_lineup(
        team,
        away_player_names=away_list,
        requested_start_players=start_list,
        game_repo=game_repo,
        game_date=date,
        user_id=current_user.id,
    )
    if game is None or not game.lineup_spins:
        return RedirectResponse(
            url=f"/teams/{team_id}/games/{date}?no_solution=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    spin_number = game.lineup_spins[-1].number
    return RedirectResponse(
        url=f"/teams/{team_id}/games/{date}/spins/{spin_number}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/teams/{team_id}/games/{date}/spins/{spin_number}/delete")
async def delete_spin(
    team_id: str,
    date: str,
    spin_number: int,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    _, game_repo = _repos()
    game = game_repo.get_by_team_and_date(current_user.id, team_id, date)
    if game:
        game.lineup_spins = [s for s in game.lineup_spins if s.number != spin_number]
        game.renumber_spins()
        if game.selected_lineup_id and not any(s.id == game.selected_lineup_id for s in game.lineup_spins):
            game.selected_lineup_id = None
        game_repo.save(game)
    return RedirectResponse(url=f"/teams/{team_id}/games/{date}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/teams/{team_id}/games/{date}/spins/delete-all")
async def delete_all_spins(
    team_id: str,
    date: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    _, game_repo = _repos()
    game = game_repo.get_by_team_and_date(current_user.id, team_id, date)
    if game:
        game.lineup_spins = []
        game.selected_lineup_id = None
        game_repo.save(game)
    return RedirectResponse(url=f"/teams/{team_id}/games/{date}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/teams/{team_id}/games/{date}/spins/{spin_number}", response_class=HTMLResponse)
async def spin_view(
    team_id: str,
    date: str,
    spin_number: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    team = _load_team(current_user.id, team_id)
    _, game_repo = _repos()
    game = game_repo.get_by_team_and_date(current_user.id, team_id, date)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    spin = next((s for s in game.lineup_spins if s.number == spin_number), None)
    if not spin:
        raise HTTPException(status_code=404, detail="Spin not found")
    display = build_spin_display(spin)
    return _render(
        "games/spin.html",
        team=team,
        date=date,
        spin=spin,
        spin_number=spin_number,
        total_spins=len(game.lineup_spins),
        display=display,
        **_ctx(current_user),
    )


# ---------------------------------------------------------------------------
# Team preferences
# ---------------------------------------------------------------------------

def _pref_redirect(team_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/teams/{team_id}/preferences", status_code=status.HTTP_303_SEE_OTHER)


def _get_config(team: Team) -> LineupConfig:
    if team.lineup_config is None:
        team.lineup_config = LineupConfig(team=team)
    return team.lineup_config


@router.get("/teams/{team_id}/preferences", response_class=HTMLResponse)
async def team_preferences(
    team_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    team = _load_team(current_user.id, team_id)
    config = _get_config(team)
    return _render(
        "teams/preferences.html",
        team=team,
        config=config,
        pref_defs=BOOLEAN_PREFERENCE_DEFINITIONS,
        **_ctx(current_user),
    )


@router.post("/teams/{team_id}/preferences/setup")
async def save_setup(
    team_id: str,
    on_court_per_period: int = Form(5),
    periods_first: int = Form(6),
    periods_second: int = Form(6),
    minutes_per_half: int = Form(20),
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    config = _get_config(team)
    config.on_court_per_period = max(1, on_court_per_period)
    config.periods_per_half = [max(1, periods_first), max(1, periods_second)]
    config.minutes_per_half = max(1, minutes_per_half)
    team.lineup_config = config
    team_repo.save(team)
    return _pref_redirect(team_id)


@router.post("/teams/{team_id}/preferences/boolean")
async def save_boolean_prefs(
    team_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    config = _get_config(team)
    form = await request.form()
    known_keys = {d.key for d in BOOLEAN_PREFERENCE_DEFINITIONS}
    config.boolean_preferences = {key: key in form for key in known_keys}
    team.lineup_config = config
    team_repo.save(team)
    return _pref_redirect(team_id)


@router.post("/teams/{team_id}/preferences/power-combos/add")
async def add_power_combo(
    team_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    config = _get_config(team)
    form = await request.form()
    selected = [v for v in form.getlist("combo_players") if v.strip()]
    if len(selected) >= 2:
        config.power_combos.append(selected)
        team.lineup_config = config
        team_repo.save(team)
    return _pref_redirect(team_id)


@router.post("/teams/{team_id}/preferences/power-combos/{combo_index}/remove")
async def remove_power_combo(
    team_id: str,
    combo_index: int,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    config = _get_config(team)
    if 0 <= combo_index < len(config.power_combos):
        del config.power_combos[combo_index]
        team.lineup_config = config
        team_repo.save(team)
    return _pref_redirect(team_id)


@router.post("/teams/{team_id}/preferences/must-finish/add")
async def add_must_finish(
    team_id: str,
    player_name: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    config = _get_config(team)
    name = player_name.strip()
    if name and name not in config.required_final_period_players:
        config.required_final_period_players.append(name)
        team.lineup_config = config
        team_repo.save(team)
    return _pref_redirect(team_id)


@router.post("/teams/{team_id}/preferences/must-finish/{player_name}/remove")
async def remove_must_finish(
    team_id: str,
    player_name: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    config = _get_config(team)
    config.required_final_period_players = [p for p in config.required_final_period_players if p != player_name]
    team.lineup_config = config
    team_repo.save(team)
    return _pref_redirect(team_id)


@router.post("/teams/{team_id}/preferences/never-start/add")
async def add_never_start(
    team_id: str,
    player_name: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    config = _get_config(team)
    name = player_name.strip()
    if name and name not in config.never_on_first_period_players:
        config.never_on_first_period_players.append(name)
        team.lineup_config = config
        team_repo.save(team)
    return _pref_redirect(team_id)


@router.post("/teams/{team_id}/preferences/never-start/{player_name}/remove")
async def remove_never_start(
    team_id: str,
    player_name: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    team_repo, _ = _repos()
    team = _load_team(current_user.id, team_id)
    config = _get_config(team)
    config.never_on_first_period_players = [p for p in config.never_on_first_period_players if p != player_name]
    team.lineup_config = config
    team_repo.save(team)
    return _pref_redirect(team_id)
