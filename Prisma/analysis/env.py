import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and fill in the values."
        )
    return value

# Database
DATABASE_URL      = _require("DATABASE_URL")
DB_HOST           = os.environ.get("DB_HOST", "localhost")
DB_PORT           = os.environ.get("DB_PORT", "5433")
DB_USER           = os.environ.get("DB_USER", "postgres")
DB_NAME           = os.environ.get("DB_NAME", "media_bias_db")

# Services
OLLAMA_BASE_URL   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")