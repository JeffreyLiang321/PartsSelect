import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "..", "data")
DB_PATH     = os.path.join(DATA_DIR, "parts.db")
CHROMA_PATH = os.path.join(DATA_DIR, "chroma")

OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]

EMBEDDING_MODEL = "text-embedding-3-small"
# gpt-6-luna: matched/beat gpt-5.4-mini and gpt-6.1-terra on eval.py at ~1/9 the cost.
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-6-luna")
# gpt-6 models reject function tools on /v1/chat/completions unless reasoning is off.
# Set OPENAI_REASONING_EFFORT="" to omit the parameter (e.g. for gpt-5.4-mini).
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "none")

MAX_ITERATIONS = 10

VECTOR_TOP_K        = 5
SYMPTOM_RESULTS_MAX = 10