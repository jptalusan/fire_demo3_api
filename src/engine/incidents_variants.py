"""Variant-aware incident generator.

Dispatches on payload['model_kind']:
  - 'weibull_aft'           : direct AFT competing-risks sampler (per cell, slot)
  - 'weibull_aft_thinning'  : Lewis-Shedler thinning sampler (per cell)
  - 'poisson_rate'          : binned Poisson sample, per (cell, hour, dow, month)

Returns a DataFrame with columns:
  incident_id, datetime, cell_id, cluster, slot, incident_type, category, lat, lon
"""
from __future__ import annotations
import functools
import os, sys, pickle, time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from pandas.tseries.holiday import USFederalHolidayCalendar

# Add fire_demo3_api to path so engine imports work
_HERE = Path(__file__).resolve()
_API = _HERE.parents[2]
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from engine.incidents import (
    generate_random_coordinates_in_cell,
    random_incident_selector,
    get_prediction_components,
)

# Bundled artifact location. Default = inside <DATA_DIR>/models/growth_poisson_v1/.
# DATA_DIR is resolved by core.config and honors the DATA_DIR env override so the
# path works both in local dev (project-relative) and in docker (where the
# package lives in site-packages and parents[2] walks up to the wrong place).
# Override the whole bundle dir via GROWTH_V1_DATA_DIR for non-standard layouts.
try:
    from core.config import DATA_DIR as _DATA_DIR  # type: ignore
except Exception:
    _DATA_DIR = _API / "data"
_BUNDLED = Path(_DATA_DIR) / "models" / "growth_poisson_v1"
BUNDLE_DIR = Path(os.environ.get("GROWTH_V1_DATA_DIR", str(_BUNDLED)))


@functools.lru_cache(maxsize=1)
def _type_to_category() -> dict[str, str]:
    """incident_type → NFDResponse Enum (e.g. 'Nine', 'ThreeF') derived from the
    historical apparatus CSV. The C++ simulator routes apparatus based on this
    Enum, so the synthetic generator's hard-coded 'Major' / 'Unknown' values
    would cause the dispatch table lookup to miss. Cached on first call."""
    path = Path(_DATA_DIR) / "incidents_export_apparatus.csv"
    if not path.exists():
        return {}
    hist = pd.read_csv(path, usecols=["incident_type", "category"], low_memory=False)
    hist = hist.dropna(subset=["incident_type", "category"])
    if hist.empty:
        return {}
    return (
        hist.groupby("incident_type")["category"]
            .agg(lambda s: s.mode().iat[0])
            .to_dict()
    )


def remap_categories(df: pd.DataFrame) -> pd.DataFrame:
    """Replace the category column with the canonical NFDResponse Enum keyed
    off incident_type. Rows whose incident_type is unknown keep whatever the
    generator emitted (no-op for empty / missing column)."""
    if df is None or df.empty or "incident_type" not in df.columns:
        return df
    mapping = _type_to_category()
    if not mapping:
        return df
    df = df.copy()
    mapped = df["incident_type"].map(mapping)
    if "category" in df.columns:
        df["category"] = mapped.fillna(df["category"])
    else:
        df["category"] = mapped
    return df


def _bundle_path(name: str) -> Path:
    """Resolve an artifact filename inside the bundle."""
    return BUNDLE_DIR / name


def _load_assets():
    yearly = pd.read_csv(_bundle_path("cell_features_yearly.csv"))
    clustering = pd.read_csv(_bundle_path("clustering_data.csv"))
    # Re-derive 8-cluster labels deterministically (matches training)
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.cluster import KMeans
    Xs = MinMaxScaler().fit_transform(clustering[["log_pop","r_j"]].values)
    clustering["cluster_label"] = KMeans(n_clusters=8, random_state=42, n_init=10).fit_predict(Xs)
    return yearly, clustering[["cell_id","cluster_label"]]


