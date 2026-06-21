#!/usr/bin/env python3
"""
Goa DRS Reverse Logistics — Fleet Estimation Model
Estimates truck requirements (fleet type, capacity, numbers) per warehouse cluster.

Two modes:
  1. Month-based (PRIMARY): Uses actual DRS Return Units from PnL CSV for a specific month.
  2. Scenario-based (LEGACY): PTM-calibrated flow using conservative/base/aggressive scenarios.

Usage:
    python3 model.py                        # Run month-based for Oct-27
    python3 model.py --month Oct-27         # Run specific month
    python3 model.py --scenario base        # Run legacy scenario
    python3 model.py --mom                  # Run full MoM table
    python3 model.py --all                  # Run all scenarios + sensitivity
"""

import csv
import json
import math
import os
import sys
from collections import defaultdict
from copy import deepcopy

# Add parent to path for config import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
import config as _cfg  # For runtime reads of overridden scalars


# ─────────────────────────────────────────────────────────────
# CSV UTILITY — Shared row reader
# ─────────────────────────────────────────────────────────────

def _read_csv_rows(csv_path=None):
    """Read CSV rows and return (rows, header, season_row) or None."""
    path = csv_path or PNL_CSV_PATH
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[2]       # Row 3: month names (Apr-26, May-26, ...)
    season_row = rows[1]   # Row 2: Normal/Peak labels
    return rows, header, season_row


_MATERIAL_MAP = {
    "PET": "PET", "HDPE": "HDPE", "MLP": "MLP",
    "Glass": "Glass", "AL Cans": "AL Cans",
    "Tetra Pack": "Tetra Pack", "LD": "LD",
}


def _parse_month_str(month_str):
    """Convert 'Jun-26' to (month_number, year_2digit) or (None, None)."""
    parts = month_str.strip().split("-")
    if len(parts) != 2:
        return None, None
    mon_name, yr_short = parts[0], parts[1]
    month_names = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                   "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    mon = month_names.get(mon_name)
    if mon is None:
        return None, None
    return mon, int(yr_short)


def _month_to_fy(month_str):
    """Convert 'Jun-26' to ('FY27', 6)"""
    mon, yr_short = _parse_month_str(month_str)
    if mon is None:
        return None, None
    yr = 2000 + yr_short
    fy_year = yr + 1 if mon >= 4 else yr
    return f"FY{fy_year % 100}", mon


# ─────────────────────────────────────────────────────────────
# PNL CSV READER — Load PTM data from exported Google Sheet
# ─────────────────────────────────────────────────────────────

def load_ptm_from_csv(csv_path=None):
    """
    Parse PnL MoM CSV to extract DRS Put to Market data by FY/period/material.
    Returns dict matching PUT_TO_MARKET format, or None if CSV not found.
    """
    result = _read_csv_rows(csv_path)
    if result is None:
        return None
    rows, header, season_row = result

    # Find "DRS Put to Market (Cr)" section — row with that label in column 6
    ptm_start = None
    for i, row in enumerate(rows):
        if len(row) > 6 and "DRS Put to Market" in row[6]:
            ptm_start = i
            break

    if ptm_start is None:
        return None

    # Parse material rows (ptm_start+1 = Total, then +2..+8 = materials)
    ptm_data = {}
    for row_offset in range(1, 9):  # Total + 7 materials
        row = rows[ptm_start + row_offset]
        if len(row) < 8:
            continue
        label = row[6].strip()

        # Find material name
        mat_name = None
        for key in _MATERIAL_MAP:
            if key in label:
                mat_name = _MATERIAL_MAP[key]
                break
        if mat_name is None and "Total" not in label:
            continue

        # Parse monthly values
        for col_idx in range(7, min(len(row), len(header))):
            month_str = header[col_idx].strip() if col_idx < len(header) else ""
            fy, mon = _month_to_fy(month_str)
            if fy is None:
                continue

            season = season_row[col_idx].strip() if col_idx < len(season_row) else ""
            period = "peak" if season == "Peak" else "normal"

            try:
                val = float(row[col_idx]) if row[col_idx].strip() else 0.0
            except ValueError:
                val = 0.0

            if mat_name and mat_name != "Total":
                if fy not in ptm_data:
                    ptm_data[fy] = {"normal": {}, "peak": {}}
                # Keep the latest value per FY/period/material (they repeat monthly)
                ptm_data[fy][period][mat_name] = val

    return ptm_data if ptm_data else None


# ─────────────────────────────────────────────────────────────
# PNL CSV READER — DRS Return Units by month (PRIMARY DATA SOURCE)
# ─────────────────────────────────────────────────────────────

def load_return_units_from_csv(csv_path=None):
    """
    Parse PnL MoM CSV to extract DRS Return Units (Cr) per month per material.

    Returns:
        {
            "months": ["Apr-26", "May-26", ..., "Mar-31"],
            "seasons": {"Apr-26": "Normal", "May-26": "Normal", "Oct-26": "Peak", ...},
            "return_units": {
                "Apr-26": {"Total": 0.0, "PET": 0.0, "HDPE": 0.0, ...},
                "May-26": {...},
                ...
            },
            "return_rates": {
                "Apr-26": {"Total": "0%", "PET": "", ...},
                ...
            }
        }
    """
    result = _read_csv_rows(csv_path)
    if result is None:
        return None
    rows, header, season_row = result

    # Find "DRS Return Units (Cr)" section
    ru_start = None
    for i, row in enumerate(rows):
        if len(row) > 6 and "DRS Return Units" in row[6]:
            ru_start = i
            break

    if ru_start is None:
        return None

    # Find "Return%" section for return rates
    rr_start = None
    for i, row in enumerate(rows):
        if len(row) > 6 and "Return%" in row[6]:
            rr_start = i
            break

    # Build month list from header (columns 7+)
    months = []
    seasons = {}
    for col_idx in range(7, len(header)):
        month_str = header[col_idx].strip()
        if not month_str:
            continue
        mon, yr = _parse_month_str(month_str)
        if mon is None:
            continue
        months.append(month_str)
        season = season_row[col_idx].strip() if col_idx < len(season_row) else "Normal"
        seasons[month_str] = season if season in ("Normal", "Peak") else "Normal"

    # Parse return units: Total (row ru_start+1) + 7 materials (rows +2..+8)
    return_units = {m: {} for m in months}
    for row_offset in range(1, 9):
        row = rows[ru_start + row_offset]
        if len(row) < 8:
            continue
        label = row[6].strip()

        mat_name = None
        if "Total" in label:
            mat_name = "Total"
        else:
            for key in _MATERIAL_MAP:
                if key in label:
                    mat_name = _MATERIAL_MAP[key]
                    break
        if mat_name is None:
            continue

        for col_idx in range(7, min(len(row), len(header))):
            month_str = header[col_idx].strip()
            if month_str not in return_units:
                continue
            try:
                val = float(row[col_idx]) if row[col_idx].strip() else 0.0
            except ValueError:
                val = 0.0
            return_units[month_str][mat_name] = val

    # Parse return rates if available
    return_rates = {m: {} for m in months}
    if rr_start is not None:
        for row_offset in range(1, 9):
            if rr_start + row_offset >= len(rows):
                break
            row = rows[rr_start + row_offset]
            if len(row) < 8:
                continue
            label = row[6].strip()

            mat_name = None
            if "Total" in label:
                mat_name = "Total"
            else:
                for key in _MATERIAL_MAP:
                    if key in label:
                        mat_name = _MATERIAL_MAP[key]
                        break
            if mat_name is None:
                continue

            for col_idx in range(7, min(len(row), len(header))):
                month_str = header[col_idx].strip()
                if month_str not in return_rates:
                    continue
                return_rates[month_str][mat_name] = row[col_idx].strip() if row[col_idx].strip() else "0%"

    return {
        "months": months,
        "seasons": seasons,
        "return_units": return_units,
        "return_rates": return_rates,
    }


# Try to load PTM from CSV at module init
_csv_ptm = load_ptm_from_csv()
if _csv_ptm:
    PUT_TO_MARKET.update(_csv_ptm)
    print(f"[model] Loaded PTM data from PnL CSV ({len(_csv_ptm)} fiscal years)")
else:
    print("[model] Using hardcoded PTM data (no PnL CSV found)")

# Load return units data at module init
_return_units_data = load_return_units_from_csv()
if _return_units_data:
    print(f"[model] Loaded DRS Return Units for {len(_return_units_data['months'])} months")
else:
    print("[model] WARNING: Could not load DRS Return Units from CSV")

# ─────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────

HORECA_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "horeca_slim.json"
)

