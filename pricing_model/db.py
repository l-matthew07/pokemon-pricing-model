"""
db.py — the only file in this project that talks to Postgres.

Every other module gets its data by calling load_panel_data() below.
None of them import sqlalchemy or write SQL directly — if the database
connection details or table structure ever change, this is the one
file that needs editing.
"""

import os
from sqlalchemy import create_engine, text
import pandas as pd
from dotenv import load_dotenv

from pricing_model import config

def get_engine():
    """
    Build a SQLAlchemy engine: a reusable handle that knows how to open
    connections to Postgres on demand. This does NOT open a connection
    itself yet — it's created once per script run and passed around to
    whatever function needs to run a query.
    """
    # load_dotenv() reads the .env file in the project root and copies
    # its key=value pairs into this process's environment variables.
    load_dotenv()

    # os.environ[...] (square brackets, not .get()) raises a clear
    # KeyError immediately if DATABASE_URL is missing. That's on
    # purpose — better to fail loudly here than get a confusing
    # connection error two function calls later.
    database_url = os.environ["DATABASE_URL"]

    # create_engine() doesn't open a connection yet — it just
    # configures HOW connections will be made when something actually
    # needs one. Call this once per script run.
    engine = create_engine(database_url)
    return engine

def load_panel_data(engine):
    """
    Run the panel query against Postgres and return the result as a
    pandas DataFrame — one row per (set_id, week_start) observation,
    already restricted to rows that are in scope for the model.

    The filtering below is enforced here even though the database is
    expected to only ever contain in-scope rows (see the schema
    comment at the top of config.py). This is a safety net: if a
    future insert on the data-collection side ever violates that
    assumption, this query won't silently let the bad rows through.
    """
    # Build the column list from config.py instead of writing SELECT *.
    # This means db.py won't silently pick up a new column

    all_columns = (
        [config.SET_ID_COL, config.WEEK_COL, config.RELEASE_DATE_COL, config.OUTCOME_COL]
        + config.PREDICTOR_COLUMNS
    )

    # "age" isn't a real Postgres column — it gets computed later in
    # data_prep.py from release_date and week_start. Drop it here so
    # we don't ask the database to SELECT a column that doesn't exist.
    columns_to_select = [c for c in all_columns if c != "age"]

    # Turns the list into a comma-separated string for the SQL query,
    # e.g. "set_id, week_start, price, break_even_price, ..."
    column_list_sql = ", ".join(columns_to_select)

    query = text(f"""
        SELECT {column_list_sql}
        FROM {config.PANEL_TABLE}
        WHERE
            -- Condition 1: per-set exclusion of each set's first 3 weeks.
            -- A set only enters the panel once it's at least 4 weeks old.
            {config.WEEK_COL} >= {config.RELEASE_DATE_COL} + INTERVAL '4 weeks'
            AND
            -- Condition 2: panel-wide start date. No row before this
            -- date is in scope, no matter how old that set already is.
            {config.WEEK_COL} >= :panel_start_date
        ORDER BY {config.SET_ID_COL}, {config.WEEK_COL}
    """)

    # pd.read_sql_query() runs the query through the engine and parses
    # the result straight into a DataFrame — no manual row-by-row loop.
    # `params` supplies the actual value for :panel_start_date.
    df = pd.read_sql_query(
        query,
        engine,
        params={"panel_start_date": config.PANEL_START_DATE},
    )

    return df