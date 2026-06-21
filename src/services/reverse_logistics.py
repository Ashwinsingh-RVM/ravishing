"""
Reverse Logistics service — wraps the RL model for use in the Goa DRS Tracker.

Uses a local copy of model.py and config.py in src/services/rl_model/,
with stripped-down data files for deployment.
"""

import json
import os
import sys
from copy import deepcopy

# Add the local rl_model package to path
RL_MODEL_DIR = os.path.join(os.path.dirname(__file__), "rl_model")
if RL_MODEL_DIR not in sys.path:
    sys.path.insert(0, RL_MODEL_DIR)

# Import from the local rl_model package
import config as rl_config
from model import (
    run_model_for_month,
    run_mom_table,
    get_available_months,
    load_horeca_data,
    assign_to_warehouses,
    run_aggregate_sensitivity,
    _return_units_data,
)

DEFAULTS_FILE = os.path.join(RL_MODEL_DIR, "defaults.json")
SENSITIVITY_CACHE_FILE = os.path.join(RL_MODEL_DIR, "sensitivity_cache.json")

# Load sensitivity cache from disk
_SENSITIVITY_CACHE = None
if os.path.exists(SENSITIVITY_CACHE_FILE):
    try:
        with open(SENSITIVITY_CACHE_FILE) as f:
            _SENSITIVITY_CACHE = json.load(f)
    except (json.JSONDecodeError, IOError):
        _SENSITIVITY_CACHE = None


def _snapshot_config():
    """Take a snapshot of all mutable config values for reset after override."""
    return {
        "SCAN_RATE_PER_MIN": rl_config.SCAN_RATE_PER_MIN,
        "AVG_SETUP_TIME_MIN": rl_config.AVG_SETUP_TIME_MIN,
        "ROAD_FACTOR": rl_config.ROAD_FACTOR,
        "AVG_INTER_HORECA_DIST_KM": rl_config.AVG_INTER_HORECA_DIST_KM,
        "LAST_HORECA_TO_WAREHOUSE_KM": rl_config.LAST_HORECA_TO_WAREHOUSE_KM,
        "WAREHOUSE_QUEUE_TIME_MIN": rl_config.WAREHOUSE_QUEUE_TIME_MIN,
        "MAX_TRIPS_PER_DAY": rl_config.MAX_TRIPS_PER_DAY,
        "TOTAL_PICKUP_HOURS": rl_config.TOTAL_PICKUP_HOURS,
        "PEAK_FACTOR": rl_config.PEAK_FACTOR,
        "NORMAL_FACTOR": rl_config.NORMAL_FACTOR,
        "MARKET_GROWTH_YOY": rl_config.MARKET_GROWTH_YOY,
        "HORECA_SHARE_OF_RETURNS": rl_config.HORECA_SHARE_OF_RETURNS,
        "CALIBRATION_REASONABLENESS_THRESHOLD": rl_config.CALIBRATION_REASONABLENESS_THRESHOLD,
        "HORECA_CONSUMPTION_SHARE": dict(rl_config.HORECA_CONSUMPTION_SHARE),
        "WASTE_GENERATION": {k: dict(v) for k, v in rl_config.WASTE_GENERATION.items()},
        "SIZE_MULTIPLIERS": dict(rl_config.SIZE_MULTIPLIERS),
        "FLEET_TYPES": {k: dict(v) for k, v in rl_config.FLEET_TYPES.items()},
        "VOLUMETRIC_FILL_KG_PER_1T": dict(rl_config.VOLUMETRIC_FILL_KG_PER_1T),
        "ROAD_DISTRIBUTION": dict(rl_config.ROAD_DISTRIBUTION),
        "PICKUP_FREQUENCY": dict(rl_config.PICKUP_FREQUENCY),
    }


_CONFIG_SNAPSHOT = _snapshot_config()


def _reset_config():
    """Restore config to original values after an override run."""
    for key, val in _CONFIG_SNAPSHOT.items():
        if isinstance(val, dict) and key in ("HORECA_CONSUMPTION_SHARE", "SIZE_MULTIPLIERS",
                                               "VOLUMETRIC_FILL_KG_PER_1T", "ROAD_DISTRIBUTION",
                                               "PICKUP_FREQUENCY"):
            getattr(rl_config, key).update(val)
        elif isinstance(val, dict) and key in ("WASTE_GENERATION", "FLEET_TYPES"):
            for k, v in val.items():
                getattr(rl_config, key)[k].update(v)
        else:
            setattr(rl_config, key, val)


