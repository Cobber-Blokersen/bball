#!/bin/bash
# Start the Basketball Lineup Optimizer web app locally

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR"

echo -e "${YELLOW}Basketball Lineup Optimizer - Local Development${NC}"
echo "=================================================="
echo ""

# Check if virtual environment exists
if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    cd "$PROJECT_ROOT"
    python -m venv .venv
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source "$PROJECT_ROOT/.venv/bin/activate"

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
# pip install -e . -q
uv sync

# Check if running on Windows (Git Bash or similar)
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows path
    PYTHON_PATH="$PROJECT_ROOT/.venv/Scripts/python.exe"
else
    # Unix path
    PYTHON_PATH="$PROJECT_ROOT/.venv/bin/python"
fi

# Run the app
echo -e "${GREEN}Starting web app...${NC}"
echo -e "${GREEN}Open your browser to: http://localhost:8000${NC}"
echo -e "${GREEN}API Docs available at: http://localhost:8000/docs${NC}"
echo ""

cd "$PROJECT_ROOT"
$PYTHON_PATH -m src.bball.web.run

deactivate