def _build_temporal_features(timestamps: np.ndarray, cat_cols: list[str],
                              holidays_set: set | None = None):
    """Vectorized temporal feature matrix for an array of pd.Timestamps."""
    ts = pd.DatetimeIndex(timestamps)
    h = ts.hour.values; m = ts.month.values; dow = ts.weekday.values
    weekend = (dow >= 5).astype(float)
    is_hol = np.zeros(len(ts), dtype=float)
    if holidays_set is not None and "is_holiday" in cat_cols:
        is_hol = np.array([d.normalize() in holidays_set for d in ts], dtype=float)
    out = np.zeros((len(ts), len(cat_cols)), dtype=float)
    for i, c in enumerate(cat_cols):
        if c == "weekend": out[:, i] = weekend
        elif c == "is_holiday": out[:, i] = is_hol
        elif c == "hour_sin1": out[:, i] = np.sin(2*np.pi*h/24)
        elif c == "hour_cos1": out[:, i] = np.cos(2*np.pi*h/24)
        elif c == "hour_sin2": out[:, i] = np.sin(4*np.pi*h/24)
        elif c == "hour_cos2": out[:, i] = np.cos(4*np.pi*h/24)
        elif c == "month_sin": out[:, i] = np.sin(2*np.pi*(m-1)/12)
        elif c == "month_cos": out[:, i] = np.cos(2*np.pi*(m-1)/12)
        elif c == "hour_x_weekend": out[:, i] = np.sin(2*np.pi*h/24) * weekend
        elif c == "hour_cos_x_weekend": out[:, i] = np.cos(2*np.pi*h/24) * weekend
        elif c.startswith("hour_") and c[5:].isdigit():
            out[:, i] = (h == int(c[5:])).astype(float)
        elif c.startswith("month_") and c[6:].isdigit():
            out[:, i] = (m == int(c[6:])).astype(float)
    return out


def _build_x_full(reg_z: np.ndarray, temporal: np.ndarray) -> np.ndarray:
    """Concat intercept (1) + scaled regs + temporals."""
    n = temporal.shape[0]
    return np.hstack([np.ones((n, 1)), reg_z, temporal])


# -------------------------------------------------------------------
# Weibull AFT direct sampler — vectorized over cells
# -------------------------------------------------------------------

