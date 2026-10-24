"""Central configuration. Secrets come from environment variables only."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def env(key, default=None):
    return os.environ.get(key, default)


CERTS = Path(env("VAULTIQ_CERTS", BASE / "certs"))
VAULT = Path(env("VAULTIQ_VAULT", BASE / "vault" / "signed"))
DB_PATH = Path(env("VAULTIQ_DB", BASE / "vault" / "vaultiq.db"))
TEMPLATES = BASE / "templates"
DSS_JAR = Path(env("VAULTIQ_DSS_JAR", BASE / "dss" / "target" / "vaultiq-dss.jar"))

TSA_URL = env("TSA_URL", "https://freetsa.org/tsr")
P12_PASSWORD = env("VAULTIQ_P12_PASSWORD")

ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

ADMIN_USER = env("ADMIN_USER", "admin")
ADMIN_PASSWORD = env("ADMIN_PASSWORD")

ANNUAL_RATE = float(env("LOAN_ANNUAL_RATE", "0.12"))
CORS_ORIGINS = [o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173").split(",")]

# Risk gating (Section 1.5 of the project document)
THRESH_BLOCK = 40   # score < 40  -> blocked
THRESH_AUTO = 70    # score > 70  -> auto-proceed, 40..70 -> manual review

USER_TOKEN_MINUTES = 15
ADMIN_TOKEN_MINUTES = 8 * 60
MAX_ID_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VERIFY_BYTES = 20 * 1024 * 1024
