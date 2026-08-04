# Basketball Lineup Optimizer Web App

A FastAPI web application for managing basketball teams and generating optimal lineups.

## Features

- **Team Management**: Create and manage basketball teams with player rosters
- **Game Planning**: Record games and generate lineup spins
- **Admin Panel**: User management with role-based access control
- **Web UI**: Clean, modern interface built with HTML/CSS
- **REST API**: Full API documentation with OpenAPI/Swagger
- **Local Development**: Easy setup and local testing
- **Cloud Ready**: Deployable to Google Cloud Run

## Architecture

```
src/bball/
├── models.py           # Data models (User, Team, Game, etc.)
├── cli.py              # CLI interface (original)
├── repositories*.py    # Data persistence layer
├── solver.py           # Lineup optimization logic
└── web/
    ├── app.py          # Main FastAPI application
    ├── auth.py         # Authentication and authorization
    ├── run.py          # Development/production entry point
    ├── routes/
    │   ├── admin.py    # Admin user management routes
    │   └── teams.py    # Team and game management routes
    ├── templates/      # Jinja2 HTML templates
    └── static/         # CSS, JavaScript, images
```

## Local Development

### Prerequisites

- Python 3.11+
- SQLite3 (included with Python)

### Quick Start

**On macOS/Linux:**
```bash
./start-local.sh
```

**On Windows (PowerShell):**
```powershell
.\start-local.ps1
```

This script will:
1. Create a Python virtual environment (if not exists)
2. Install dependencies
3. Start the development server

### Manual Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate  # Windows

# Install the package
pip install -e .

# Run the development server
python -m src.bball.web.run
```

The app will be available at: **http://localhost:8000**

- Web UI: http://localhost:8000
- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Usage

### Default Admin User

For local development, a default admin user is automatically created:
- **ID**: `admin-001`
- **Email**: `admin@localhost`
- **Role**: `admin`

### Authentication

**For Local Development:**
- No authentication required by default (admin user is automatically loaded)

**For Production:**
- Use the `Authorization: Bearer {user_id}` header to authenticate
- Example: `Authorization: Bearer admin-001`

## API Endpoints

### Admin Routes (`/admin`)

```
GET    /admin/users              - List all users
POST   /admin/users              - Create a new user
GET    /admin/users/{user_id}    - Get a specific user
PATCH  /admin/users/{user_id}    - Update a user
DELETE /admin/users/{user_id}    - Delete a user
```

### Team Routes (`/teams`)

```
GET    /teams                    - List user's teams
POST   /teams                    - Create a new team
GET    /teams/{team_id}          - Get a specific team
DELETE /teams/{team_id}          - Delete a team
POST   /teams/{team_id}/players  - Add a player to a team
DELETE /teams/{team_id}/players/{player_name} - Remove a player
GET    /teams/{team_id}/games    - List games for a team
```

## Role-Based Access Control

### User Role
- Create and manage their own teams
- Add/remove players
- Record games and spins
- View their own data

### Admin Role
- All user permissions
- Create, update, and delete users
- Manage user data on their behalf
- Access to admin panel

## Database

The app uses SQLite by default (configurable). Database file location:
- Local: `data/sqlite/bball.sqlite3`

To use in-memory storage (for testing):
- Set environment variable: `BBALL_BACKEND=inmemory`

## Deployment to Google Cloud Run

### Prerequisites

- Google Cloud Project with Cloud Run and Container Registry enabled
- `gcloud` CLI installed and authenticated
- Docker installed

### Deploy

```bash
# Set your project ID
export PROJECT_ID=your-project-id

# Build and deploy
gcloud builds submit --config=cloudbuild.yaml --project=$PROJECT_ID
```

The deployment will:
1. Build a Docker image
2. Push to Container Registry
3. Deploy to Cloud Run

### Environment Variables (Production)

```
PORT=8080                    # Port to run on
BBALL_BACKEND=sqlite         # Storage backend
```

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Quality

```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/
```

### Adding New Admin Features

1. Create routes in `src/bball/web/routes/admin.py`
2. Add authorization with `@require_admin` decorator
3. Add templates in `src/bball/web/templates/`

### Adding New User Features

1. Create routes in `src/bball/web/routes/teams.py`
2. Use `@get_current_user` dependency
3. Filter data by `current_user.id`
4. Add templates as needed

## Future Enhancements

- [ ] Real OAuth2 authentication (Google, GitHub)
- [ ] Database migrations with Alembic
- [ ] Game lineup generation UI
- [ ] Statistics and reporting
- [ ] Team sharing and collaboration
- [ ] Mobile app
- [ ] WebSocket support for real-time updates

## License

MIT
