from __future__ import annotations

import os

import pytest

from bball import settings
from bball.web.auth import DEFAULT_ADMIN_ID


@pytest.fixture(scope="session", autouse=True)
def isolated_test_environment(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Point the SQLite backend at a throwaway database for the whole session.

    Keeps tests from reading or writing the real ``data/sqlite/bball.sqlite3`` and
    runs CLI commands as the default admin user.
    """
    data_dir = tmp_path_factory.mktemp("sqlite")
    original_db_path = settings.DB_PATH
    original_data_dir = settings.DATA_DIR
    settings.DB_PATH = data_dir / "test_bball.sqlite3"
    settings.DATA_DIR = data_dir
    os.environ["BBALL_USER_ID"] = DEFAULT_ADMIN_ID
    try:
        yield
    finally:
        settings.DB_PATH = original_db_path
        settings.DATA_DIR = original_data_dir
        os.environ.pop("BBALL_USER_ID", None)
