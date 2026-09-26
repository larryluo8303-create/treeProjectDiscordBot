"""Shared test fixtures.

Sets the credentials the API server requires at startup (fail-closed since
the critical-security fixes).  These are test-only values; real deployments
must set them via environment variables / .env (see .env.example).
"""

import os

os.environ.setdefault("API_USERNAME", "testuser")
os.environ.setdefault("API_PASSWORD", "testpass-for-tests-only")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key-32-chars-minimum!!")
