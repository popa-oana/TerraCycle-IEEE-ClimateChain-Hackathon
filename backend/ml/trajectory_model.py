"""
backend/ml/trajectory_model.py — Gaussian Process Regression for NDVI trajectories

Day 6C.1 for TerraCycle Proof. Learns a separate GPR model for each parcel
to model NDVI as a function of elapsed days since the first observation.

This is an EXPERIMENTAL regression module. It does NOT:
- create compliance labels,
- predict compliance verdicts,
- claim predictive accuracy,
- interpolate missing dates or invent measurements,
- modify satellite data.

Each parcel's model is trained independently. Predictions include a
predictive standard deviation (uncertainty estimate).

Kernel: ConstantKernel * Matern + WhiteKernel (scikit-learn defaults).
"""
from __future__ import annotations

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import (
    ConstantKernel,
    Matern,
    WhiteKernel,
)

# Deterministic seed for reproducibility
RANDOM_SEED = 42

# Kernel hyperparameters (simple, stable)
KERNEL_CONSTANT_VALUE = 1.0
KERNEL_MATERN_LENGTH_SCALE = 30.0  # days
KERNEL_MATERN_NU = 1.5
KERNEL_WHITE_NOISE_LEVEL = 0.01

# Minimum observations required for training
MIN_OBSERVATIONS = 3


def build_kernel() -> object:
    """Build the GPR kernel: ConstantKernel * Matern + WhiteKernel."""
    constant = ConstantKernel(
        constant_value=KERNEL_CONSTANT_VALUE,
        constant_value_bounds=(1e-3, 1e3),
    )
    matern = Matern(
        length_scale=KERNEL_MATERN_LENGTH_SCALE,
        length_scale_bounds=(1e-2, 1e3),
        nu=KERNEL_MATERN_NU,
    )
    white = WhiteKernel(
        noise_level=KERNEL_WHITE_NOISE_LEVEL,
        noise_level_bounds=(1e-10, 1e1),
    )
    return constant * matern + white


def build_model() -> GaussianProcessRegressor:
    """Build a GaussianProcessRegressor with the standard kernel."""
    return GaussianProcessRegressor(
        kernel=build_kernel(),
        normalize_y=True,
        random_state=RANDOM_SEED,
        optimizer="fmin_l_bfgs_b",
        n_restarts_optimizer=1,
    )


def train_parcel_model(
    parcel_id: str,
    elapsed_days: np.ndarray,
    ndvi_values: np.ndarray,
) -> dict[str, object]:
    """
    Train a GPR model for one parcel.

    Parameters
    ----------
    parcel_id : str
        Parcel identifier (e.g., "parcel_01").
    elapsed_days : np.ndarray, shape (n,)
        Elapsed days since the first observation for each acquisition.
    ndvi_values : np.ndarray, shape (n,)
        Corresponding NDVI measurements.

    Returns
    -------
    dict with:
        model : GaussianProcessRegressor or None (if insufficient data)
        parcel_id : str
        observation_count : int
        trained : bool (True if model was fitted)
        error : str or None (reason if training failed)
    """
    obs_count = len(elapsed_days)

    if obs_count < MIN_OBSERVATIONS:
        return {
            "model": None,
            "parcel_id": parcel_id,
            "observation_count": obs_count,
            "trained": False,
            "error": f"Insufficient observations: {obs_count} < {MIN_OBSERVATIONS}",
        }

    # Reshape for scikit-learn (n_samples, n_features)
    X = elapsed_days.reshape(-1, 1)
    y = ndvi_values.astype(float)

    model = build_model()

    try:
        model.fit(X, y)
        return {
            "model": model,
            "parcel_id": parcel_id,
            "observation_count": obs_count,
            "trained": True,
            "error": None,
        }
    except Exception as exc:
        return {
            "model": None,
            "parcel_id": parcel_id,
            "observation_count": obs_count,
            "trained": False,
            "error": str(exc),
        }


def predict_with_uncertainty(
    model: GaussianProcessRegressor,
    elapsed_days: np.ndarray,
) -> dict[str, np.ndarray]:
    """
    Generate predictions with predictive standard deviation.

    Parameters
    ----------
    model : GaussianProcessRegressor
        A trained GPR model.
    elapsed_days : np.ndarray, shape (m,)
        Elapsed days at which to predict.

    Returns
    -------
    dict with:
        mean : np.ndarray, shape (m,)
            Predicted NDVI values.
        std : np.ndarray, shape (m,)
            Predictive standard deviations (nonnegative).
    """
    X = np.asarray(elapsed_days, dtype=float).reshape(-1, 1)
    mean, std = model.predict(X, return_std=True)
    # Ensure nonnegative (guard against numerical round-off)
    std = np.maximum(std, 0.0)
    return {"mean": mean, "std": std}


def observations_to_training_data(
    observations: np.ndarray,
    timestamps_ns: np.ndarray,
    origin_ns: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert observation timestamps and NDVI values to training data.

    Parameters
    ----------
    observations : np.ndarray, shape (n,)
        NDVI values.
    timestamps_ns : np.ndarray, shape (n,)
        Timestamps in nanoseconds since epoch (UTC).
    origin_ns : int, optional
        Timestamp (nanoseconds since epoch, UTC) used as the zero point for
        elapsed days. If None, the minimum timestamp in ``timestamps_ns`` is
        used (backward-compatible behaviour).

        A trained model must always be evaluated against coordinates measured
        from the SAME origin used at fit time. Passing the training origin for
        held-out observations prevents the origin from being silently reset to
        the held-out subset's own minimum.

    Returns
    -------
    (elapsed_days, ndvi_values) : tuple of np.ndarray
        elapsed_days is float64 days since the chosen origin.
    """
    # Convert nanoseconds to seconds, then to days
    timestamps_s = timestamps_ns.astype(np.float64) / 1e9
    if origin_ns is None:
        origin_s = timestamps_s.min()
    else:
        origin_s = float(origin_ns) / 1e9
    elapsed_days = (timestamps_s - origin_s) / 86400.0
    return elapsed_days, observations.astype(float)
