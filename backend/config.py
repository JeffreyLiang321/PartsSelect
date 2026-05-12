import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "..", "data")
DB_PATH     = os.path.join(DATA_DIR, "parts.db")
CHROMA_PATH = os.path.join(DATA_DIR, "chroma")

OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

EMBEDDING_MODEL = "text-embedding-3-small"
CLAUDE_MODEL    = "claude-sonnet-4-5"

MAX_ITERATIONS = 10

VECTOR_TOP_K        = 5
SYMPTOM_RESULTS_MAX = 10