def generate_weibull_aft(payload, start, end, seed=42, sampler="direct"):
    """sampler in {'direct', 'thinning'}."""
    yearly, clustering = _load_assets()
    rng = np.random.default_rng(seed)

    reg_cols = payload["reg_columns"]
    cat_cols = payload["cat_columns"]
    scaler   = payload["scaler"]
    models   = payload["models"]
    top3     = set(payload.get("top3_types", []))

    # Pre-pick yearly features (use start year)
    yr = pd.Timestamp(start).year
    yrly = yearly[yearly["year"] == yr].copy()
    if len(yrly) == 0:
        # fallback to closest year
        yr = yearly["year"].max()
        yrly = yearly[yearly["year"] == yr].copy()
    yrly = yrly.merge(clustering, on="cell_id", how="left")
    yrly = yrly.dropna(subset=["cluster_label"])
    yrly["cluster_label"] = yrly["cluster_label"].astype(int)

    # scale reg cols
    Z = scaler.transform(yrly[reg_cols].values)
    Z = np.clip(Z, -3.0, 3.0)

    # Group cells by cluster
    cells_per_cluster: dict[int, list] = {}
    for i, row in yrly.reset_index(drop=True).iterrows():
        cells_per_cluster.setdefault(int(row["cluster_label"]), []).append((int(row["cell_id"]), i))

    # Reorganize cluster-slot models
    cluster_slots: dict[int, dict[str, dict]] = {}
    for key, m in models.items():
        cl_str, slot = key.split("|", 1)
        cluster_slots.setdefault(int(cl_str), {})[slot] = m

    # Fallback prob dict for "other" slot
    fb = get_prediction_components(incident_type="fire") or {}
    incident_prob_dict = fb.get("incident_probabilities", {})

    rows = []
    incident_id = 5_000_000

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    n_cat = len(cat_cols)

    for cl, cell_list in cells_per_cluster.items():
        cell_models = cluster_slots.get(cl, {})
        if not cell_models:
            continue
        slot_names = list(cell_models.keys())
        # Per cell-row, scaled reg vector
        for cell_id, idx in cell_list:
            reg_z = Z[idx:idx+1]  # (1, p)

            if sampler == "thinning":
                # Compute lambda_max for this cell over 24 hours x 7 dow x 12 month grid
                # lambda(t) = sum over slots of 1/E[T_slot]; with Weibull AFT scale = exp(w.x)
                # mean(T) = scale * Gamma(1+1/k); rate ~ 1/mean.
                from math import gamma
                # build grid of representative timestamps
                grid_ts = pd.date_range(start_ts, start_ts + pd.Timedelta(days=14),
                                        freq="h", inclusive="left")
                cat_grid = _build_temporal_features(np.array(grid_ts, dtype="datetime64[ns]"), cat_cols)
                # broadcast reg_z
                X_grid = _build_x_full(np.tile(reg_z, (len(grid_ts), 1)), cat_grid)
                rate_total = np.zeros(len(grid_ts))
                for slot, m in cell_models.items():
                    w = m["w"].ravel(); k = m["k"]
                    log_scale = np.clip(X_grid @ w, -30, 30)
                    scale = np.exp(log_scale)
                    mean_T = scale * gamma(1.0 + 1.0/k)
                    rate_total += 1.0 / np.maximum(mean_T, 1e-9)
                lam_max = float(rate_total.max()) * 1.2 + 1e-6  # 20% margin

                # Lewis-Shedler thinning
                t = start_ts
                horizon_h = (end_ts - start_ts).total_seconds() / 3600.0
                tau_total = 0.0
                while True:
                    # propose next event
                    u = rng.uniform(1e-12, 1.0)
                    dt_h = -np.log(u) / lam_max
                    tau_total += dt_h
                    if tau_total >= horizon_h:
                        break
                    cand_ts = start_ts + pd.Timedelta(hours=float(tau_total))
                    # compute lambda(cand_ts)
                    cat_t = _build_temporal_features(np.array([cand_ts], dtype="datetime64[ns]"), cat_cols)
                    X_t = _build_x_full(reg_z, cat_t)
                    rate = 0.0
                    contributions = {}
                    for slot, m in cell_models.items():
                        w = m["w"].ravel(); k = m["k"]
                        log_scale = float(np.clip(X_t @ w, -30, 30))
                        scale = float(np.exp(log_scale))
                        mean_T = scale * gamma(1.0 + 1.0/k)
                        contrib = 1.0 / max(mean_T, 1e-9)
                        contributions[slot] = contrib
                        rate += contrib
                    if rng.uniform() < rate / lam_max:
                        # accept; pick winning slot proportional to contribution
                        slots_arr = list(contributions.keys())
                        probs_arr = np.array([contributions[s] for s in slots_arr])
                        probs_arr = probs_arr / probs_arr.sum()
                        slot = rng.choice(slots_arr, p=probs_arr)
                        rows.append(_emit_row(incident_id, cand_ts, int(cell_id), int(cl),
                                              slot, top3,
                                              incident_prob_dict=incident_prob_dict, rng=rng))
                        incident_id += 1

            else:  # sampler == "direct"
                # Loop with per-step temporal feature build
                t = start_ts
                while t < end_ts:
                    cat_t = _build_temporal_features(np.array([t], dtype="datetime64[ns]"), cat_cols)
                    X_t = _build_x_full(reg_z, cat_t)
                    best_T = np.inf; best_slot = None
                    for slot, m in cell_models.items():
                        w = m["w"].ravel(); k = m["k"]
                        log_scale = float(np.clip(X_t @ w, -30, 30))
                        scale = float(np.exp(log_scale))
                        u = rng.uniform(1e-12, 1.0)
                        T_slot = scale * (-np.log(u)) ** (1.0/k)
                        if T_slot < best_T:
                            best_T = T_slot
                            best_slot = slot
                    if best_T == np.inf:
                        break
                    horizon_h = (end_ts - t).total_seconds() / 3600.0
                    if best_T > horizon_h:
                        break
                    t = t + pd.Timedelta(hours=float(best_T))
                    rows.append(_emit_row(incident_id, t, int(cell_id), int(cl), best_slot,
                                          top3,
                                          incident_prob_dict=incident_prob_dict, rng=rng))
                    incident_id += 1

    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values("datetime").reset_index(drop=True)
    return df


