"""
backend/ml/trajectory_diagnostics.py — Day 6C.2A diagnostic utilities

Diagnostic helpers for the per-parcel GPR trajectory models. This module is
EXPERIMENTAL and DIAGNOSTIC ONLY. It does NOT:

- modify the source dataset,
- tune or select models against held-out test observations,
- overwrite the original Day 6C.2 evaluation outputs,
- change compliance verdicts or settlement behavior.

The purpose is to answer one question honestly: are the poor GPR results caused
by an implementation bug, an inappropriate model configuration, or a genuinely
difficult seasonal extrapolation?

Design constraints enforced here:
- Rolling-origin validation uses ONLY the original training period (the earliest
  ~75% of each parcel's observations). The held-out test period is never touched.
- Within every fold, the time origin, scaling, fitting and hyperparameter
  optimization use only observations strictly before the target.
- Candidate configurations are fixed up front and selected before any
  validation result is inspected.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import (
    ConstantKernel,
    ExpSineSquared,
    Matern,
    WhiteKernel,
)

from backend.ml.trajectory_model import build_model

RANDOM_SEED = 42

# Candidate identifiers. The two alternative GPR configurations were chosen
# BEFORE any validation results were inspected (see diagnostic report).
CANDIDATE_PERSISTENCE = "persistence"
CANDIDATE_LINEAR = "linear_trend"
CANDIDATE_GPR_EXISTING = "gpr_existing"
CANDIDATE_GPR_SMOOTH = "gpr_smooth"
CANDIDATE_GPR_PERIODIC = "gpr_periodic"

DEFAULT_CANDIDATES: tuple[str, ...] = (
    CANDIDATE_PERSISTENCE,
    CANDIDATE_LINEAR,
    CANDIDATE_GPR_EXISTING,
    CANDIDATE_GPR_SMOOTH,
    CANDIDATE_GPR_PERIODIC,
)

# Nominal 95% interval z-score (matches the original evaluation).
Z_95 = 1.96

# Minimum number of observations in the fold training window. Kept at 8 so the
# GPR has enough points to optimise three kernel hyperparameters without the
# marginal-likelihood surface collapsing.
MIN_TRAIN_WINDOW = 8


# ---------------------------------------------------------------------------
# Candidate builders
# ---------------------------------------------------------------------------
def build_gpr_smooth() -> GaussianProcessRegressor:
    """Alternative A: smoother Matern kernel + larger noise floor.

    Rationale (chosen before validation): the existing Matern(nu=1.5,
    length_scale=30) is relatively rough and can overfit small noisy samples.
    A smoother kernel (nu=2.5, length_scale=60 days) with a larger WhiteKernel
    floor (0.05) tests whether overfitting / overconfidence is the problem.
    """
    kernel = (
        ConstantKernel(1.0, constant_value_bounds=(1e-3, 1e3))
        * Matern(
            length_scale=60.0,
            length_scale_bounds=(1e-2, 1e3),
            nu=2.5,
        )
        + WhiteKernel(noise_level=0.05, noise_level_bounds=(1e-10, 1e1))
    )
    return GaussianProcessRegressor(
        kernel=kernel,
        normalize_y=True,
        random_state=RANDOM_SEED,
        optimizer="fmin_l_bfgs_b",
        n_restarts_optimizer=1,
    )


def build_gpr_periodic() -> GaussianProcessRegressor:
    """Alternative B: Matern + explicit seasonal (ExpSineSquared) component.

    Rationale (chosen before validation): NDVI is a seasonal signal. Adding an
    ExpSineSquared term with a ~180-day period tests whether the model needs
    explicit seasonal structure to extrapolate across a growing season.
    """
    kernel = (
        ConstantKernel(1.0, constant_value_bounds=(1e-3, 1e3))
        * (
            Matern(
                length_scale=30.0,
                length_scale_bounds=(1e-2, 1e3),
                nu=1.5,
            )
            + ExpSineSquared(
                length_scale=30.0,
                length_scale_bounds=(1e-2, 1e3),
                periodicity=180.0,
                periodicity_bounds=(1e-2, 1e3),
            )
        )
        + WhiteKernel(noise_level=0.01, noise_level_bounds=(1e-10, 1e1))
    )
    return GaussianProcessRegressor(
        kernel=kernel,
        normalize_y=True,
        random_state=RANDOM_SEED,
        optimizer="fmin_l_bfgs_b",
        n_restarts_optimizer=1,
    )


def build_candidate(candidate: str) -> GaussianProcessRegressor | None:
    """Return an *unfitted* model for a candidate, or None for non-GP candidates."""
    if candidate == CANDIDATE_GPR_EXISTING:
        return build_model()  # exact existing configuration
    if candidate == CANDIDATE_GPR_SMOOTH:
        return build_gpr_smooth()
    if candidate == CANDIDATE_GPR_PERIODIC:
        return build_gpr_periodic()
    return None


def is_gpr_candidate(candidate: str) -> bool:
    return candidate in (
        CANDIDATE_GPR_EXISTING,
        CANDIDATE_GPR_SMOOTH,
        CANDIDATE_GPR_PERIODIC,
    )


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
def predict_candidate(
    candidate: str,
    train_elapsed: np.ndarray,
    train_ndvi: np.ndarray,
    target_elapsed: np.ndarray,
) -> tuple[np.ndarray, np.ndarray | None]:
    """
    Fit a candidate on the fold's training window and predict the targets.

    Parameters
    ----------
    candidate : str
        One of the CANDIDATE_* identifiers.
    train_elapsed : np.ndarray, shape (n,)
        Elapsed days for the training window (origin = first training obs).
    train_ndvi : np.ndarray, shape (n,)
        NDVI values for the training window.
    target_elapsed : np.ndarray, shape (m,)
        Elapsed days for the targets, measured from the SAME origin as
        ``train_elapsed``. This is the key correctness property.

    Returns
    -------
    (mean, std) : tuple
        Predicted NDVI means. ``std`` is None for non-GP candidates.
    """
    if candidate == CANDIDATE_PERSISTENCE:
        mean = np.full(len(target_elapsed), float(train_ndvi[-1]))
        return mean, None

    if candidate == CANDIDATE_LINEAR:
        # Least-squares linear trend on the training window only.
        coef = np.polyfit(train_elapsed, train_ndvi, deg=1)
        mean = np.polyval(coef, target_elapsed)
        return mean, None

    model = build_candidate(candidate)
    if model is None:
        raise ValueError(f"Unknown candidate: {candidate!r}")

    X_train = np.asarray(train_elapsed, dtype=float).reshape(-1, 1)
    y_train = np.asarray(train_ndvi, dtype=float)
    X_target = np.asarray(target_elapsed, dtype=float).reshape(-1, 1)
    model.fit(X_train, y_train)
    mean, std = model.predict(X_target, return_std=True)
    return mean, np.maximum(std, 0.0)


# ---------------------------------------------------------------------------
# Rolling-origin validation
# ---------------------------------------------------------------------------
def rolling_origin_validation(
    train_df: pd.DataFrame,
    candidates: Sequence[str] = DEFAULT_CANDIDATES,
    min_train_window: int = MIN_TRAIN_WINDOW,
    horizon: int = 1,
) -> list[dict[str, object]]:
    """
    Time-ordered rolling-origin validation over a single parcel's training period.

    For each fold ``k`` (with ``k`` observations available), the model is fit on
    observations ``[0, k)`` and asked to predict observations
    ``[k, k + horizon)``. The elapsed-day origin is always the first training
    observation of that fold, so target times are never re-zeroed.

    No test observation is required or used.

    Returns
    -------
    list of per-fold, per-candidate dicts with keys:
        parcel_id, fold_train_size, target_time, candidate, prediction,
        predicted_std, actual, abs_error, squared_error, inside_95.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")

    df = train_df.sort_values("_ts").reset_index(drop=True)
    n = len(df)

    ts = df["_ts"].values.astype("datetime64[ns]")
    ndvi = df["ndvi_mean"].values.astype(float)
    parcel_id = str(df["parcel_id"].iloc[0]) if "parcel_id" in df.columns else "parcel"

    rows: list[dict[str, object]] = []

    for fold_end in range(min_train_window, n - horizon + 1):
        fit_ts = ts[:fold_end]
        fit_ndvi = ndvi[:fold_end]
        target_ts = ts[fold_end:fold_end + horizon]
        target_ndvi = ndvi[fold_end:fold_end + horizon]

        origin = fit_ts[0]
        # Target elapsed days use the TRAINING origin (not the target's own min).
        fit_elapsed = (fit_ts - origin) / np.timedelta64(1, "D")
        target_elapsed = (target_ts - origin) / np.timedelta64(1, "D")

        for candidate in candidates:
            mean, std = predict_candidate(
                candidate, fit_elapsed, fit_ndvi, target_elapsed
            )

            for j in range(horizon):
                pred = float(mean[j])
                actual = float(target_ndvi[j])
                std_j = float(std[j]) if std is not None else None
                inside = (
                    None
                    if std_j is None
                    else bool(abs(actual - pred) <= Z_95 * std_j)
                )
                rows.append({
                    "parcel_id": parcel_id,
                    "fold_train_size": int(fold_end),
                    "target_time": pd.Timestamp(target_ts[j]).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "candidate": candidate,
                    "prediction": pred,
                    "predicted_std": std_j,
                    "actual": actual,
                    "abs_error": abs(actual - pred),
                    "squared_error": (actual - pred) ** 2,
                    "inside_95": inside,
                })

    return rows


