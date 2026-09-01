"""
regression.py — fits the demeaned OLS regression and returns beta_hat
plus the residuals it produces.

This file doesn't know anything about weeks, sets, or dollars. It just
takes whatever X and y it's handed and fits a line through them. All
of that other context gets attached back on in residuals.py.
"""

import numpy as np


def fit_ols(X, y):
    """
    Solves for beta_hat using np.linalg.lstsq instead of the textbook

    No intercept gets added here. X and y already had their week's
    average subtracted out in data_prep.py, so every column already
    sums to zero within each week — fitting an intercept on top of
    that would just estimate something that has to come out at zero
    anyway.
    """
    # lstsq returns four things — the solution itself, plus some extra
    # diagnostic info (residual sum of squares, rank of X, singular
    # values) that isn't needed here, hence the underscores.
    beta_hat, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    return beta_hat


def predict(X, beta_hat):
    """
    Applies beta_hat to X and returns the fitted values. Kept as its
    own function rather than folded into fit_ols, since residuals.py
    will need this exact operation again later on a different X.
    """
    return X @ beta_hat


def compute_residuals(y, y_hat):
    """
    Actual minus predicted, one value per row. Since y is demeaned log
    price, this comes out as a demeaned log-price residual too — this
    is the array residuals.py will pull the smearing factor from.
    """
    return y - y_hat


def fit_model(X, y):
    """
    Runs the fit end to end and hands back everything downstream code
    needs, bundled into one dict rather than several loose return
    values.
    """
    beta_hat = fit_ols(X, y)
    y_hat = predict(X, beta_hat)
    residuals = compute_residuals(y, y_hat)

    return {
        "beta_hat": beta_hat,
        "fitted_values": y_hat,
        "residuals": residuals,
    }