def _emit_row(iid, ts, cell_id, cluster, slot, top3, incident_prob_dict, rng,
              lat=None, lon=None):
    if slot in top3:
        category = "Major"; inc_type = slot
    else:
        cat_, sub = random_incident_selector(cluster, incident_prob_dict)
        category = cat_ or "Unknown"
        inc_type = sub or "Other"
    return {
        "incident_id": int(iid),
        "datetime": ts,
        "cell_id": int(cell_id),
        "cluster": int(cluster),
        "slot": slot,
        "incident_type": inc_type,
        "category": category,
        "lat": np.nan if lat is None else lat,
        "lon": np.nan if lon is None else lon,
    }


# -------------------------------------------------------------------
# Poisson rate sampler — bin by (cell, hour, dow, month)
# -------------------------------------------------------------------

def _build_cluster_type_marginal(rng):
    """Cluster -> (types[], probs[]) from precomputed JSON bundle."""
    import json
    path = _bundle_path("cluster_type_marginal.json")
    with open(path) as f:
        raw = json.load(f)
    return {int(cl): (np.array(d["types"]), np.array(d["probs"], dtype=float))
            for cl, d in raw.items()}


def generate_poisson_rate(payload, start, end, seed=42):
    yearly, clustering = _load_assets()
    grid = gpd.read_file(_bundle_path("grid.geojson"))
    rng = np.random.default_rng(seed)
    type_marginal = _build_cluster_type_marginal(rng)

    reg_cols = payload["reg_columns"]
    cat_cols = payload["cat_columns"]
    scaler   = payload["scaler"]
    models   = payload["models"]
    include_holidays = bool(payload.get("include_holidays", False))

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    yr = start_ts.year
    yrly = yearly[yearly["year"] == yr].copy()
    if len(yrly) == 0:
        yr = yearly["year"].max()
        yrly = yearly[yearly["year"] == yr].copy()
    yrly = yrly.merge(clustering, on="cell_id", how="left").dropna(subset=["cluster_label"])
    yrly["cluster_label"] = yrly["cluster_label"].astype(int)

    Z = scaler.transform(yrly[reg_cols].values)
    # Clip extreme Z values to avoid catastrophic eta blow-up on cells whose
    # feature values are far from the per-incident training distribution.
    Z = np.clip(Z, -3.0, 3.0)

    # Build hourly index over horizon
    idx = pd.date_range(start_ts, end_ts, freq="h", inclusive="left")
    n_hours = len(idx)
    h_arr = idx.hour.values
    m_arr = idx.month.values
    dow_arr = idx.weekday.values

    holidays_set = set()
    if include_holidays:
        cal = USFederalHolidayCalendar()
        hols = cal.holidays(start=str(start_ts.date()), end=str((end_ts - pd.Timedelta(days=1)).date()))
        holidays_set = set(pd.DatetimeIndex(hols).normalize())

    # Build temporal feature matrix for ALL hours once
    # We'll vectorize across hours x cells via per-cluster batches
    # First: build cat features for the hourly grid
    temporal_grid = _build_temporal_features(idx.values, cat_cols, holidays_set)  # (H, p_cat)

    fb = get_prediction_components(incident_type="fire") or {}
    incident_prob_dict = fb.get("incident_probabilities", {})

    rows = []
    incident_id = 7_000_000

    # Per-cell: lambda per hour = exp(beta . [1, regs, temporal])
    # Group cells by cluster to vectorize
    cells_idx = yrly.reset_index(drop=True)
    by_cluster: dict[int, list] = {}
    for i, row in cells_idx.iterrows():
        by_cluster.setdefault(int(row["cluster_label"]), []).append(i)

    for cl, cell_idx_list in by_cluster.items():
        beta = models.get(str(int(cl)), {}).get("beta")
        if beta is None:
            continue
        # X for cell c, hour h: [1, Z[c], temporal[h]]  -> for all c x h, can split
        # eta = b0 + beta_reg . Z[c] + beta_temp . temporal[h]
        p_reg = len(reg_cols)
        b0 = beta[0]
        b_reg = beta[1:1+p_reg]
        b_temp = beta[1+p_reg:]

        # Per-cell scalar: b0 + b_reg . Z[c]
        Zc = Z[cell_idx_list]  # (Nc, p_reg)
        per_cell = b0 + Zc @ b_reg  # (Nc,)
        # Per-hour scalar: b_temp . temporal[h]
        per_hour = temporal_grid @ b_temp  # (H,)
        # Combined: lambda[c, h] = exp(per_cell[c] + per_hour[h])  (offset=log(1)=0)
        # broadcast
        eta = per_cell[:, None] + per_hour[None, :]
        np.clip(eta, -30, 30, out=eta)
        lam = np.exp(eta)  # events per cell per hour

        # Sample Poisson per (cell, hour)
        counts = rng.poisson(lam)
        # Place uniformly within each hour
        nz = np.nonzero(counts)
        types_arr, probs_arr = type_marginal.get(int(cl), (np.array(["Other"]), np.array([1.0])))
        for ci, hi in zip(*nz):
            n = int(counts[ci, hi])
            cell_id = int(cells_idx.iloc[cell_idx_list[ci]]["cell_id"])
            offsets_min = rng.uniform(0, 60, size=n)
            inc_types = rng.choice(types_arr, size=n, p=probs_arr)
            for off, it in zip(offsets_min, inc_types):
                ts = idx[hi] + pd.Timedelta(minutes=float(off))
                lat, lon = generate_random_coordinates_in_cell(cell_id, grid)
                rows.append({
                    "incident_id": int(incident_id),
                    "datetime": ts,
                    "cell_id": cell_id,
                    "cluster": int(cl),
                    "slot": "other",
                    "incident_type": str(it),
                    "category": "Major",
                    "lat": lat, "lon": lon,
                })
                incident_id += 1

    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values("datetime").reset_index(drop=True)
    return df