def aggregate_rolls(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Aggregate per-fold rows into per-candidate (pooled and per-parcel) metrics."""
    if not rows:
        return []

    df = pd.DataFrame(rows)
    out: list[dict[str, object]] = []

    groups: list[tuple[str, pd.DataFrame]] = [
        ("__all__", df),
    ]
    for pid in sorted(df["parcel_id"].unique()):
        groups.append((str(pid), df[df["parcel_id"] == pid]))

    for scope, group in groups:
        for candidate, cand_df in group.groupby("candidate"):
            errors = cand_df["abs_error"].to_numpy(dtype=float)
            sq = cand_df["squared_error"].to_numpy(dtype=float)
            std_vals = cand_df["predicted_std"].dropna().to_numpy(dtype=float)
            inside = cand_df["inside_95"].dropna().astype(bool).to_numpy()

            out.append({
                "scope": scope,
                "candidate": candidate,
                "n_folds": int(len(cand_df)),
                "mae": float(np.mean(errors)) if len(errors) else float("nan"),
                "rmse": float(np.sqrt(np.mean(sq))) if len(sq) else float("nan"),
                "mean_predicted_std": (
                    float(np.mean(std_vals)) if len(std_vals) else float("nan")
                ),
                "coverage_95": (
                    float(np.mean(inside)) if len(inside) else float("nan")
                ),
            })

    return out


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------
def original_train_test_split(
    parcel_df: pd.DataFrame,
    train_fraction: float = 0.75,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Reproduce the original chronological split (first ~75% train, rest test).

    Returns train and test frames. The test frame is returned ONLY so the audit
    can measure the feature-alignment mismatch; it is never used for fitting.
    """
    df = parcel_df.sort_values("_ts").reset_index(drop=True)
    n = len(df)
    split_idx = int(np.floor(n * train_fraction))
    split_idx = max(split_idx, 1)
    split_idx = min(split_idx, n - 1)
    return df.iloc[:split_idx].reset_index(drop=True), df.iloc[split_idx:].reset_index(drop=True)


def elapsed_days_from_origin(
    timestamps_ns: np.ndarray,
    origin_ns: int,
) -> np.ndarray:
    """Elapsed days relative to a fixed origin (no re-zeroing)."""
    ts_s = np.asarray(timestamps_ns, dtype=np.float64) / 1e9
    origin_s = float(origin_ns) / 1e9
    return (ts_s - origin_s) / 86400.0


def fitted_kernel_summary(model: GaussianProcessRegressor) -> dict[str, object]:
    """Extract readable hyperparameters from a fitted sklearn GPR model."""
    kernel = model.kernel_
    summary: dict[str, object] = {"kernel_str": str(kernel)}

    constant = getattr(kernel, "k1", None)
    if constant is not None and hasattr(constant, "constant_value"):
        summary["constant_value"] = float(constant.constant_value)

    # Walk the kernel tree and collect Matern / WhiteKernel / ExpSineSquared.
    def _walk(node: object, prefix: str = "") -> None:
        cls = type(node).__name__
        if cls == "Matern":
            summary[f"{prefix}matern_length_scale"] = float(node.length_scale)
            summary[f"{prefix}matern_nu"] = float(node.nu)
        elif cls == "WhiteKernel":
            summary[f"{prefix}white_noise_level"] = float(node.noise_level)
        elif cls == "ExpSineSquared":
            summary[f"{prefix}exp_sine_length_scale"] = float(node.length_scale)
            summary[f"{prefix}exp_sine_periodicity"] = float(node.periodicity)

        for attr in ("k1", "k2"):
            child = getattr(node, attr, None)
            if child is not None:
                _walk(child, prefix + attr + ".")

    _walk(kernel)

    # y normalization statistics
    if getattr(model, "normalize_y", False):
        summary["y_train_mean"] = float(model._y_train_mean)
        summary["y_train_std"] = float(model._y_train_std)

    return summary
