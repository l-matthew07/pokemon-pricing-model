"""
config.py — central place for constant values used across the model.

--------------------------------------------------------------------
EXPECTED POSTGRES SCHEMA
--------------------------------------------------------------------
This model expects a single panel table (long format — one row per
set-week observation) called `panel_data`, with the following columns:

    set_id            TEXT      -- unique identifier per ETB set (e.g. 'twilight_masquerade')
    week_start        DATE      -- anchor date of the observation week (e.g. every Monday)
    release_date      DATE      -- the set's original release date (used to compute Age)
    price             NUMERIC   -- outcome variable: weekly market price of the ETB
    break_even_price  NUMERIC   -- predictor: cost to break even (raw card value)
    grading_premium   NUMERIC   -- predictor: PSA10 promo price / raw promo price
    in_print          BOOLEAN   -- predictor: TRUE if the set is still being printed that week
    specialty_set     BOOLEAN   -- predictor: TRUE if holiday/special-run set (time-invariant per set)

Constraints:
    - PRIMARY KEY (set_id, week_start)     -- one row per set per week, no duplicates
    - price, break_even_price, grading_premium must be > 0 (required for log transform)
    - No NULLs in the columns above, for any row that's already in scope
      (the weeks-1-3 exclusion and panel-start-date rules mean those rows
      should simply never be inserted, not inserted and filtered out later)

"""

# --- Table name ---------------------------------------------------------
PANEL_TABLE = "panel_data"

# --- Column names ---------------------------------------------------------
SET_ID_COL = "set_id"
WEEK_COL = "week_start"
RELEASE_DATE_COL = "release_date"
OUTCOME_COL = "price"

# Continuous predictors — these get log-transformed (log-log spec).
CONTINUOUS_PREDICTORS = [
    "break_even_price",
    "grading_premium",
    # "age" is NOT a raw column. It's computed in data_prep.py as
    # WEEK_COL - RELEASE_DATE_COL, then added under this name.
    "age",
]

# Dummy predictors — 0/1, never log-transformed.
DUMMY_PREDICTORS = [
    "in_print",
    "specialty_set",
]

# Every predictor in the design matrix, in a fixed order. regression.py
# builds the columns of X in exactly this order, so this list IS the
# definition of what "column 3 of X" means everywhere downstream.
PREDICTOR_COLUMNS = CONTINUOUS_PREDICTORS + DUMMY_PREDICTORS

PANEL_START_DATE = "2024-06-21"