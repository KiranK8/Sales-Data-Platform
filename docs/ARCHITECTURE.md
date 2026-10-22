# Architecture and working rules

A pricing data platform for Rieck Logistik Gruppe, built on open-source tools.

## Data flow

Sources -> Python collectors -> PostgreSQL schema `bronze` -> dbt models in `silver` -> dbt models in `gold` -> Power BI.
Apache Airflow orchestrates the whole chain.

- **Bronze** (PostgreSQL schema `bronze`): raw copy of every source. All columns are TEXT. Never edited.
  Every table has `load_ts`, `source_file` and `file_hash`. Append-only.
- **Silver** (dbt models, schema `silver`): cleaned and standardised. German number and date formats parsed,
  customers matched to one ID, charge names mapped to one standard list, each price split into
  base rate + surcharges with validity dates.
- **Gold** (dbt models, schema `gold`): star schema. `fact_rate` plus dimensions `customer`, `lane`, `date`,
  `charge_type`, `service_mode`, `currency`. Each dimension has an Unknown row. History via dbt snapshots.
- **Power BI** reads gold only.

## Tools

Python 3.12 in `.venv`, PostgreSQL 16 in Docker, dbt Core with dbt-postgres, Airflow in Docker, Git.
All open source.

## Engineering rules

- Never hardcode passwords. Use `.env` and keep `.env.example` up to date (placeholders only).
- Never commit real data. `data/` is not tracked by Git.
- Every Python script must be re-runnable without creating duplicates (idempotent).
- Bronze is append-only.
- Keep code small and readable, with comments.
- Every piece of code has tests.
- Windows / PowerShell: commands in the docs are PowerShell commands.
- Use `pathlib`, not hard-coded backslash paths.
- Always use the project environment (`.\.venv\Scripts\Activate.ps1`, Python 3.12).
  Plain `python` on the development PC is 3.13, so create environments with `py -3.12 -m venv .venv`.
- Keep everything inside the project folder, not in OneDrive.

## Folder layout

- `data/synthetic/{incoming,archive,ground_truth}`: generated test files (not tracked)
- `data_generator/`: creates the synthetic data
- `ingestion/`: Python readers and the bronze loader
- `dbt_project/`: dbt models (silver, gold, serving), seeds, snapshots, tests
- `airflow/dags/`: Airflow DAGs
- `sql/`: plain SQL (schemas, roles, views)
- `docs/`: documentation
- `tests/`: Python tests (pytest)
