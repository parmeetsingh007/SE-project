"""Points the test suite at its own SQLite file, never the dev/demo database.

Must run before any test module imports src.models.db, since that module
reads DATABASE_URL and builds its engine at import time. pytest imports
conftest.py before collecting test modules in this directory, so this is
early enough.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///./test_sdlc_requirements.db"
