"""
residuals.py — takes beta_hat and the demeaned regression's residuals
and turns them into the real output: an implied price in USD for
every set-week row, and a z-score saying how over- or under-priced
that row is relative to the rest of the panel.
"""

import numpy as np
import pandas as pd

from pricing_model import config


def _predictor_log_columns():
    """
    Rebuilds the exact column order data_prep.py used when it built X.
    This has to match that file exactly - if the two ever drift apart,
    X_it·beta_hat would end up multiplying the wrong coefficient
    against the wrong column, and nothing would throw an error to
    warn you.
    """
    return [f"log_{col}" for col in config.CONTINUOUS_PREDICTORS] + config.DUMMY_PREDICTORS


def recover_week_fixed_effects(logged_data, beta_hat):
    """
    Computes delta_hat_t for every week - the piece demeaning strips
    out and OLS never estimates directly. Deliberately uses the
    original, non-demeaned X here, since delta_hat_t is defined as the
    average gap between actual and predicted log price using real
    values, not the week-centered ones.
    """
    predictor_cols = _predictor_log_columns()
    outcome_log_col = f"log_{config.OUTCOME_COL}"

    X = logged_data[predictor_cols].to_numpy()
    predicted_log_price = X @ beta_hat

    gap = logged_data[outcome_log_col].to_numpy() - predicted_log_price

    # small frame just to make grouping the gap by week straightforward
    gap_by_week = pd.DataFrame({
        config.WEEK_COL: logged_data[config.WEEK_COL],
        "gap": gap,
    })

    week_fixed_effects = gap_by_week.groupby(config.WEEK_COL)["gap"].mean()
    week_fixed_effects.name = "delta_hat"
    return week_fixed_effects


def compute_smearing_factor(residuals):
    """
    One number for the whole panel - the average of exp() applied to
    every residual from the demeaned regression. This is what nudges
    the naive exponentiated price back up from a median estimate
    toward a mean estimate.
    """
    return np.mean(np.exp(residuals))


def compute_implied_price(logged_data, beta_hat, week_fixed_effects, smearing_factor):
    """
    Rebuilds price in USD for every row. X_it·beta_hat gives the
    model's log prediction, delta_hat_t adds that week's price level
    back in, exp() converts out of log space, and the smearing factor
    corrects for the exp() undershoot.
    """
    predictor_cols = _predictor_log_columns()
    X = logged_data[predictor_cols].to_numpy()
    predicted_log_price = X @ beta_hat

    # matches each row to its own week's delta_hat by looking up that
    # row's week_start value against the Series recover_week_fixed_effects
    # returned - this still lines up correctly even though weeks don't
    # all have the same number of sets in them
    delta_for_row = logged_data[config.WEEK_COL].map(week_fixed_effects).to_numpy()

    implied_log_price = predicted_log_price + delta_for_row
    implied_price_usd = np.exp(implied_log_price) * smearing_factor

    result = logged_data.copy()
    result["implied_price_usd"] = implied_price_usd
    return result


def compute_usd_residuals(df):
    """
    Actual price minus implied price, in real dollars. Positive means
    the set is trading above what its characteristics predict,
    negative means it's trading below.
    """
    df = df.copy()
    df["residual_usd"] = df[config.OUTCOME_COL] - df["implied_price_usd"]
    return df


def compute_mispricing_zscore(df):
    """
    Standardizes residual_usd against the whole panel at once - one
    mean and one standard deviation across every set and every week,
    not per set. This is what makes the number comparable across
    sets: a z-score of +2 means priced further above the model's
    expectation than roughly 97% of every other set-week observation
    in the panel, regardless of which set it is.
    """
    df = df.copy()
    pooled_mean = df["residual_usd"].mean()
    pooled_std = df["residual_usd"].std()
    df["mispricing_zscore"] = (df["residual_usd"] - pooled_mean) / pooled_std
    return df


def export_full_history_csv(df, path):
    """
    Writes every row - every set, every week - to disk. This is the
    file the historical price and residual charts will read from
    later, so nothing gets filtered out here.
    """
    df.to_csv(path, index=False)


def export_latest_snapshot_csv(df, path):
    """
    Filters down to just the single most recent week in the data and
    writes that out on its own - one row per set, showing where
    things stand right now. This is the table that actually answers
    which ETBs are over- or under-priced today.
    """
    latest_week = df[config.WEEK_COL].max()
    latest = df[df[config.WEEK_COL] == latest_week]
    latest.to_csv(path, index=False)


def build_residuals_output(logged_data, beta_hat, residuals, full_history_path, latest_snapshot_path):
    """
    Runs the whole pipeline end to end: recovers the week effects,
    computes the smearing factor, rebuilds implied price in USD, turns
    that into residuals and a pooled z-score, then writes both files.
    """
    week_fixed_effects = recover_week_fixed_effects(logged_data, beta_hat)
    smearing_factor = compute_smearing_factor(residuals)

    df = compute_implied_price(logged_data, beta_hat, week_fixed_effects, smearing_factor)
    df = compute_usd_residuals(df)
    df = compute_mispricing_zscore(df)

    export_full_history_csv(df, full_history_path)
    export_latest_snapshot_csv(df, latest_snapshot_path)

    return df