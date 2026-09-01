"""
run_model.py — runs the whole pipeline start to finish: pulls the
panel from postgres, preps it, fits the model, and writes the
residuals out to csv.

This file doesn't contain any modeling logic itself - it just calls
each piece in the right order and passes the right things between
them.
"""

import os

from pricing_model import db, data_prep, regression
from pricing_model import residuals as residuals_module


def main():
    # step 1: pull the raw panel out of postgres
    engine = db.get_engine()
    raw_panel = db.load_panel_data(engine)

    # step 2: clean it up, log-transform it, demean it by week
    prepared = data_prep.prepare_model_data(raw_panel)

    # step 3: fit the demeaned regression and get beta_hat back
    fit_result = regression.fit_model(prepared["X"], prepared["y"])

    # step 4: make sure the output folder actually exists before
    # trying to write anything into it - won't error out if it's
    # already there
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    full_history_path = os.path.join(output_dir, "residuals_full_history.csv")
    latest_snapshot_path = os.path.join(output_dir, "residuals_latest.csv")

    # step 5: recover the week effects, rebuild implied price in USD,
    # compute the z-score, write both csv files
    residuals_module.build_residuals_output(
        prepared["logged_data"],
        fit_result["beta_hat"],
        fit_result["residuals"],
        full_history_path,
        latest_snapshot_path,
    )


if __name__ == "__main__":
    main()