def load_horeca_data(include_possible=False):
    """Load and filter HoReCa data for reverse logistics.

    FY27 scope (alcohol-only):
    - Always include: Confirmed + Likely + Inferred (all types)
    - From 'Possible': only Restaurants, Hotels & Beach Shacks (these are
      establishments that likely serve alcohol but lack explicit Google signals)
    - Exclude: Possible Resorts (too few to matter),
      Unknown (Lodging, Homestays, Cafes, Guesthouses — no alcohol relevance)
    """
    with open(HORECA_DATA_PATH) as f:
        all_data = json.load(f)

    # Core alcohol-serving signals — always included regardless of type
    core_signals = list(ALCOHOL_SIGNALS_INCLUDE)  # Confirmed, Likely, Inferred

    filtered = []
    for r in all_data:
        if str(r.get("Is_Active", "")).upper() != "TRUE":
            continue
        if str(r.get("Is_Duplicate", "")).upper() == "TRUE":
            continue
        if not r.get("Latitude") or not r.get("Longitude"):
            continue

        signal = r.get("Alcohol_Signal")
        htype = r.get("HoReCa_Type", "Unknown")

        if signal in core_signals:
            filtered.append(r)
        elif signal == "Possible" and htype in ("Restaurant", "Hotel", "Beach Shack"):
            filtered.append(r)

    print(f"  Loaded {len(all_data)} total HoReCas")
    print(f"  Filtered to {len(filtered)} alcohol-serving HoReCas")
    print(f"    Core (Confirmed+Likely+Inferred): all types")
    print(f"    Possible: Restaurants, Hotels & Beach Shacks only")
    return filtered


# ─────────────────────────────────────────────────────────────
# DISTANCE & CLUSTERING
# ─────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    """Haversine distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(float(lat2) - float(lat1))
    dlon = math.radians(float(lon2) - float(lon1))
    a = math.sin(dlat/2)**2 + math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def assign_to_warehouses(horecas):
    """Assign each HoReCa to nearest warehouse. Returns dict: warehouse_name → [horecas]."""
    clusters = defaultdict(list)
    for h in horecas:
        hlat, hlon = float(h["Latitude"]), float(h["Longitude"])
        best_wh = None
        best_dist = float("inf")
        for wh_name, wh in WAREHOUSES.items():
            d = haversine_km(hlat, hlon, wh["lat"], wh["lon"])
            if d < best_dist:
                best_dist = d
                best_wh = wh_name
        h["assigned_warehouse"] = best_wh
        h["distance_to_warehouse_km"] = round(best_dist * _cfg.ROAD_FACTOR, 2)
        clusters[best_wh].append(h)

    return clusters


# ─────────────────────────────────────────────────────────────
# PTM CALIBRATION
# ─────────────────────────────────────────────────────────────

def calibrate_from_ptm(horecas, year="FY28", period="normal", percentile=50):
    """
    Top-down calibration using PnL Put-to-Market data.

    Flow:
      PTM (Cr/month) → daily units → HoReCa consumption share → total at HoReCa
      Compare with bottom-up sum → calibration_factor scales all estimates to match.

    Returns dict with calibration data including per-type calibrated waste gen.
    """
    ptm = PUT_TO_MARKET[year][period]

    # Step 1: Daily containers at HoReCa by material
    horeca_daily_by_mat = {}
    for mat in MATERIALS:
        ptm_monthly_cr = ptm.get(mat, 0)
        ptm_daily = ptm_monthly_cr * 1e7 / 30  # Cr/month → units/day
        share = HORECA_CONSUMPTION_SHARE.get(mat, 0.05)
        horeca_daily_by_mat[mat] = ptm_daily * share

    horeca_daily_total = sum(horeca_daily_by_mat.values())

    # Step 2: Bottom-up total (uncalibrated, using relative WASTE_GENERATION weights)
    bottom_up_total = sum(estimate_daily_waste(h, percentile) for h in horecas)

    # Step 3: Calibration factor
    cal_factor = horeca_daily_total / bottom_up_total if bottom_up_total > 0 else 1.0
    avg_per_horeca = horeca_daily_total / len(horecas) if horecas else 0

    # Step 4: Calibrated per-type waste generation (derived, read-only)
    calibrated_waste_gen = {}
    for htype, params in WASTE_GENERATION.items():
        calibrated_waste_gen[htype] = {
            "mean": round(params["mean"] * cal_factor, 1),
            "min": round(params["min"] * cal_factor, 1),
            "max": round(params["max"] * cal_factor, 1),
            "original_mean": params["mean"],
        }

    # Step 5: Calibrated material mix at HoReCa (derived from PTM shares)
    calibrated_material_mix = {}
    for mat in MATERIALS:
        calibrated_material_mix[mat] = round(
            horeca_daily_by_mat[mat] / horeca_daily_total, 4
        ) if horeca_daily_total > 0 else 0

    # Step 6: Calibrated average bottle weight
    cal_avg_weight_g = sum(
        calibrated_material_mix.get(mat, 0) * MATERIALS[mat]["weight_g"]
        for mat in MATERIALS
    )

    # PTM totals for display
    ptm_total_cr = sum(ptm.get(mat, 0) for mat in MATERIALS)
    horeca_total_cr = sum(
        ptm.get(mat, 0) * HORECA_CONSUMPTION_SHARE.get(mat, 0.05) for mat in MATERIALS
    )

    return {
        "calibration_factor": round(cal_factor, 3),
        "horeca_daily_total": round(horeca_daily_total),
        "bottom_up_total": round(bottom_up_total),
        "avg_per_horeca": round(avg_per_horeca, 1),
        "num_horecas": len(horecas),
        "calibrated_waste_gen": calibrated_waste_gen,
        "calibrated_material_mix": calibrated_material_mix,
        "original_material_mix": dict(HORECA_MATERIAL_MIX),
        "calibrated_avg_weight_g": round(cal_avg_weight_g, 1),
        "original_avg_weight_g": round(AVG_BOTTLE_WEIGHT_G, 1),
        "horeca_daily_by_material": {k: round(v) for k, v in horeca_daily_by_mat.items()},
        "ptm_year": year,
        "ptm_period": period,
        "ptm_total_cr_month": round(ptm_total_cr, 1),
        "horeca_total_cr_month": round(horeca_total_cr, 2),
        "ptm_by_material": {mat: ptm.get(mat, 0) for mat in MATERIALS},
        "consumption_shares": dict(HORECA_CONSUMPTION_SHARE),
        "included_possible": False,  # updated by caller if needed
    }


# ─────────────────────────────────────────────────────────────
# WASTE GENERATION ESTIMATION (PTM-calibrated)
# ─────────────────────────────────────────────────────────────

def estimate_daily_waste(horeca, percentile=50, calibration_factor=1.0):
    """Estimate daily bottles generated by a single HoReCa (calibrated)."""
    htype = horeca.get("HoReCa_Type", "Other")
    size = horeca.get("Size_Tier", "Unknown")

    waste_params = WASTE_GENERATION.get(htype, WASTE_GENERATION["Other"])
    size_mult = SIZE_MULTIPLIERS.get(size, 0.5)

    if percentile <= 25:
        base = waste_params["min"] + (waste_params["mean"] - waste_params["min"]) * 0.25
    elif percentile >= 75:
        base = waste_params["mean"] + (waste_params["max"] - waste_params["mean"]) * 0.5
    else:
        base = waste_params["mean"]

    return base * size_mult * calibration_factor


def estimate_pickup_bottles(horeca, percentile=50, calibration_factor=1.0, avg_weight_g=None):
    """Estimate bottles to pick up per visit (accounts for frequency accumulation).

    NOTE: Frequency is assigned later in get_daily_pickup_schedule() using
    PICKUP_FREQUENCY config distribution. This function only computes daily waste.
    """
    if avg_weight_g is None:
        avg_weight_g = AVG_BOTTLE_WEIGHT_G

    daily = estimate_daily_waste(horeca, percentile, calibration_factor)
    horeca["daily_bottles"] = round(daily, 1)

    return daily


def get_daily_pickup_schedule(clusters, percentile=50, calibration_factor=1.0, avg_weight_g=None):
    """
    For each warehouse, calculate how many HoReCas need pickup on any given day
    and the total weight to collect.

    Pickup frequency is assigned using PICKUP_FREQUENCY from config:
    - HoReCas are sorted by daily volume (highest first)
    - Top N% get "daily", next N% get "alternate", etc. per config distribution
    - This way, high-volume establishments get more frequent pickups
    """
    if avg_weight_g is None:
        avg_weight_g = AVG_BOTTLE_WEIGHT_G

    accum_map = {"daily": 1, "alternate": 2, "twice_weekly": 3.5, "weekly": 7}
    prob_map = {"daily": 1.0, "alternate": 0.5, "twice_weekly": 2/7, "weekly": 1/7}

    schedule = {}
    for wh_name, horecas in clusters.items():
        # Step 1: Compute daily waste for each HoReCa
        for h in horecas:
            estimate_pickup_bottles(h, percentile, calibration_factor, avg_weight_g)

        # Step 2: Sort by daily volume (highest first) and assign frequency buckets
        sorted_horecas = sorted(horecas, key=lambda h: h.get("daily_bottles", 0), reverse=True)
        n = len(sorted_horecas)

        # Build frequency buckets from PICKUP_FREQUENCY config
        # Order: daily (highest volume) → alternate → twice_weekly → weekly (lowest volume)
        freq_order = ["daily", "alternate", "twice_weekly", "weekly"]
        boundaries = []
        cumulative = 0
        for fq in freq_order:
            pct = PICKUP_FREQUENCY.get(fq, 0)
            cumulative += pct
            boundaries.append((fq, int(round(cumulative * n))))

        idx = 0
        for fq, end_idx in boundaries:
            for h in sorted_horecas[idx:end_idx]:
                h["pickup_frequency"] = fq
                h["bottles_per_visit"] = round(h["daily_bottles"] * accum_map[fq], 1)
                h["weight_per_visit_kg"] = round(h["bottles_per_visit"] * avg_weight_g / 1000, 2)
                h["daily_pickup_prob"] = prob_map[fq]
            idx = end_idx
        # Any remaining (rounding edge case) → weekly
        for h in sorted_horecas[idx:]:
            h["pickup_frequency"] = "weekly"
            h["bottles_per_visit"] = round(h["daily_bottles"] * accum_map["weekly"], 1)
            h["weight_per_visit_kg"] = round(h["bottles_per_visit"] * avg_weight_g / 1000, 2)
            h["daily_pickup_prob"] = prob_map["weekly"]

        # Step 3: Compute schedule totals
        daily_weight_kg = 0
        daily_bottles = 0

        for h in horecas:
            daily_weight_kg += h["weight_per_visit_kg"] * h["daily_pickup_prob"]
            daily_bottles += h["bottles_per_visit"] * h["daily_pickup_prob"]

        freq_dist = defaultdict(int)
        for h in horecas:
            freq_dist[h["pickup_frequency"]] += 1

        schedule[wh_name] = {
            "total_horecas": len(horecas),
            "expected_daily_pickups": round(sum(h["daily_pickup_prob"] for h in horecas)),
            "expected_daily_weight_kg": round(daily_weight_kg, 1),
            "expected_daily_bottles": round(daily_bottles),
            "frequency_distribution": dict(freq_dist),
            "horecas": horecas,
        }

    return schedule


