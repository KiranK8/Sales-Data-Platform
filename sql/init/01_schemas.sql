-- Runs once, on the first start of the database.
-- IF NOT EXISTS makes it safe to run again.
CREATE SCHEMA IF NOT EXISTS bronze;  -- raw copy of every source, all TEXT, append-only
CREATE SCHEMA IF NOT EXISTS silver;  -- cleaned and standardised (built by dbt)
CREATE SCHEMA IF NOT EXISTS gold;    -- star schema that Power BI reads (built by dbt)
CREATE SCHEMA IF NOT EXISTS ops;     -- load logs, watermarks and review lists
