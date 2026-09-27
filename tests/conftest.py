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

_TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_sdlc_requirements.db"
_TEST_DB_PATH.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