# ─────────────────────────────────────────────────────────────
# ROUTE TIME ESTIMATION
# ─────────────────────────────────────────────────────────────

def estimate_time_per_horeca(horeca):
    """Time spent at a single HoReCa (scanning + setup), in minutes."""
    bottles = horeca.get("bottles_per_visit", 20)
    scan_time = bottles / _cfg.SCAN_RATE_PER_MIN
    return _cfg.AVG_SETUP_TIME_MIN + scan_time


def estimate_trip_time(fleet_type, num_stops, horecas_in_trip, wh_name):
    """
    Estimate total time for one trip:
    warehouse → HoReCa1 → HoReCa2 → ... → warehouse
    Returns time in minutes.
    """
    ft = FLEET_TYPES[fleet_type]

    avg_to_first_km = 8
    travel_to_first = (avg_to_first_km / ft["speed_kmph_urban"]) * 60

    inter_travel = (num_stops - 1) * (_cfg.AVG_INTER_HORECA_DIST_KM / ft["speed_kmph_urban"]) * 60

    service_time = sum(estimate_time_per_horeca(h) for h in horecas_in_trip)

    if horecas_in_trip:
        last_h = horecas_in_trip[-1]
        return_dist = last_h.get("distance_to_warehouse_km", _cfg.LAST_HORECA_TO_WAREHOUSE_KM)
    else:
        return_dist = _cfg.LAST_HORECA_TO_WAREHOUSE_KM
    avg_return_speed = (ft["speed_kmph_urban"] + ft["speed_kmph_highway"]) / 2
    travel_return = (return_dist / avg_return_speed) * 60

    warehouse_time = _cfg.WAREHOUSE_QUEUE_TIME_MIN + ft["unloading_time_min"]

    total = travel_to_first + inter_travel + service_time + travel_return + warehouse_time
    return round(total, 1)


# ─────────────────────────────────────────────────────────────
# FLEET REQUIREMENT CALCULATION
# ─────────────────────────────────────────────────────────────

def _compute_volumetric_weight(actual_weight_kg, material_mix):
    """Compute volumetric weight using per-material fill factors.

    Volumetric factor for each material = 1000 / VOLUMETRIC_FILL_KG_PER_1T[mat]
    Volumetric weight = sum(actual_weight_kg * mix_pct * vol_factor for each material)

    This means: if the truck were filled with ONLY glass, 700kg actual = 1000kg volumetric.
    A mixed load uses weighted average of volumetric factors.
    """
    if not material_mix or actual_weight_kg <= 0:
        return actual_weight_kg

    vol_weight = 0
    for mat, pct in material_mix.items():
        fill_kg = VOLUMETRIC_FILL_KG_PER_1T.get(mat, 1000)  # default: no volumetric penalty
        vol_factor = 1000.0 / fill_kg
        vol_weight += actual_weight_kg * pct * vol_factor

    return vol_weight


def calculate_fleet_for_warehouse(wh_name, schedule_data, return_rate_multiplier=1.0, material_mix=None):
    """Calculate fleet requirements for a single warehouse.

    Uses volumetric weight to determine truck capacity utilization:
    truck is full when sum of volumetric weights >= nominal_capacity_kg.
    """
    horecas = schedule_data["horecas"]
    daily_weight = schedule_data["expected_daily_weight_kg"] * return_rate_multiplier
    daily_pickups = schedule_data["expected_daily_pickups"]
    total_available_min = _cfg.TOTAL_PICKUP_HOURS * 60

    # Compute volumetric factor: how much "space" 1 kg of mixed material takes
    # If material_mix is provided, use volumetric weight; otherwise use actual weight
    if material_mix:
        daily_vol_weight = _compute_volumetric_weight(daily_weight, material_mix)
        vol_factor = daily_vol_weight / daily_weight if daily_weight > 0 else 1.0
    else:
        vol_factor = 1.0
        daily_vol_weight = daily_weight

    results = {}

    for fleet_name, ft in FLEET_TYPES.items():
        capacity = ft["nominal_capacity_kg"]

        if daily_pickups == 0:
            results[fleet_name] = {"trips_needed": 0, "vehicles_needed": 0, "stops_per_trip": 0}
            continue

        # Volumetric weight per stop — this is what fills the truck
        avg_vol_weight_per_stop = daily_vol_weight / daily_pickups if daily_pickups > 0 else 0
        stops_by_weight = int(capacity / avg_vol_weight_per_stop) if avg_vol_weight_per_stop > 0 else 0
        stops_by_weight = max(1, min(stops_by_weight, daily_pickups))

        # Time-based cap: how many stops fit in one trip given the pickup window?
        # Travel to first HoReCa (truck departs early) and return leg (last HoReCa → WH
        # + queue + unload) both happen OUTSIDE the pickup window.
        # The full pickup window is available for collection stops.
        avg_bottles_per_stop = daily_weight / (daily_pickups * (AVG_BOTTLE_WEIGHT_G / 1000)) if daily_pickups > 0 and AVG_BOTTLE_WEIGHT_G > 0 else 20
        avg_service_time = _cfg.AVG_SETUP_TIME_MIN + avg_bottles_per_stop / _cfg.SCAN_RATE_PER_MIN
        time_per_stop = avg_service_time + (_cfg.AVG_INTER_HORECA_DIST_KM / ft["speed_kmph_urban"]) * 60
        available_for_stops = _cfg.TOTAL_PICKUP_HOURS * 60
        max_stops_by_time = max(1, int(available_for_stops / time_per_stop)) if time_per_stop > 0 else stops_by_weight

        stops_per_trip = min(stops_by_weight, max_stops_by_time, daily_pickups)
        stops_per_trip = max(1, stops_per_trip)

        sample_horecas = horecas[:stops_per_trip]
        trip_time = estimate_trip_time(fleet_name, stops_per_trip, sample_horecas, wh_name)

        total_trips = math.ceil(daily_pickups / stops_per_trip) if stops_per_trip > 0 else 0

        # 1 trip per vehicle — the pickup window is fully consumed by one trip's pickups.
        # The return leg happens after the window closes.
        vehicles = total_trips
        trips_per_vehicle = 1
        daily_cost = vehicles * ft["daily_cost_inr"]

        # Actual weight per trip (for reporting)
        avg_actual_weight_per_stop = daily_weight / daily_pickups if daily_pickups > 0 else 0
        actual_weight_per_trip = avg_actual_weight_per_stop * stops_per_trip
        vol_weight_per_trip = avg_vol_weight_per_stop * stops_per_trip
        utilization = vol_weight_per_trip / capacity if capacity > 0 else 0

        results[fleet_name] = {
            "vehicles_needed": vehicles,
            "trips_per_vehicle": trips_per_vehicle,
            "stops_per_trip": stops_per_trip,
            "total_trips": total_trips,
            "trip_time_min": trip_time,
            "weight_per_trip_kg": round(actual_weight_per_trip, 1),
            "vol_weight_per_trip_kg": round(vol_weight_per_trip, 1),
            "utilization_pct": round(utilization * 100, 1),
            "daily_cost_inr": daily_cost,
            "suitable_for": ft["suitable_for"],
        }

    return results


