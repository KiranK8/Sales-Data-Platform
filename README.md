# rieck-pricing-platform

A pricing data platform for Rieck Logistik Gruppe: one trusted price per customer and lane.

**Flow:** Sources -> Python -> PostgreSQL `bronze` (raw) -> dbt `silver` (clean) -> dbt `gold` (star schema) -> Power BI.
Apache Airflow runs the chain. Everything is open source.

## Setup (Windows / PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version          # should show 3.12.x
pip install -r requirements.txt
Copy-Item .env.example .env   # then fill in your own values
```

## Folders

| Folder | Purpose |
|---|---|
| `data/synthetic/` | Fake source files (not committed) |
| `data_generator/` | Creates the synthetic data |
| `ingestion/readers/` | Readers for Excel, CSV, PDF, Word, databases |
| `dbt_project/` | dbt models, seeds, snapshots, tests |
| `airflow/dags/` | Airflow DAGs |
| `sql/` | Plain SQL scripts |
| `docs/` | Documentation |
| `tests/` | Python tests |

## Load the raw files into bronze

```powershell
docker compose up -d                      # PostgreSQL must be running
python -m data_generator.generate         # fake source files (only once)
python -m ingestion.load_bronze           # Excel, CSV and legacy .dat -> schema "bronze"
python -m pytest -q                       # tests (they use a temporary database)
```

Bronze stores every value as TEXT, exactly as received, and is append-only. A file that was already loaded
(same SHA-256) is skipped. Look at `ops.load_log` to see what happened to each file.

See `docs/ARCHITECTURE.md` for the architecture and working rules.