def _apply_overrides(overrides):
    """Apply UI parameter overrides to config module before model run."""
    mapping = {
        "operational.scan_rate_per_min": ("SCAN_RATE_PER_MIN", float),
        "operational.avg_setup_time_min": ("AVG_SETUP_TIME_MIN", float),
        "operational.road_factor": ("ROAD_FACTOR", float),
        "operational.avg_inter_horeca_dist_km": ("AVG_INTER_HORECA_DIST_KM", float),
        "operational.last_horeca_to_warehouse_km": ("LAST_HORECA_TO_WAREHOUSE_KM", float),
        "operational.warehouse_queue_time_min": ("WAREHOUSE_QUEUE_TIME_MIN", float),
        "operational.max_trips_per_day": ("MAX_TRIPS_PER_DAY", int),
        "operational.total_pickup_hours": ("TOTAL_PICKUP_HOURS", float),
        "seasonality.peak_factor": ("PEAK_FACTOR", float),
        "seasonality.normal_factor": ("NORMAL_FACTOR", float),
        "seasonality.market_growth_yoy": ("MARKET_GROWTH_YOY", float),
        "calibration.horeca_share_of_returns": ("HORECA_SHARE_OF_RETURNS", float),
        "calibration.reasonableness_threshold": ("CALIBRATION_REASONABLENESS_THRESHOLD", float),
    }
    for ui_key, val in overrides.items():
        if ui_key in mapping:
            attr, cast = mapping[ui_key]
            setattr(rl_config, attr, cast(val))
            if attr == "HORECA_SHARE_OF_RETURNS":
                for mat in rl_config.HORECA_CONSUMPTION_SHARE:
                    rl_config.HORECA_CONSUMPTION_SHARE[mat] = float(val)
        elif ui_key.startswith("consumption_shares."):
            mat = ui_key.split(".", 1)[1]
            rl_config.HORECA_CONSUMPTION_SHARE[mat] = float(val)
        elif ui_key.startswith("size_multipliers."):
            tier = ui_key.split(".", 1)[1]
            rl_config.SIZE_MULTIPLIERS[tier] = float(val)
        elif ui_key.startswith("waste_gen."):
            parts = ui_key.split(".")
            htype, field = parts[1], parts[2]
            rl_config.WASTE_GENERATION[htype][field] = float(val)
        elif ui_key.startswith("fleet."):
            parts = ui_key.split(".")
            ft_name, field = parts[1], parts[2]
            if ft_name in rl_config.FLEET_TYPES and field != "suitable_for":
                rl_config.FLEET_TYPES[ft_name][field] = float(val)
        elif ui_key.startswith("volumetric."):
            mat = ui_key.split(".", 1)[1]
            if mat in rl_config.VOLUMETRIC_FILL_KG_PER_1T:
                rl_config.VOLUMETRIC_FILL_KG_PER_1T[mat] = float(val)
        elif ui_key.startswith("road_distribution."):
            road_type = ui_key.split(".", 1)[1]
            if road_type in rl_config.ROAD_DISTRIBUTION:
                rl_config.ROAD_DISTRIBUTION[road_type] = float(val)
        elif ui_key.startswith("pickup_frequency."):
            freq_type = ui_key.split(".", 1)[1]
            if freq_type in rl_config.PICKUP_FREQUENCY:
                rl_config.PICKUP_FREQUENCY[freq_type] = float(val)