def recommend_fleet_mix(wh_name, fleet_results, schedule_data):
    """Recommend optimal fleet mix considering road constraints and cost.

    Uses ROAD_DISTRIBUTION from config (editable in UI):
      - narrow_streets → Tata Ace + Bolero Pickup (split evenly)
      - medium_streets → Intra V50
      - main_roads → Intra V70
    """
    narrow_street_pct = ROAD_DISTRIBUTION.get("narrow_streets", 0.30)
    medium_street_pct = ROAD_DISTRIBUTION.get("medium_streets", 0.45)
    main_road_pct = ROAD_DISTRIBUTION.get("main_roads", 0.25)

    daily_pickups = schedule_data["expected_daily_pickups"]

    narrow_pickups = int(daily_pickups * narrow_street_pct)
    medium_pickups = int(daily_pickups * medium_street_pct)
    main_pickups = daily_pickups - narrow_pickups - medium_pickups

    recommendation = {}

    # Narrow streets: split between Tata Ace and Bolero Pickup
    ace_pickups = narrow_pickups // 2
    bolero_pickups = narrow_pickups - ace_pickups

    if ace_pickups > 0 and "Tata Ace" in fleet_results:
        fr = fleet_results["Tata Ace"]
        trips = math.ceil(ace_pickups / max(1, fr["stops_per_trip"]))
        vehicles = math.ceil(trips / max(1, fr["trips_per_vehicle"]))
        recommendation["Tata Ace"] = {
            "vehicles": vehicles,
            "purpose": "Narrow streets & village lanes",
            "pickups_served": ace_pickups,
            "daily_cost": vehicles * FLEET_TYPES["Tata Ace"]["daily_cost_inr"],
        }

    if bolero_pickups > 0 and "Bolero Pickup" in fleet_results:
        fr = fleet_results["Bolero Pickup"]
        trips = math.ceil(bolero_pickups / max(1, fr["stops_per_trip"]))
        vehicles = math.ceil(trips / max(1, fr["trips_per_vehicle"]))
        recommendation["Bolero Pickup"] = {
            "vehicles": vehicles,
            "purpose": "Narrow streets & inner town roads",
            "pickups_served": bolero_pickups,
            "daily_cost": vehicles * FLEET_TYPES["Bolero Pickup"]["daily_cost_inr"],
        }

    if medium_pickups > 0 and "Intra V50" in fleet_results:
        fr = fleet_results["Intra V50"]
        trips = math.ceil(medium_pickups / max(1, fr["stops_per_trip"]))
        vehicles = math.ceil(trips / max(1, fr["trips_per_vehicle"]))
        recommendation["Intra V50"] = {
            "vehicles": vehicles,
            "purpose": "Medium roads & town centers",
            "pickups_served": medium_pickups,
            "daily_cost": vehicles * FLEET_TYPES["Intra V50"]["daily_cost_inr"],
        }

    if main_pickups > 0 and "Intra V70" in fleet_results:
        fr = fleet_results["Intra V70"]
        trips = math.ceil(main_pickups / max(1, fr["stops_per_trip"]))
        vehicles = math.ceil(trips / max(1, fr["trips_per_vehicle"]))
        recommendation["Intra V70"] = {
            "vehicles": vehicles,
            "purpose": "Main roads & highway-connected areas",
            "pickups_served": main_pickups,
            "daily_cost": vehicles * FLEET_TYPES["Intra V70"]["daily_cost_inr"],
        }

    total_vehicles = sum(r["vehicles"] for r in recommendation.values())
    total_cost = sum(r["daily_cost"] for r in recommendation.values())

    return {
        "fleet_mix": recommendation,
        "total_vehicles": total_vehicles,
        "total_daily_cost_inr": total_cost,
        "total_monthly_cost_inr": total_cost * 26,
    }


# ─────────────────────────────────────────────────────────────
# SENSITIVITY ANALYSIS (uses calibrated baseline)
# ─────────────────────────────────────────────────────────────

def _run_fleet_total(clusters, percentile, cal_factor, avg_weight_g, material_mix=None,
                      road_override=None, freq_override=None):
    """Helper: run fleet sizing for all warehouses and return (total_vehicles, total_cost).

    road_override: dict like {"narrow_streets": 0.5, "medium_streets": 0.35, "main_roads": 0.15}
    freq_override: dict like {"daily": 0.5, "alternate": 0.3, ...} — reassigns pickup frequency
    """
    import random as _rand

    schedule = get_daily_pickup_schedule(deepcopy(clusters), percentile, cal_factor, avg_weight_g)

    # Apply frequency override if provided
    if freq_override:
        prob_map = {"daily": 1.0, "alternate": 0.5, "twice_weekly": 2/7, "weekly": 1/7}
        accum_map = {"daily": 1, "alternate": 2, "twice_weekly": 3.5, "weekly": 7}
        for wh, s in schedule.items():
            for h in s["horecas"]:
                _rand.seed(hash(h.get("Place ID", "")))
                r = _rand.random()
                cumulative = 0
                for fq, pct in freq_override.items():
                    cumulative += pct
                    if r <= cumulative:
                        h["pickup_frequency"] = fq
                        break
                h["daily_pickup_prob"] = prob_map[h["pickup_frequency"]]
                h["bottles_per_visit"] = h["daily_bottles"] * accum_map[h["pickup_frequency"]]
                h["weight_per_visit_kg"] = round(h["bottles_per_visit"] * avg_weight_g / 1000, 2)
            s["expected_daily_pickups"] = round(sum(h["daily_pickup_prob"] for h in s["horecas"]))
            s["expected_daily_weight_kg"] = round(sum(h["weight_per_visit_kg"] * h["daily_pickup_prob"] for h in s["horecas"]), 1)

    # Apply road distribution override temporarily
    saved_road = None
    if road_override:
        saved_road = dict(ROAD_DISTRIBUTION)
        ROAD_DISTRIBUTION.update(road_override)

    total_v, total_c = 0, 0
    for wh, s in schedule.items():
        f = calculate_fleet_for_warehouse(wh, s, material_mix=material_mix)
        r = recommend_fleet_mix(wh, f, s)
        total_v += r["total_vehicles"]
        total_c += r["total_daily_cost_inr"]

    if saved_road:
        ROAD_DISTRIBUTION.update(saved_road)

    return total_v, total_c


