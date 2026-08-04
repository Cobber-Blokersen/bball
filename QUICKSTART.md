# Quick Start Guide for Basketball Lineup Optimizer Web App

## Overview

Ponko has created a complete web application with:
- ✅ FastAPI backend with REST API
- ✅ Role-based access control (User & Admin)
- ✅ Admin panel for user management
- ✅ Team and game management UI
- ✅ Local development setup scripts
- ✅ CloudRun deployment ready
- ✅ Database with user persistence

## Starting the Web App

### Windows (PowerShell)
```powershell
.\start-local.ps1
```

### macOS/Linux (Bash)
```bash
chmod +x start-local.sh
./start-local.sh
```

### Manual Start
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# OR
.venv\Scripts\activate            # Windows

# Install dependencies
pip install -e .

# Start development server
python -m src.bball.web.run
```

## Access the App

After starting, open your browser:
- **Web App**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc

## Default Login

For local development, you're automatically logged in as:
- **User**: Admin
- **Email**: admin@localhost
- **Role**: admin

## Features Available

### Admin Features
1. **User Management** (`/admin/users`)
   - Create new users
   - Delete users
   - Assign roles (user or admin)

### User Features
1. **Teams** (`/teams`)
   - Create teams
   - Add/remove players
   - View team details

2. **Games**
   - Record games
   - Generate lineup spins
   - Track player usage

## API Usage

All API endpoints are documented at `/docs` with interactive testing.

### Example: Create a Team
```bash
curl -X POST http://localhost:8000/teams \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Basketball Team",
    "player_names": ["Player 1", "Player 2", "Player 3"]
  }'
```

### Example: List Teams
```bash
curl http://localhost:8000/teams
```

## CLI Still Works

The original CLI is still available:
```bash
python -m src.bball.cli team list --user admin-001
```

## Deployment

### To Google Cloud Run

```bash
gcloud builds submit --config=cloudbuild.yaml --project=YOUR_PROJECT_ID
```

This will:
1. Build Docker image
2. Push to Container Registry
3. Deploy to Cloud Run

### Environment Variables

```
PORT=8080           # For Cloud Run
BBALL_BACKEND=sqlite
```

## Project Structure

```
src/bball/web/
├── app.py              # Main FastAPI application
├── auth.py             # Authentication & authorization
├── run.py              # Development/production runner
├── routes/
│   ├── admin.py        # Admin API routes
│   └── teams.py        # Team/game API routes
├── templates/          # HTML templates
│   ├── base.html       # Base template
│   └── index.html      # Home page
└── static/             # CSS, JS, images
```

## Troubleshooting

### Port Already in Use
If port 8000 is in use, modify `start-local.ps1` or `start-local.sh`:
```bash
python -m src.bball.web.run --port 8001
```

### Module Not Found Errors
```bash
pip install -e . --upgrade
```

### Database Issues
Reset the database:
```bash
rm data/sqlite/bball.sqlite3
python -m src.bball.cli system db-create --user admin-001
```

## Next Steps

1. Explore the API at `/docs`
2. Create some test teams
3. Add players to teams
4. Try generating lineups
5. Check out the admin panel

## Support

For issues or questions:
- Check the API documentation: `/docs`
- Review the code in `src/bball/web/`
- Check `WEB_APP.md` for detailed documentation
