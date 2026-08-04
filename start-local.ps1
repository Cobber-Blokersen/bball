# Start the Basketball Lineup Optimizer web app locally

$ErrorActionPreference = "Stop"

# Colors and formatting
$Yellow = "`e[1;33m"
$Green = "`e[0;32m"
$Red = "`e[0;31m"
$NC = "`e[0m"

# Get project root
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "$Yellow`nBasketball Lineup Optimizer - Local Development$NC"
Write-Host "=================================================="
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path "$ProjectRoot\.venv")) {
    Write-Host "${Yellow}Creating virtual environment...${NC}"
    Push-Location $ProjectRoot
    python -m venv .venv
    Pop-Location
}

# Activate virtual environment
Write-Host "${Yellow}Activating virtual environment...${NC}"
& "$ProjectRoot\.venv\Scripts\Activate.ps1"

# Install dependencies
Write-Host "${Yellow}Installing dependencies...${NC}"
# pip install -e . -q
uv sync

# Run the app
Write-Host "$Green`nStarting web app...$NC"
Write-Host "$Green`nOpen your browser to: http://localhost:8000$NC"
Write-Host "$Green`nAPI Docs available at: http://localhost:8000/docs$NC"
Write-Host ""

Push-Location $ProjectRoot
python -m src.bball.web.run