def run_sensitivity(clusters, base_percentile=50, cal_factor=1.0, avg_weight_g=None, material_mix=None):
    """Vary key variables one at a time. Returns combined +/- for each variable, ranked by impact.

    Each result has:
      - variable: human-readable variable name
      - description: what it means
      - low_label / high_label: what the -/+ scenario represents
      - low_vehicles / high_vehicles: fleet count for each
      - low_cost / high_cost: daily cost for each
      - low_delta_pct / high_delta_pct: % change from base
      - max_impact_pct: max(|low_delta_pct|, |high_delta_pct|) for ranking
    """
    if avg_weight_g is None:
        avg_weight_g = AVG_BOTTLE_WEIGHT_G

    print("\n" + "="*60)
    print("SENSITIVITY ANALYSIS")
    print("="*60)

    # Base case
    base_total, base_cost = _run_fleet_total(clusters, base_percentile, cal_factor, avg_weight_g, material_mix)

    def pct(v):
        return round((v - base_total) / base_total * 100, 1) if base_total > 0 else 0

    results = []

    # 1. HoReCa Share of Returns (±30%)
    lo_v, lo_c = _run_fleet_total(clusters, base_percentile, cal_factor * 0.7, avg_weight_g, material_mix)
    hi_v, hi_c = _run_fleet_total(clusters, base_percentile, cal_factor * 1.3, avg_weight_g, material_mix)
    results.append({
        "variable": "HoReCa Share of Returns",
        "description": "What % of total DRS returns flow through HoReCa channel (currently 50%)",
        "low_label": "−30% share", "high_label": "+30% share",
        "low_vehicles": lo_v, "high_vehicles": hi_v,
        "low_cost": lo_c, "high_cost": hi_c,
        "low_delta_pct": pct(lo_v), "high_delta_pct": pct(hi_v),
        "base_vehicles": base_total, "base_cost": base_cost,
    })

    # 2. Pickup Frequency — more frequent vs less frequent
    freq_high = {"daily": 0.50, "alternate": 0.30, "twice_weekly": 0.15, "weekly": 0.05}
    freq_low = {"daily": 0.10, "alternate": 0.20, "twice_weekly": 0.30, "weekly": 0.40}
    lo_v, lo_c = _run_fleet_total(clusters, base_percentile, cal_factor, avg_weight_g, material_mix, freq_override=freq_low)
    hi_v, hi_c = _run_fleet_total(clusters, base_percentile, cal_factor, avg_weight_g, material_mix, freq_override=freq_high)
    results.append({
        "variable": "Pickup Frequency",
        "description": "How often HoReCas are visited — more frequent means more daily stops but less waste per stop",
        "low_label": "Less frequent (40% weekly)", "high_label": "More frequent (50% daily)",
        "low_vehicles": lo_v, "high_vehicles": hi_v,
        "low_cost": lo_c, "high_cost": hi_c,
        "low_delta_pct": pct(lo_v), "high_delta_pct": pct(hi_v),
        "base_vehicles": base_total, "base_cost": base_cost,
    })

    # 3. Road Distribution — more narrow vs more main roads
    road_narrow = {"narrow_streets": 0.50, "medium_streets": 0.35, "main_roads": 0.15}
    road_main = {"narrow_streets": 0.15, "medium_streets": 0.35, "main_roads": 0.50}
    lo_v, lo_c = _run_fleet_total(clusters, base_percentile, cal_factor, avg_weight_g, material_mix, road_override=road_main)
    hi_v, hi_c = _run_fleet_total(clusters, base_percentile, cal_factor, avg_weight_g, material_mix, road_override=road_narrow)
    results.append({
        "variable": "Road Distribution",
        "description": "Mix of narrow streets vs main roads — narrow streets need smaller, less efficient trucks",
        "low_label": "More main roads (50%)", "high_label": "More narrow streets (50%)",
        "low_vehicles": lo_v, "high_vehicles": hi_v,
        "low_cost": lo_c, "high_cost": hi_c,
        "low_delta_pct": pct(lo_v), "high_delta_pct": pct(hi_v),
        "base_vehicles": base_total, "base_cost": base_cost,
    })

    # 4. Material Mix — lighter vs heavier avg weight
    lo_v, lo_c = _run_fleet_total(clusters, base_percentile, cal_factor, avg_weight_g * 0.7, material_mix)
    hi_v, hi_c = _run_fleet_total(clusters, base_percentile, cal_factor, avg_weight_g * 1.4, material_mix)
    results.append({
        "variable": "Material Mix (Avg Weight)",
        "description": "Heavier mix (more glass) fills trucks faster → more trips needed. Lighter mix (more MLP/PET) means more units per trip.",
        "low_label": "Lighter mix (−30% weight)", "high_label": "Heavier mix (+40% weight)",
        "low_vehicles": lo_v, "high_vehicles": hi_v,
        "low_cost": lo_c, "high_cost": hi_c,
        "low_delta_pct": pct(lo_v), "high_delta_pct": pct(hi_v),
        "base_vehicles": base_total, "base_cost": base_cost,
    })

    # 5. Volume (PTM) — ±30% total return units
    lo_v, lo_c = _run_fleet_total(clusters, base_percentile, cal_factor * 0.7, avg_weight_g, material_mix)
    hi_v, hi_c = _run_fleet_total(clusters, base_percentile, cal_factor * 1.3, avg_weight_g, material_mix)
    # Note: this is similar to #1 but labelled as volume
    # Let's make it ±20% volume instead to differentiate
    lo_v2, lo_c2 = _run_fleet_total(clusters, base_percentile, cal_factor * 0.8, avg_weight_g, material_mix)
    hi_v2, hi_c2 = _run_fleet_total(clusters, base_percentile, cal_factor * 1.2, avg_weight_g, material_mix)
    results.append({
        "variable": "Total Volume (Return Units)",
        "description": "Overall DRS return units — higher volumes mean more weight to collect daily",
        "low_label": "−20% volume", "high_label": "+20% volume",
        "low_vehicles": lo_v2, "high_vehicles": hi_v2,
        "low_cost": lo_c2, "high_cost": hi_c2,
        "low_delta_pct": pct(lo_v2), "high_delta_pct": pct(hi_v2),
        "base_vehicles": base_total, "base_cost": base_cost,
    })

    # 6. Operational efficiency — scan rate & setup time
    saved_scan = _cfg.SCAN_RATE_PER_MIN
    saved_setup = _cfg.AVG_SETUP_TIME_MIN
    # Slower: 12 btl/min, 5 min setup
    _cfg.SCAN_RATE_PER_MIN = 12
    _cfg.AVG_SETUP_TIME_MIN = 5
    hi_v, hi_c = _run_fleet_total(clusters, base_percentile, cal_factor, avg_weight_g, material_mix)
    # Faster: 30 btl/min, 2 min setup
    _cfg.SCAN_RATE_PER_MIN = 30
    _cfg.AVG_SETUP_TIME_MIN = 2
    lo_v, lo_c = _run_fleet_total(clusters, base_percentile, cal_factor, avg_weight_g, material_mix)
    _cfg.SCAN_RATE_PER_MIN = saved_scan
    _cfg.AVG_SETUP_TIME_MIN = saved_setup
    results.append({
        "variable": "Operational Efficiency",
        "description": "Scan rate + setup time at each stop — faster scanning means more stops per trip",
        "low_label": "Faster (30 btl/min, 2 min setup)", "high_label": "Slower (12 btl/min, 5 min setup)",
        "low_vehicles": lo_v, "high_vehicles": hi_v,
        "low_cost": lo_c, "high_cost": hi_c,
        "low_delta_pct": pct(lo_v), "high_delta_pct": pct(hi_v),
        "base_vehicles": base_total, "base_cost": base_cost,
    })

    # Compute max_impact_pct and sort descending
    for r in results:
        r["max_impact_pct"] = max(abs(r["low_delta_pct"]), abs(r["high_delta_pct"]))
    results.sort(key=lambda x: x["max_impact_pct"], reverse=True)

    print(f"  Base: {base_total} vehicles, INR {base_cost:,}/day")
    for r in results:
        print(f"  {r['variable']:30s}: {r['low_delta_pct']:+.1f}% / {r['high_delta_pct']:+.1f}%  (max {r['max_impact_pct']:.1f}%)")

    return {"base_vehicles": base_total, "base_cost": base_cost, "variables": results}


def run_aggregate_sensitivity(month_keys=None):
    """Run sensitivity across multiple months and return median-ranked results.

    This gives a single, stable sensitivity ranking that doesn't change per month.
    For each variable, we take the median of max_impact_pct across all months.

    Args:
        month_keys: list of month keys to use. Defaults to 12 months starting Aug-26.

    Returns:
        dict with "variables" list (median-ranked), "months_used", and per-variable
        "monthly_detail" showing how the impact varied.
    """
    import statistics

    if _return_units_data is None:
        raise ValueError("DRS Return Units data not available — CSV not loaded")

    # Default: 12 months starting from Aug-26
    if month_keys is None:
        all_months = _return_units_data["months"]
        # Find Aug-26 index
        try:
            start_idx = all_months.index("Aug-26")
        except ValueError:
            start_idx = 0
        month_keys = all_months[start_idx:start_idx + 12]

    # Filter to months that have meaningful data (> 0.1 Cr total)
    valid_months = []
    for mk in month_keys:
        ru = _return_units_data["return_units"].get(mk, {})
        if ru.get("Total", 0) > 0.1:
            valid_months.append(mk)

    if not valid_months:
        raise ValueError("No months with meaningful data found")

    print(f"\n{'='*60}")
    print(f"AGGREGATE SENSITIVITY ANALYSIS — {len(valid_months)} months")
    print(f"Months: {', '.join(valid_months)}")
    print(f"{'='*60}")

    # Preload HoReCas and clusters once (FY27 fixed set)
    horecas_base = load_horeca_data()
    clusters_base = assign_to_warehouses(horecas_base)

    # Collect sensitivity results per month
    # Key: variable name → list of {low_delta_pct, high_delta_pct, max_impact_pct}
    var_monthly = defaultdict(list)
    var_meta = {}  # Store the first month's labels/descriptions

    for mk in valid_months:
        ru = _return_units_data["return_units"][mk]
        mat_return_cr = {mat: ru.get(mat, 0) for mat in MATERIALS}

        # Compute daily units and HoReCa share
        daily_units_by_mat = {mat: mat_return_cr[mat] * 1e7 / 30 for mat in MATERIALS}
        horeca_daily_total = sum(v * _cfg.HORECA_SHARE_OF_RETURNS for v in daily_units_by_mat.values())

        # Material mix and avg weight
        total_daily = sum(daily_units_by_mat.values())
        material_mix = {}
        for mat in MATERIALS:
            material_mix[mat] = round(daily_units_by_mat[mat] / total_daily, 4) if total_daily > 0 else 0
        avg_weight_g = sum(material_mix.get(mat, 0) * MATERIALS[mat]["weight_g"] for mat in MATERIALS)

        # Use fixed HoReCa set (FY27 scope)
        clusters = clusters_base
        horecas = horecas_base

        # Cal factor
        bottom_up = sum(estimate_daily_waste(h, 50) for h in horecas)
        cal_factor = horeca_daily_total / bottom_up if bottom_up > 0 else 1.0

        print(f"  {mk:8s}: {horeca_daily_total:>10,.0f} units/day, avg_wt={avg_weight_g:.1f}g, cal={cal_factor:.2f}")

        # Run sensitivity for this month
        sens = run_sensitivity(clusters, 50, cal_factor, avg_weight_g, material_mix)

        for v in sens["variables"]:
            vname = v["variable"]
            var_monthly[vname].append({
                "month": mk,
                "low_delta_pct": v["low_delta_pct"],
                "high_delta_pct": v["high_delta_pct"],
                "max_impact_pct": v["max_impact_pct"],
                "base_vehicles": v["base_vehicles"],
            })
            if vname not in var_meta:
                var_meta[vname] = {
                    "description": v["description"],
                    "low_label": v["low_label"],
                    "high_label": v["high_label"],
                }

    # Compute median for each variable
    results = []
    for vname, monthly_data in var_monthly.items():
        impacts = [d["max_impact_pct"] for d in monthly_data]
        lo_pcts = [d["low_delta_pct"] for d in monthly_data]
        hi_pcts = [d["high_delta_pct"] for d in monthly_data]

        median_impact = round(statistics.median(impacts), 1)
        median_lo = round(statistics.median(lo_pcts), 1)
        median_hi = round(statistics.median(hi_pcts), 1)
        min_impact = round(min(impacts), 1)
        max_impact = round(max(impacts), 1)

        meta = var_meta[vname]
        results.append({
            "variable": vname,
            "description": meta["description"],
            "low_label": meta["low_label"],
            "high_label": meta["high_label"],
            "median_impact_pct": median_impact,
            "median_low_delta_pct": median_lo,
            "median_high_delta_pct": median_hi,
            "impact_range": [min_impact, max_impact],
            "months_sampled": len(monthly_data),
        })

    # Sort by median impact (descending)
    results.sort(key=lambda x: x["median_impact_pct"], reverse=True)

    print(f"\n  AGGREGATE RANKING (median of {len(valid_months)} months):")
    for i, r in enumerate(results):
        print(f"    #{i+1} {r['variable']:30s}: median {r['median_impact_pct']:.1f}% (range {r['impact_range'][0]:.1f}–{r['impact_range'][1]:.1f}%)")

    return {
        "months_used": valid_months,
        "variables": results,
    }


