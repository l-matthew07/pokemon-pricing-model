"""
data_prep.py — turns the raw panel from db.py into what regression.py
and residuals.py each need.

Two different shapes come out of here, because regression.py and
residuals.py want different things:
    - regression.py needs the demeaned X and y as plain numpy arrays,
      no set_id or dates mixed in, ready to hand straight to OLS.
    - residuals.py needs the original (non-demeaned) logged data,
      with set_id and week_start still attached, so it can figure out
      which row belongs to which set when it recovers the week effects.
"""

import numpy as np
import pandas as pd

from pricing_model import config


def add_age_column(df):
    """
    Adds an 'age' column: how many full weeks old the set was at that
    observation. db.py gives us release_date and week_start separately
    instead of a precomputed age, since age changes every week and
    there's no reason to store a moving target in the database.
    """
    df = df.copy()
    days_old = (df[config.WEEK_COL] - df[config.RELEASE_DATE_COL]).dt.days
    df["age"] = days_old // 7
    return df


def log_transform(df):
    """
    Adds a log_ version of the outcome and every continuous predictor,
    for the log-log spec. Keeps the originals around too — makes it a
    lot easier to sanity-check things later without re-deriving raw
    prices from logs every time you want to print a row and eyeball it.

    Dummy predictors (in_print, specialty_set) skip this entirely —
    logging a 0/1 column just isn't a meaningful thing to do.
    """
    df = df.copy()

    df[f"log_{config.OUTCOME_COL}"] = np.log(df[config.OUTCOME_COL])

    for col in config.CONTINUOUS_PREDICTORS:
        df[f"log_{col}"] = np.log(df[col])

    return df


def demean_by_week(df, columns, week_col):
    """
    The actual FWL step. For each column given, subtracts that week's
    average from every row in that week. groupby(...).transform("mean")
    is what does the heavy lifting here — it computes each week's mean
    and then broadcasts that mean back out to every row belonging to
    that week, so the subtraction below lines up row-for-row without
    needing a manual loop over weeks.
    """
    week_means = df.groupby(week_col)[columns].transform("mean")
    demeaned = df[columns] - week_means
    return demeaned


def prepare_model_data(df):
    """
    Runs the full prep pipeline in order and hands back everything
    both regression.py and residuals.py need. Order matters: age has
    to exist before it can be logged, and everything has to be logged
    before it gets demeaned, since the model lives in log-log space.
    """
    df = add_age_column(df)
    df = log_transform(df)

    outcome_log_col = f"log_{config.OUTCOME_COL}"

    # this is the fixed column order the design matrix X will follow —
    # log_break_even_price, log_grading_premium, log_age, then the
    # dummies untouched. regression.py trusts this exact order, so
    # "column 2 of X" means the same thing everywhere downstream.
    predictor_log_cols = (
        [f"log_{col}" for col in config.CONTINUOUS_PREDICTORS]
        + config.DUMMY_PREDICTORS
    )

    columns_to_demean = [outcome_log_col] + predictor_log_cols
    demeaned = demean_by_week(df, columns_to_demean, config.WEEK_COL)

    y = demeaned[outcome_log_col].to_numpy()
    X = demeaned[predictor_log_cols].to_numpy()

    # smearing correction (residuals.py) needs the demeaned regression's
    # residuals, which needs y and X lined up with set_id/week_start so
    # you can tell which residual belongs to which observation later.
    set_id = df[config.SET_ID_COL].to_numpy()
    week = df[config.WEEK_COL].to_numpy()

    # residuals.py recovers δ_t using the ORIGINAL, non-demeaned logged
    # values — so that version has to survive past this function too,
    # not just the demeaned arrays above.
    logged_data = df[
        [config.SET_ID_COL, config.WEEK_COL, outcome_log_col] + predictor_log_cols
    ].copy()

    return {
        "X": X,
        "y": y,
        "set_id": set_id,
        "week": week,
        "logged_data": logged_data,
    }