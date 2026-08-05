"""Main FastAPI application."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .auth import CurrentUser, create_default_admin, get_current_user
from .routes import admin, pages, teams
from .templating import jinja_env

STATIC_DIR = Path(__file__).parent / "static"

# Create app
app = FastAPI(
    title="Basketball Lineup Optimizer",
    description="Optimize basketball team lineups",
    version="1.0.0",
)

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialize default admin user
create_default_admin()

# Include API routes
app.include_router(admin.router)
app.include_router(teams.router)
app.include_router(pages.router)


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    """Home page."""
    template = jinja_env.get_template("index.html")
    return template.render(
        is_admin=current_user.is_admin,
        user_name=current_user.name,
    )


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "message": "Basketball Lineup Optimizer is running"}