# ─────────────────────────────────────────────────────────────
# MAIN EXECUTION
# ─────────────────────────────────────────────────────────────

def run_model(scenario_name="base", skip_sensitivity=False):
    """Run the complete model for a given scenario (PTM-calibrated)."""
    scenario = SCENARIOS[scenario_name]
    percentile = scenario["waste_gen_percentile"]
    year = scenario["return_rate_year"]
    ptm_year = scenario.get("ptm_year", year)
    ptm_period = scenario.get("ptm_period", "normal")

    print(f"\n{'='*60}")
    print(f"GOA DRS REVERSE LOGISTICS MODEL — {scenario['label']}")
    print(f"PTM year: {ptm_year} ({ptm_period}) | Return rate: {year} ({RETURN_RATES[year]['total']*100:.0f}%)")
    print(f"{'='*60}\n")

    # 1. Load data (FY27 fixed set)
    print("Step 1: Loading HoReCa data...")
    horecas = load_horeca_data()

    # 2. Calibrate from PTM
    print(f"\nStep 2: PTM Calibration ({ptm_year} {ptm_period})...")
    cal = calibrate_from_ptm(horecas, ptm_year, ptm_period, percentile)
    print(f"  PTM total: {cal['ptm_total_cr_month']} Cr/month")
    print(f"  HoReCa share: {cal['horeca_total_cr_month']} Cr/month ({cal['horeca_daily_total']:,} units/day)")
    print(f"  Bottom-up uncalibrated: {cal['bottom_up_total']:,} units/day")
    print(f"  Calibration factor: {cal['calibration_factor']}x")
    print(f"  Avg per HoReCa: {cal['avg_per_horeca']} bottles/day")

    cal_factor = cal["calibration_factor"]
    cal_avg_weight = cal["calibrated_avg_weight_g"]

    print(f"\n  Calibrated avg bottle weight: {cal_avg_weight}g (was {cal['original_avg_weight_g']}g)")
    print(f"  Calibrated material mix:")
    for mat in MATERIALS:
        orig = cal["original_material_mix"].get(mat, 0)
        new = cal["calibrated_material_mix"].get(mat, 0)
        print(f"    {mat:12s}: {orig*100:5.1f}% → {new*100:5.1f}%")

    print(f"\n  Calibrated waste gen per HoReCa type (bottles/day, mean):")
    for htype in sorted(cal["calibrated_waste_gen"].keys()):
        cw = cal["calibrated_waste_gen"][htype]
        print(f"    {htype:18s}: {cw['original_mean']:5.0f} → {cw['mean']:5.1f}")

    # 4. Cluster to warehouses
    print(f"\nStep 3: Assigning HoReCas to warehouses...")
    clusters = assign_to_warehouses(horecas)
    for wh, hs in sorted(clusters.items(), key=lambda x: -len(x[1])):
        avg_dist = sum(h["distance_to_warehouse_km"] for h in hs) / len(hs) if hs else 0
        print(f"  {wh:12s}: {len(hs):4d} HoReCas (avg dist: {avg_dist:.1f} km)")

    # 5. Estimate daily schedule (calibrated)
    print(f"\nStep 4: Estimating daily pickup schedule (calibrated, P{percentile})...")
    schedule = get_daily_pickup_schedule(clusters, percentile, cal_factor, cal_avg_weight)
    for wh, s in sorted(schedule.items(), key=lambda x: -x[1]["expected_daily_weight_kg"]):
        print(f"  {wh:12s}: {s['expected_daily_pickups']:3d} pickups/day, "
              f"{s['expected_daily_weight_kg']:,.0f} kg/day, "
              f"{s['expected_daily_bottles']:,} bottles/day")
        freq = s["frequency_distribution"]
        print(f"               Freq: daily={freq.get('daily',0)}, alt={freq.get('alternate',0)}, "
              f"2x/wk={freq.get('twice_weekly',0)}, weekly={freq.get('weekly',0)}")

    # 6. Calculate fleet per warehouse
    print(f"\nStep 5: Fleet requirement per warehouse...")
    all_recommendations = {}
    grand_total_vehicles = 0
    grand_total_cost = 0

    for wh_name in sorted(schedule.keys()):
        sched = schedule[wh_name]
        fleet_results = calculate_fleet_for_warehouse(wh_name, sched)
        rec = recommend_fleet_mix(wh_name, fleet_results, sched)
        all_recommendations[wh_name] = rec

        print(f"\n  {wh_name} ({WAREHOUSES[wh_name]['region']})")
        print(f"     {sched['total_horecas']} HoReCas | {sched['expected_daily_pickups']} pickups/day | {sched['expected_daily_weight_kg']:,.0f} kg/day")
        print(f"     Fleet mix:")
        for ft_name, ft_data in rec["fleet_mix"].items():
            if ft_data["vehicles"] > 0:
                print(f"       {ft_name:12s}: {ft_data['vehicles']} vehicles — {ft_data['purpose']}")
        print(f"     Total: {rec['total_vehicles']} vehicles | INR {rec['total_daily_cost_inr']:,}/day | INR {rec['total_monthly_cost_inr']:,}/month")

        grand_total_vehicles += rec["total_vehicles"]
        grand_total_cost += rec["total_daily_cost_inr"]

    # 7. Summary
    print(f"\n{'='*60}")
    print(f"TOTAL FLEET REQUIREMENT — {scenario['label']}")
    print(f"{'='*60}")

    fleet_totals = defaultdict(int)
    for wh, rec in all_recommendations.items():
        for ft, data in rec["fleet_mix"].items():
            fleet_totals[ft] += data["vehicles"]

    for ft in FLEET_TYPES:
        if fleet_totals[ft] > 0:
            print(f"  {ft:16s}: {fleet_totals[ft]:3d} vehicles")
    print(f"  {'TOTAL':16s}: {grand_total_vehicles:3d} vehicles")
    print(f"  Daily cost : INR {grand_total_cost:,}")
    print(f"  Monthly cost: INR {grand_total_cost * 26:,}")

    # 8. Vendor capacity check
    print(f"\n{'='*60}")
    print("VENDOR CAPACITY CHECK")
    print(f"{'='*60}")
    vendor_totals = {"tata_ace": 0, "1mt": 0, "1.5_2mt": 0, "3_5mt": 0}
    completed_totals = {"tata_ace": 0, "1mt": 0, "1.5_2mt": 0, "3_5mt": 0}
    for v in VENDORS:
        for k in vendor_totals:
            vendor_totals[k] += v[k]
            if v["status"] == "Completed":
                completed_totals[k] += v[k]

    mapping = {"Tata Ace": "tata_ace", "1 MT": "1mt", "1.5-2 MT": "1.5_2mt", "3-5 MT": "3_5mt"}
    print(f"  {'Type':12s} {'Need':>6s} {'Available':>10s} {'Completed':>10s} {'Gap':>6s}")
    for ft, vk in mapping.items():
        need = fleet_totals[ft]
        avail = vendor_totals[vk]
        comp = completed_totals[vk]
        gap = need - comp
        status = "OK" if gap <= 0 else "GAP"
        print(f"  {ft:12s} {need:6d} {avail:10d} {comp:10d} {gap:+6d} {status}")

    # 9. Sensitivity (skip for faster initial load)
    sensitivity = None
    if not skip_sensitivity:
        sensitivity = run_sensitivity(clusters, percentile, cal_factor, cal_avg_weight)
        print(f"\n  {'Parameter':<30s} {'Scenario':<40s} {'Vehicles':>8s} {'Delta':>8s} {'%':>6s}")
        print(f"  {'-'*30} {'-'*40} {'-'*8} {'-'*8} {'-'*6}")
        for s in sensitivity:
            print(f"  {s['parameter']:<30s} {s['value']:<40s} {s['total_vehicles']:8d} {s['delta_vehicles']:+8d} {s['delta_pct']:+6.1f}%")

    return {
        "scenario": scenario,
        "calibration": cal,
        "clusters": {wh: {
            "total_horecas": schedule[wh]["total_horecas"],
            "expected_daily_pickups": schedule[wh]["expected_daily_pickups"],
            "expected_daily_weight_kg": schedule[wh]["expected_daily_weight_kg"],
            "expected_daily_bottles": schedule[wh]["expected_daily_bottles"],
            "frequency_distribution": schedule[wh]["frequency_distribution"],
            "recommendation": all_recommendations[wh],
            "warehouse_info": WAREHOUSES[wh],
            "horecas": [
                {
                    "name": h.get("Name", ""),
                    "lat": float(h["Latitude"]),
                    "lon": float(h["Longitude"]),
                    "type": h.get("HoReCa_Type", ""),
                    "size": h.get("Size_Tier", ""),
                    "alcohol": h.get("Alcohol_Signal", ""),
                    "daily_bottles": h.get("daily_bottles", 0),
                    "pickup_freq": h.get("pickup_frequency", ""),
                    "weight_per_visit_kg": h.get("weight_per_visit_kg", 0),
                    "dist_to_wh_km": h.get("distance_to_warehouse_km", 0),
                }
                for h in schedule[wh]["horecas"]
            ],
        } for wh in schedule},
        "fleet_totals": dict(fleet_totals),
        "grand_total_vehicles": grand_total_vehicles,
        "grand_total_daily_cost": grand_total_cost,
        "sensitivity": sensitivity,
    }