# -------------------------------------------------------------------
# Top-level dispatch
# -------------------------------------------------------------------

def generate(payload: dict, start, end, seed: int = 42) -> pd.DataFrame:
    kind = payload.get("model_kind", "weibull_aft")
    if kind == "weibull_aft":
        return generate_weibull_aft(payload, start, end, seed=seed, sampler="direct")
    if kind == "weibull_aft_thinning":
        return generate_weibull_aft(payload, start, end, seed=seed, sampler="thinning")
    if kind == "poisson_rate":
        return generate_poisson_rate(payload, start, end, seed=seed)
    raise ValueError(f"unknown model_kind: {kind}")


DEFAULT_MODEL_PKL = "growth_poisson_v1.pkl"
_default_payload_cache: dict | None = None
_fire_types_cache: set | None = None


def _load_default_payload() -> dict:
    global _default_payload_cache
    if _default_payload_cache is None:
        path = _bundle_path(DEFAULT_MODEL_PKL)
        if not path.exists():
            raise FileNotFoundError(
                f"default model not found: {path}. "
                "Run survival_model_analysis/scripts/run_variants.py to fit it."
            )
        with open(path, "rb") as f:
            _default_payload_cache = pickle.load(f)
    return _default_payload_cache


def _load_fire_types() -> set:
    """Whitelist of incident_type values that count as 'fire' for filtering."""
    global _fire_types_cache
    if _fire_types_cache is None:
        import json
        path = _bundle_path("fire_incident_types.json")
        if path.exists():
            with open(path) as f:
                _fire_types_cache = set(json.load(f))
        else:
            _fire_types_cache = set()
    return _fire_types_cache


def predict_incidents(start_date, end_date, seed: int = 42,
                      incident_type: str | None = None) -> pd.DataFrame:
    """Default synthetic incident generator.

    Uses growth_poisson_v1: inhomogeneous Poisson rate model with cyclical
    hour/month, weekend flag, and building-class features (highrise-aware).

    incident_type:
        None or 'all'  -> return all generated events (~430/day)
        'fire'         -> filter to fire-only types (~3-5/day, matches NFIRS 100)
        'ems_fire'     -> return all (model is unified across NFIRS categories)
    """
    df = generate(_load_default_payload(), start_date, end_date, seed=seed)
    if incident_type == "fire" and not df.empty:
        fire_types = _load_fire_types()
        df = df[df["incident_type"].isin(fire_types)].reset_index(drop=True)
    return df