def _collect_params(month=None, result=None):
    """Collect all tweakable parameters from config for the UI."""
    params = {
        "operational": {
            "scan_rate_per_min": {"value": rl_config.SCAN_RATE_PER_MIN, "label": "Scan rate (bottles/min)", "min": 5, "max": 60, "step": 1},
            "avg_setup_time_min": {"value": rl_config.AVG_SETUP_TIME_MIN, "label": "Setup time per stop (min)", "min": 1, "max": 10, "step": 0.5},
            "road_factor": {"value": rl_config.ROAD_FACTOR, "label": "Road factor (actual/straight-line)", "min": 1.0, "max": 2.0, "step": 0.1},
            "avg_inter_horeca_dist_km": {"value": rl_config.AVG_INTER_HORECA_DIST_KM, "label": "Avg inter-HoReCa distance (km)", "min": 0.5, "max": 5.0, "step": 0.5},
            "last_horeca_to_warehouse_km": {"value": rl_config.LAST_HORECA_TO_WAREHOUSE_KM, "label": "Last stop -> warehouse (km)", "min": 5, "max": 30, "step": 1},
            "warehouse_queue_time_min": {"value": rl_config.WAREHOUSE_QUEUE_TIME_MIN, "label": "Warehouse queue time (min)", "min": 0, "max": 30, "step": 5},
            "max_trips_per_day": {"value": rl_config.MAX_TRIPS_PER_DAY, "label": "Max trips/day (ceiling)", "min": 1, "max": 4, "step": 1},
            "total_pickup_hours": {"value": rl_config.TOTAL_PICKUP_HOURS, "label": "Total pickup window (hrs)", "min": 4, "max": 12, "step": 0.5},
        },
        "calibration": {
            "horeca_share_of_returns": {"value": rl_config.HORECA_SHARE_OF_RETURNS, "label": "HoReCa share of total returns", "min": 0.10, "max": 0.60, "step": 0.05},
            "reasonableness_threshold": {"value": rl_config.CALIBRATION_REASONABLENESS_THRESHOLD, "label": "Auto-include 'Possible' threshold (btl/day)", "min": 50, "max": 300, "step": 10},
        },
        "fleet": {
            ft_name: {
                "nominal_capacity_kg": ft["nominal_capacity_kg"],
                "daily_cost_inr": ft["daily_cost_inr"],
                "monthly_quotation_inr": ft.get("monthly_quotation_inr", ft["daily_cost_inr"] * 26),
                "working_days": ft.get("working_days", 26),
                "total_km_monthly": ft.get("total_km_monthly", 2600),
                "working_hrs_per_day": ft.get("working_hrs_per_day", 12),
                "extra_km_rate_inr": ft.get("extra_km_rate_inr", 10),
                "extra_hr_rate_inr": ft.get("extra_hr_rate_inr", 100),
                "speed_kmph_urban": ft["speed_kmph_urban"],
                "speed_kmph_highway": ft["speed_kmph_highway"],
                "unloading_time_min": ft["unloading_time_min"],
                "suitable_for": ft["suitable_for"],
            }
            for ft_name, ft in rl_config.FLEET_TYPES.items()
        },
        "volumetric_fill": dict(rl_config.VOLUMETRIC_FILL_KG_PER_1T),
        "road_distribution": dict(rl_config.ROAD_DISTRIBUTION),
        "pickup_frequency": dict(rl_config.PICKUP_FREQUENCY),
        "waste_generation": {
            ht: {"mean": p["mean"], "min": p["min"], "max": p["max"]}
            for ht, p in rl_config.WASTE_GENERATION.items()
        },
        "size_multipliers": dict(rl_config.SIZE_MULTIPLIERS),
        "material_mix": dict(rl_config.HORECA_MATERIAL_MIX),
        "warehouses": {
            name: {"lat": w["lat"], "lon": w["lon"], "region": w["region"], "shed_sqm": w["shed_sqm"]}
            for name, w in rl_config.WAREHOUSES.items()
        },
    }

    # Add PnL data section for month-based runs
    if month and result:
        cal = result.get("calibration", {})
        params["pnl_data"] = {
            "month": month,
            "season": cal.get("season", ""),
            "return_rate": cal.get("return_rate", ""),
            "return_units_cr": cal.get("return_units_cr", {}),
            "daily_weight_kg": cal.get("daily_weight_kg", 0),
            "daily_weight_by_material_kg": cal.get("daily_weight_by_material_kg", {}),
            "horeca_daily_total_units": cal.get("horeca_daily_total", 0),
            "horeca_daily_by_material": cal.get("horeca_daily_by_material", {}),
            "material_mix": cal.get("calibrated_material_mix", {}),
            "avg_weight_g": cal.get("calibrated_avg_weight_g", 0),
            "num_horecas": cal.get("num_horecas", 0),
            "included_possible": cal.get("included_possible", False),
        }

    return params