# ─────────────────────────────────────────────────────────────
# MONTH-BASED MODEL (PRIMARY) — Uses actual DRS Return Units
# ─────────────────────────────────────────────────────────────

def _is_fy27(month_key):
    """Check if a month key falls in FY27 (Apr-26 to Mar-27)."""
    month_map = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                 "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    parts = month_key.split("-")
    if len(parts) != 2:
        return False
    mon, yr = parts[0], int(parts[1])
    m = month_map.get(mon, 0)
    # FY27 = Apr-26 (m>=4, yr=26) through Mar-27 (m<=3, yr=27)
    if yr == 26 and m >= 4:
        return True
    if yr == 27 and m <= 3:
        return True
    return False


def get_available_months():
    """Return list of available months from PnL CSV (FY27 only)."""
    if _return_units_data is None:
        return []
    return [m for m in _return_units_data["months"] if _is_fy27(m)]


def run_model_for_month(month_key="Oct-27", skip_sensitivity=False):
    """
    Run fleet estimation for a specific month using actual DRS Return Units from PnL CSV.

    Flow:
      1. Read DRS Return Units for month (per material, in Cr)
      2. Convert to daily units: return_units_cr * 1e7 / 30
      3. Apply _cfg.HORECA_SHARE_OF_RETURNS to get HoReCa daily units
      4. Compute weight per material: daily_units * weight_g / 1000 → kg/day
      5. Distribute across warehouses proportionally (by HoReCa count share)
      6. Run fleet sizing per warehouse
    """
    if _return_units_data is None:
        raise ValueError("DRS Return Units data not available — CSV not loaded")

    if month_key not in _return_units_data["return_units"]:
        raise ValueError(f"Month '{month_key}' not found in CSV. Available: {_return_units_data['months'][:5]}...")

    ru = _return_units_data["return_units"][month_key]
    season = _return_units_data["seasons"].get(month_key, "Normal")
    return_rate_str = _return_units_data["return_rates"].get(month_key, {}).get("Total", "0%")

    print(f"\n{'='*60}")
    print(f"GOA DRS REVERSE LOGISTICS MODEL — {month_key} ({season})")
    print(f"{'='*60}\n")

    # Step 1: DRS Return Units for this month
    total_return_cr = ru.get("Total", 0)
    mat_return_cr = {mat: ru.get(mat, 0) for mat in MATERIALS}

    print(f"  DRS Return Units: {total_return_cr:.1f} Cr total")
    for mat in MATERIALS:
        print(f"    {mat:12s}: {mat_return_cr[mat]:.2f} Cr")

    # Step 2: Convert to daily units
    daily_units_by_mat = {}
    for mat in MATERIALS:
        daily_units_by_mat[mat] = mat_return_cr[mat] * 1e7 / 30
    total_daily_units = sum(daily_units_by_mat.values())

    # Step 3: Apply HoReCa share
    horeca_daily_units_by_mat = {}
    for mat in MATERIALS:
        horeca_daily_units_by_mat[mat] = daily_units_by_mat[mat] * _cfg.HORECA_SHARE_OF_RETURNS
    horeca_daily_total_units = sum(horeca_daily_units_by_mat.values())

    print(f"\n  HoReCa share ({HORECA_SHARE_OF_RETURNS*100:.0f}%): {horeca_daily_total_units:,.0f} units/day")

    # Step 4: Compute weight per material
    horeca_daily_weight_by_mat = {}
    for mat in MATERIALS:
        horeca_daily_weight_by_mat[mat] = horeca_daily_units_by_mat[mat] * MATERIALS[mat]["weight_g"] / 1000  # kg
    horeca_daily_weight_kg = sum(horeca_daily_weight_by_mat.values())

    print(f"  Daily weight at HoReCa: {horeca_daily_weight_kg:,.1f} kg/day")

    # Compute material mix and avg bottle weight from actual return units
    material_mix = {}
    for mat in MATERIALS:
        material_mix[mat] = round(horeca_daily_units_by_mat[mat] / horeca_daily_total_units, 4) if horeca_daily_total_units > 0 else 0
    avg_weight_g = sum(
        material_mix.get(mat, 0) * MATERIALS[mat]["weight_g"] for mat in MATERIALS
    )

    print(f"  Avg bottle weight: {avg_weight_g:.1f}g")
    print(f"  Material mix: {', '.join(f'{mat}={material_mix[mat]*100:.1f}%' for mat in MATERIALS)}")

    # Step 5: Load HoReCa data
    # FY27 scope: Confirmed+Likely+Inferred (all types) + Possible (Restaurants & Hotels only)
    horecas = load_horeca_data()
    avg_per_horeca = horeca_daily_total_units / len(horecas) if horecas else 0

    # Assign to warehouses
    print(f"\n  Assigning {len(horecas)} HoReCas to warehouses...")
    clusters = assign_to_warehouses(horecas)
    total_horecas = len(horecas)

    # Step 6: Distribute volume to warehouses proportionally (by HoReCa count)
    # Then run fleet sizing per warehouse using the proportional weight
    wh_horeca_counts = {wh: len(hs) for wh, hs in clusters.items()}

    for wh, hs in sorted(clusters.items(), key=lambda x: -len(x[1])):
        share = len(hs) / total_horecas if total_horecas > 0 else 0
        wh_weight = horeca_daily_weight_kg * share
        avg_dist = sum(h["distance_to_warehouse_km"] for h in hs) / len(hs) if hs else 0
        print(f"  {wh:20s}: {len(hs):4d} HoReCas ({share*100:.1f}%), {wh_weight:,.1f} kg/day, avg dist: {avg_dist:.1f} km")

    # For each warehouse, we need to set up the schedule data structure
    # that calculate_fleet_for_warehouse() expects. We use proportional volume distribution.
    # The calibration factor is derived from actual return units distributed to match HoReCa count share.
    all_recommendations = {}
    grand_total_vehicles = 0
    grand_total_cost = 0
    schedule = {}

    for wh_name, wh_horecas in clusters.items():
        share = len(wh_horecas) / total_horecas if total_horecas > 0 else 0
        wh_daily_weight = horeca_daily_weight_kg * share
        wh_daily_units = horeca_daily_total_units * share

        # Compute calibration factor for this warehouse's HoReCas
        # so that bottom-up estimates match the proportional top-down volume
        bottom_up = sum(estimate_daily_waste(h, 50) for h in wh_horecas)
        cal_factor = wh_daily_units / bottom_up if bottom_up > 0 else 1.0

        # Build schedule via existing machinery
        wh_clusters = {wh_name: wh_horecas}
        wh_schedule = get_daily_pickup_schedule(wh_clusters, 50, cal_factor, avg_weight_g)
        sched = wh_schedule[wh_name]

        # Override weight with the exact proportional value from PnL
        sched["expected_daily_weight_kg"] = round(wh_daily_weight, 1)

        schedule[wh_name] = sched

        # Fleet sizing (pass material_mix for volumetric weight)
        fleet_results = calculate_fleet_for_warehouse(wh_name, sched, material_mix=material_mix)
        rec = recommend_fleet_mix(wh_name, fleet_results, sched)
        all_recommendations[wh_name] = rec

        grand_total_vehicles += rec["total_vehicles"]
        grand_total_cost += rec["total_daily_cost_inr"]

    # Fleet totals
    fleet_totals = defaultdict(int)
    for wh, rec in all_recommendations.items():
        for ft, data in rec["fleet_mix"].items():
            fleet_totals[ft] += data["vehicles"]

    print(f"\n{'='*60}")
    print(f"FLEET REQUIREMENT — {month_key} ({season})")
    print(f"{'='*60}")
    for ft in FLEET_TYPES:
        if fleet_totals[ft] > 0:
            print(f"  {ft:16s}: {fleet_totals[ft]:3d} vehicles")
    print(f"  {'TOTAL':16s}: {grand_total_vehicles:3d} vehicles")
    print(f"  Daily cost : INR {grand_total_cost:,}")
    print(f"  Monthly cost: INR {grand_total_cost * 26:,}")

    # Sensitivity (optional)
    sensitivity = None
    if not skip_sensitivity:
        # Use the overall cal_factor for sensitivity
        overall_bottom_up = sum(estimate_daily_waste(h, 50) for h in horecas)
        overall_cal = horeca_daily_total_units / overall_bottom_up if overall_bottom_up > 0 else 1.0
        sensitivity = run_sensitivity(clusters, 50, overall_cal, avg_weight_g)

    # Build calibration-like dict for compatibility with existing UI
    cal_info = {
        "calibration_factor": None,  # Not applicable — using actual return units
        "horeca_daily_total": round(horeca_daily_total_units),
        "bottom_up_total": None,
        "avg_per_horeca": round(avg_per_horeca, 1),
        "num_horecas": total_horecas,
        "calibrated_material_mix": material_mix,
        "original_material_mix": dict(HORECA_MATERIAL_MIX),
        "calibrated_avg_weight_g": round(avg_weight_g, 1),
        "original_avg_weight_g": round(AVG_BOTTLE_WEIGHT_G, 1),
        "horeca_daily_by_material": {k: round(v) for k, v in horeca_daily_units_by_mat.items()},
        "ptm_year": None,
        "ptm_period": None,
        "ptm_total_cr_month": None,
        "horeca_total_cr_month": round(total_return_cr * _cfg.HORECA_SHARE_OF_RETURNS, 2),
        "ptm_by_material": mat_return_cr,
        "consumption_shares": dict(HORECA_CONSUMPTION_SHARE),
        "included_possible": False,  # FY27: fixed HoReCa set, no dynamic expansion
        "mode": "month",
        "month": month_key,
        "season": season,
        "return_rate": return_rate_str,
        "return_units_cr": dict(ru),
        "daily_weight_kg": round(horeca_daily_weight_kg, 1),
        "daily_weight_by_material_kg": {k: round(v, 2) for k, v in horeca_daily_weight_by_mat.items()},
    }

    return {
        "scenario": {"label": f"{month_key} ({season})", "mode": "month", "month": month_key, "season": season},
        "calibration": cal_info,
        "clusters": {wh: {
            "total_horecas": schedule[wh]["total_horecas"],
            "expected_daily_pickups": schedule[wh]["expected_daily_pickups"],
            "expected_daily_weight_kg": schedule[wh]["expected_daily_weight_kg"],
            "expected_daily_bottles": schedule[wh]["expected_daily_bottles"],
            "frequency_distribution": schedule[wh]["frequency_distribution"],
            "recommendation": all_recommendations[wh],
            "warehouse_info": WAREHOUSES[wh],
            "horecas": [
                {
                    "name": h.get("Name", ""),
                    "lat": float(h["Latitude"]),
                    "lon": float(h["Longitude"]),
                    "type": h.get("HoReCa_Type", ""),
                    "size": h.get("Size_Tier", ""),
                    "alcohol": h.get("Alcohol_Signal", ""),
                    "daily_bottles": h.get("daily_bottles", 0),
                    "pickup_freq": h.get("pickup_frequency", ""),
                    "weight_per_visit_kg": h.get("weight_per_visit_kg", 0),
                    "dist_to_wh_km": h.get("distance_to_warehouse_km", 0),
                }
                for h in schedule[wh]["horecas"]
            ],
        } for wh in schedule},
        "fleet_totals": dict(fleet_totals),
        "grand_total_vehicles": grand_total_vehicles,
        "grand_total_daily_cost": grand_total_cost,
        "sensitivity": sensitivity,
    }


