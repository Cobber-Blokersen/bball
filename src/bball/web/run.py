"""Development and production entry point."""

import os
import sys

import uvicorn


def run_local():
    """Run the application locally with uvicorn."""
    uvicorn.run(
        "bball.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


def run_production():
    """Run the application in production mode."""
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(
        "bball.web.app:app",
        host="0.0.0.0",
        port=port,
        workers=4,
    )


def main():
    """Console-script entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "production":
        run_production()
    else:
        run_local()


if __name__ == "__main__":
    main()
