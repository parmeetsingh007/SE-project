"""Points the test suite at its own, always-fresh SQLite file, never the
dev/demo database.

Must run before any test module imports src.models.db, since that module
reads DATABASE_URL and builds its engine at import time. pytest imports
conftest.py before collecting test modules in this directory, so this is
early enough.

The file is deleted on collection so a schema change (e.g. a new column)
never silently breaks tests against a stale file left over from a previous
run — fixtures use Base.metadata.create_all directly, not init_db(), so
they don't get the dev database's ALTER TABLE migration path.
"""

import os
from pathlib import Path

import pytest

_TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_sdlc_requirements.db"
_TEST_DB_PATH.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"


@pytest.fixture(autouse=True)
def _uncapped_shared_rate_limiter():
    """llm_client's rate limiter is a process-wide singleton shared by every
    mocked call across the whole suite. Without this, dozens of tests each
    making a call could collectively trip its real 15/60s pacing and add
    real sleeps to the suite. Tests for the limiter itself (test_rate_limiter.py)
    construct their own instances, so they're unaffected by this."""
    from src.agents import llm_client

    original_limit = llm_client._rate_limiter.limit
    llm_client._rate_limiter.limit = 1_000_000
    llm_client._rate_limiter._call_times.clear()
    yield
    llm_client._rate_limiter.limit = original_limit