# ── Public API ──

def rl_get_months():
    """Return available months from PnL CSV with metadata."""
    months = get_available_months()
    if _return_units_data is None:
        return {"months": [], "default": "Oct-27"}

    month_list = []
    for m in months:
        ru = _return_units_data["return_units"].get(m, {})
        total = ru.get("Total", 0)
        season = _return_units_data["seasons"].get(m, "Normal")
        month_list.append({
            "key": m,
            "season": season,
            "total_return_units_cr": round(total, 2),
            "has_data": total > 0,
        })

    default = "Oct-27"
    for m in month_list:
        if m["has_data"] and m["total_return_units_cr"] >= 0.5:
            default = m["key"]
            break

    return {"months": month_list, "default": default}


def rl_run_model(month=None, overrides=None):
    """Run the RL model for a given month, optionally with parameter overrides."""
    if overrides:
        _apply_overrides(overrides)

    try:
        if month:
            result = run_model_for_month(month, skip_sensitivity=True)
        else:
            result = run_model_for_month("Oct-27", skip_sensitivity=True)
    except ValueError as e:
        if overrides:
            _reset_config()
        raise e

    params = _collect_params(month=month, result=result)

    if overrides:
        _reset_config()

    return {"result": result, "params": params}


def rl_get_mom():
    """Return full month-over-month fleet requirement table, applying saved defaults."""
    if os.path.exists(DEFAULTS_FILE):
        with open(DEFAULTS_FILE) as f:
            saved = json.load(f)
        if saved:
            overrides = {}
            pct_keys = ['seasonality.market_growth_yoy', 'calibration.horeca_share_of_returns']
            for key, val in saved.items():
                is_pct_prefix = key.startswith('consumption_shares.') or key.startswith('road_distribution.') or key.startswith('pickup_frequency.')
                if key in pct_keys or is_pct_prefix:
                    overrides[key] = val / 100
                else:
                    overrides[key] = val
            _apply_overrides(overrides)

    try:
        mom_data = run_mom_table()
    finally:
        _reset_config()

    return {"mom": mom_data}


def rl_save_defaults(data):
    """Save parameter defaults to file."""
    global _SENSITIVITY_CACHE
    with open(DEFAULTS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    # Invalidate sensitivity cache
    _SENSITIVITY_CACHE = None
    if os.path.exists(SENSITIVITY_CACHE_FILE):
        os.remove(SENSITIVITY_CACHE_FILE)
    return {"status": "saved"}


def rl_load_defaults():
    """Load saved parameter defaults."""
    if os.path.exists(DEFAULTS_FILE):
        with open(DEFAULTS_FILE) as f:
            return json.load(f)
    return {}


def rl_get_sensitivity(refresh=False):
    """Run aggregate sensitivity analysis. Cached on disk."""
    global _SENSITIVITY_CACHE

    if refresh and os.path.exists(SENSITIVITY_CACHE_FILE):
        os.remove(SENSITIVITY_CACHE_FILE)
        _SENSITIVITY_CACHE = None

    if _SENSITIVITY_CACHE is not None and not refresh:
        return {"sensitivity": _SENSITIVITY_CACHE}

    # Apply saved defaults
    _load_and_apply_saved_defaults()

    try:
        result = run_aggregate_sensitivity()
        _SENSITIVITY_CACHE = result
        with open(SENSITIVITY_CACHE_FILE, "w") as f:
            json.dump(result, f)
        return {"sensitivity": result}
    finally:
        _reset_config()


def _load_and_apply_saved_defaults():
    """Load saved defaults and apply as overrides."""
    if os.path.exists(DEFAULTS_FILE):
        with open(DEFAULTS_FILE) as f:
            saved = json.load(f)
        if saved:
            overrides = {}
            pct_keys = ['seasonality.market_growth_yoy', 'calibration.horeca_share_of_returns']
            for key, val in saved.items():
                is_pct_prefix = key.startswith('consumption_shares.') or key.startswith('road_distribution.') or key.startswith('pickup_frequency.')
                if key in pct_keys or is_pct_prefix:
                    overrides[key] = val / 100
                else:
                    overrides[key] = val
            _apply_overrides(overrides)
