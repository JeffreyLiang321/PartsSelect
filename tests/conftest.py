"""
Test environment. Must run before `main` is imported: config reads these at
import time, and load_dotenv() never overrides variables that are already set,
so a developer's real .env key is not used.
"""

import os
import sys

os.environ["OPENAI_API_KEY"] = "test-key-not-real"
os.environ["ALLOWED_ORIGINS"] = "https://app.example"
os.environ["TRUSTED_PROXY_HOPS"] = "0"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
