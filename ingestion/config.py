"""Settings for the ingestion code: database connection (from .env) and folders (pathlib)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "data" / "synthetic" / "incoming"
ARCHIVE = ROOT / "data" / "synthetic" / "archive"
LAYOUT_FILE = ROOT / "data_generator" / "legacy_layout.yaml"
ENV_FILE = ROOT / ".env"

REQUIRED = ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_PORT"]


@dataclass(frozen=True)
class DbSettings:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)   # repr=False: the password never shows up in logs or error messages

    def url(self, database=None):
        """SQLAlchemy connection URL. URL.create escapes special characters in the password for us."""
        return URL.create("postgresql+psycopg2", username=self.user, password=self.password,
                          host=self.host, port=self.port, database=database or self.database)


def load_settings(env_file=ENV_FILE):
    """Read the connection settings from .env (values already set in the environment win)."""
    load_dotenv(env_file)
    missing = [name for name in REQUIRED if not os.getenv(name)]
    if missing:   # only the NAMES are reported, never the values
        raise RuntimeError(f"Missing in .env: {', '.join(missing)}. Copy .env.example to .env and fill it in.")
    return DbSettings(host=os.getenv("POSTGRES_HOST", "localhost"), port=int(os.environ["POSTGRES_PORT"]),
                      database=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
                      password=os.environ["POSTGRES_PASSWORD"])