def run_mom_table():
    """
    Run fleet sizing for ALL months in the PnL CSV and return a MoM summary table.

    Returns list of dicts, one per month:
    [
        {
            "month": "Jun-26",
            "season": "Normal",
            "return_units_cr": {"Total": X, "PET": X, ...},
            "daily_units": X,
            "daily_weight_kg": X,
            "total_vehicles": X,
            "fleet_mix": {"Tata Ace": X, "1 MT": X, ...},
            "daily_cost": X,
            "warehouses": {
                "Margao South": {"vehicles": X, "fleet_mix": {...}, "weight_kg": X},
                ...
            }
        },
        ...
    ]
    """
    if _return_units_data is None:
        return []

    # Pre-load HoReCa data and clusters once (expensive)
    horecas_base = load_horeca_data()

    results = []
    # FY27 scope: only Apr-26 to Mar-27
    all_months = _return_units_data["months"]
    fy27_months = [m for m in all_months if _is_fy27(m)]

    for month_key in fy27_months:
        ru = _return_units_data["return_units"][month_key]
        season = _return_units_data["seasons"].get(month_key, "Normal")
        total_return_cr = ru.get("Total", 0)

        # Skip months with zero return units
        if total_return_cr <= 0:
            results.append({
                "month": month_key,
                "season": season,
                "return_units_cr": dict(ru),
                "daily_units": 0,
                "daily_weight_kg": 0,
                "total_vehicles": 0,
                "fleet_mix": {"Tata Ace": 0, "Bolero Pickup": 0, "Intra V50": 0, "Intra V70": 0},
                "daily_cost": 0,
                "warehouses": {},
            })
            continue

        # Compute daily HoReCa units and weight
        horeca_daily_units = {}
        horeca_daily_weight = {}
        for mat in MATERIALS:
            units = ru.get(mat, 0) * 1e7 / 30 * _cfg.HORECA_SHARE_OF_RETURNS
            horeca_daily_units[mat] = units
            horeca_daily_weight[mat] = units * MATERIALS[mat]["weight_g"] / 1000
        total_daily_units = sum(horeca_daily_units.values())
        total_daily_weight = sum(horeca_daily_weight.values())

        # Material mix and avg weight
        material_mix = {}
        for mat in MATERIALS:
            material_mix[mat] = horeca_daily_units[mat] / total_daily_units if total_daily_units > 0 else 0
        avg_wt_g = sum(material_mix.get(mat, 0) * MATERIALS[mat]["weight_g"] for mat in MATERIALS)

        # Use fixed HoReCa set (FY27 scope)
        horecas = horecas_base

        # Cluster and compute fleet
        clusters = assign_to_warehouses(deepcopy(horecas))
        total_h = len(horecas)

        wh_data = {}
        fleet_totals = defaultdict(int)
        total_vehicles = 0
        total_cost = 0

        for wh_name, wh_horecas in clusters.items():
            share = len(wh_horecas) / total_h if total_h > 0 else 0
            wh_weight = total_daily_weight * share
            wh_units = total_daily_units * share

            bottom_up = sum(estimate_daily_waste(h, 50) for h in wh_horecas)
            cal_f = wh_units / bottom_up if bottom_up > 0 else 1.0

            wh_clusters = {wh_name: wh_horecas}
            wh_schedule = get_daily_pickup_schedule(wh_clusters, 50, cal_f, avg_wt_g)
            sched = wh_schedule[wh_name]
            sched["expected_daily_weight_kg"] = round(wh_weight, 1)

            fleet_results = calculate_fleet_for_warehouse(wh_name, sched, material_mix=material_mix)
            rec = recommend_fleet_mix(wh_name, fleet_results, sched)

            wh_fleet_mix = {ft: data["vehicles"] for ft, data in rec["fleet_mix"].items()}
            wh_data[wh_name] = {
                "vehicles": rec["total_vehicles"],
                "fleet_mix": wh_fleet_mix,
                "weight_kg": round(wh_weight, 1),
                "daily_cost": rec["total_daily_cost_inr"],
                "horecas": len(wh_horecas),
            }
            for ft, v in wh_fleet_mix.items():
                fleet_totals[ft] += v
            total_vehicles += rec["total_vehicles"]
            total_cost += rec["total_daily_cost_inr"]

        results.append({
            "month": month_key,
            "season": season,
            "return_units_cr": dict(ru),
            "daily_units": round(total_daily_units),
            "daily_weight_kg": round(total_daily_weight, 1),
            "total_vehicles": total_vehicles,
            "fleet_mix": dict(fleet_totals),
            "daily_cost": total_cost,
            "warehouses": wh_data,
        })

    print(f"[model] MoM table computed for {len(results)} months")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Goa DRS Reverse Logistics Fleet Model")
    parser.add_argument("--scenario", choices=["conservative", "base", "aggressive"], default=None)
    parser.add_argument("--month", default=None, help="Run model for specific month (e.g. Oct-27)")
    parser.add_argument("--mom", action="store_true", help="Run full MoM table")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--output", default=None, help="Save results JSON to file")
    args = parser.parse_args()

    if args.mom:
        mom = run_mom_table()
        if args.output:
            with open(args.output, "w") as f:
                json.dump(mom, f, indent=2, default=str)
        else:
            for row in mom:
                print(f"  {row['month']:8s} {row['season']:6s} | {row['return_units_cr'].get('Total',0):5.1f} Cr | {row['daily_weight_kg']:8.1f} kg/day | {row['total_vehicles']:3d} vehicles | INR {row['daily_cost']:,}/day")
    elif args.all:
        all_results = {}
        for s in ["conservative", "base", "aggressive"]:
            all_results[s] = run_model(s)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(all_results, f, indent=2, default=str)
    elif args.scenario:
        result = run_model(args.scenario)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2, default=str)
    else:
        # Default: run month-based model
        month = args.month or "Oct-27"
        result = run_model_for_month(month)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2, default=str)
