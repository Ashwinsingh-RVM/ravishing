"""
Goa DRS Reverse Logistics — Configuration & Assumptions
All parameters are tweakable. Sensitivity analysis will vary these.
"""

# ═══════════════════════════════════════════════════════════════
# 1. WAREHOUSE LOCATIONS (AA-operated, from PnL Model)
# ═══════════════════════════════════════════════════════════════
WAREHOUSES = {
    "Margao South": {
        "lat": 15.26208, "lon": 74.01871,
        "shed_sqm": 1200, "rent_lakhs": 2.5,
        "region": "South Goa"
    },
    "Cortalim": {
        "lat": 15.36944, "lon": 73.94835,
        "shed_sqm": 4500, "rent_lakhs": 11.4,
        "region": "South Goa - Central"
    },
    "Calangute North": {
        "lat": 15.56619, "lon": 73.76914,
        "shed_sqm": 800, "rent_lakhs": 2.1,
        "region": "North Goa - Tourist Belt"
    },
    "Mapusa North": {
        "lat": 15.63806, "lon": 73.82701,
        "shed_sqm": 2000, "rent_lakhs": 5.4,
        "region": "North Goa - Interior"
    },
    "Arambol": {
        "lat": 15.68436, "lon": 73.79556,
        "shed_sqm": 600, "rent_lakhs": 1.6,
        "region": "North Goa - Far North"
    },
}

# ═══════════════════════════════════════════════════════════════
# 2. FLEET TYPES — Actual vendor quotations
# ═══════════════════════════════════════════════════════════════
# Source: Vendor RFQ responses (Mar 2026)
# Cost model: Monthly quotation covers working_days × working_hrs × total_km
#   - Extra charges: per km beyond total_km, per hour beyond working_hrs
#   - daily_cost_inr derived from: monthly_quotation / working_days

FLEET_TYPES = {
    "Tata Ace": {
        "nominal_capacity_kg": 1000,
        "suitable_for": "narrow_streets",
        "speed_kmph_urban": 15,
        "speed_kmph_highway": 35,
        "unloading_time_min": 15,
        # Cost structure
        "working_days": 26,
        "total_km_monthly": 2600,
        "working_hrs_per_day": 12,
        "extra_km_rate_inr": 9,
        "extra_hr_rate_inr": 100,
        "monthly_quotation_inr": 73457,
        "daily_cost_inr": 2826,  # 73457 / 26
    },
    "Bolero Pickup": {
        "nominal_capacity_kg": 1500,
        "suitable_for": "narrow_streets",
        "speed_kmph_urban": 15,
        "speed_kmph_highway": 40,
        "unloading_time_min": 20,
        # Cost structure
        "working_days": 26,
        "total_km_monthly": 2600,
        "working_hrs_per_day": 12,
        "extra_km_rate_inr": 9,
        "extra_hr_rate_inr": 100,
        "monthly_quotation_inr": 75157,
        "daily_cost_inr": 2891,  # 75157 / 26
    },
    "Intra V50": {
        "nominal_capacity_kg": 2000,
        "suitable_for": "medium_streets",
        "speed_kmph_urban": 15,
        "speed_kmph_highway": 40,
        "unloading_time_min": 25,
        # Cost structure
        "working_days": 26,
        "total_km_monthly": 2600,
        "working_hrs_per_day": 12,
        "extra_km_rate_inr": 11,
        "extra_hr_rate_inr": 100,
        "monthly_quotation_inr": 81277,
        "daily_cost_inr": 3126,  # 81277 / 26
    },
    "Intra V70": {
        "nominal_capacity_kg": 2500,
        "suitable_for": "main_roads",
        "speed_kmph_urban": 12,
        "speed_kmph_highway": 40,
        "unloading_time_min": 30,
        # Cost structure
        "working_days": 26,
        "total_km_monthly": 2600,
        "working_hrs_per_day": 12,
        "extra_km_rate_inr": 11,
        "extra_hr_rate_inr": 100,
        "monthly_quotation_inr": 82127,
        "daily_cost_inr": 3159,  # 82127 / 26
    },
}

# ═══════════════════════════════════════════════════════════════
# 2b. VOLUMETRIC FILL WEIGHTS — kg of material that fills a 1T truck
# ═══════════════════════════════════════════════════════════════
# When a truck is completely filled with one material type, this is
# the actual weight (kg) that fits. Used to compute volumetric weight:
#   volumetric_factor = 1000 / fill_kg  (e.g., Glass: 1000/700 = 1.43)
#   volumetric_weight = actual_weight × volumetric_factor
# Truck is full when sum of volumetric weights >= nominal_capacity_kg
VOLUMETRIC_FILL_KG_PER_1T = {
    "Glass":      700,   # 700 kg of glass fills a 1T truck (confirmed)
    "PET":        350,   # Bulky plastic bottles — space-limited
    "HDPE":       400,   # Similar to PET, slightly denser
    "AL Cans":    250,   # Very bulky uncrushed cans
    "MLP":        200,   # Extremely light & bulky
    "Tetra Pack": 300,   # Light, somewhat compact
    "LD":         200,   # Very light & bulky like MLP
}

# ═══════════════════════════════════════════════════════════════
# 2c. ROAD DISTRIBUTION — % of routes by road type
# ═══════════════════════════════════════════════════════════════
ROAD_DISTRIBUTION = {
    "narrow_streets": 0.30,   # Tata Ace + Bolero Pickup
    "medium_streets": 0.45,   # Intra V50
    "main_roads": 0.25,       # Intra V70
}

# ═══════════════════════════════════════════════════════════════
# 3. VENDOR FLEET AVAILABILITY (from user data)
# ═══════════════════════════════════════════════════════════════
VENDORS = [
    {"name": "Moeving India", "tata_ace": 10, "1mt": 5, "1.5_2mt": 5, "3_5mt": 0, "status": "Pending"},
    {"name": "Instant Transport", "tata_ace": 15, "1mt": 7, "1.5_2mt": 5, "3_5mt": 3, "status": "Incomplete"},
    {"name": "Reliable Supply Chain", "tata_ace": 15, "1mt": 7, "1.5_2mt": 5, "3_5mt": 3, "status": "Completed"},
    {"name": "Shree Ajani Group", "tata_ace": 0, "1mt": 0, "1.5_2mt": 0, "3_5mt": 0, "status": "Completed"},
    {"name": "Hiram Transport", "tata_ace": 30, "1mt": 15, "1.5_2mt": 10, "3_5mt": 5, "status": "Completed"},
    {"name": "AAA Transport", "tata_ace": 0, "1mt": 0, "1.5_2mt": 0, "3_5mt": 0, "status": "Completed"},
    {"name": "Mars Highway", "tata_ace": 10, "1mt": 4, "1.5_2mt": 4, "3_5mt": 2, "status": "Completed"},
    {"name": "Vidhi International", "tata_ace": 10, "1mt": 4, "1.5_2mt": 4, "3_5mt": 2, "status": "Completed"},
    {"name": "Shree Radhe Travel", "tata_ace": 10, "1mt": 4, "1.5_2mt": 4, "3_5mt": 2, "status": "Completed"},
    {"name": "Swastik Group", "tata_ace": 0, "1mt": 0, "1.5_2mt": 0, "3_5mt": 0, "status": "Incomplete"},
    {"name": "Sanesh Fleet", "tata_ace": 30, "1mt": 15, "1.5_2mt": 10, "3_5mt": 5, "status": "Completed"},
    {"name": "Kashyap Transport", "tata_ace": 0, "1mt": 0, "1.5_2mt": 0, "3_5mt": 0, "status": "Pending"},
    {"name": "Sea Royal Logistics", "tata_ace": 10, "1mt": 4, "1.5_2mt": 4, "3_5mt": 2, "status": "Completed"},
    {"name": "DASS Green Solutions", "tata_ace": 10, "1mt": 5, "1.5_2mt": 5, "3_5mt": 0, "status": "Incomplete"},
    {"name": "Sachin Mali", "tata_ace": 0, "1mt": 0, "1.5_2mt": 0, "3_5mt": 0, "status": "Pending"},
    {"name": "Aapar Logistics", "tata_ace": 10, "1mt": 0, "1.5_2mt": 0, "3_5mt": 0, "status": "Completed"},
    {"name": "Odwen", "tata_ace": 10, "1mt": 5, "1.5_2mt": 5, "3_5mt": 0, "status": "Completed"},
]

# ═══════════════════════════════════════════════════════════════
# 4. MATERIAL CHARACTERISTICS (from PnL Model)
# ═══════════════════════════════════════════════════════════════
MATERIALS = {
    "PET":        {"market_cr_units": 44,  "weight_g": 23.2, "deposit_inr": 2.2},
    "HDPE":       {"market_cr_units": 15,  "weight_g": 25.0, "deposit_inr": 2.0},
    "MLP":        {"market_cr_units": 107, "weight_g": 4.9,  "deposit_inr": 1.0},
    "Glass":      {"market_cr_units": 27,  "weight_g": 250.0,"deposit_inr": 9.5},
    "AL Cans":    {"market_cr_units": 9,   "weight_g": 12.0, "deposit_inr": 5.0},
    "Tetra Pack": {"market_cr_units": 18,  "weight_g": 20.0, "deposit_inr": 1.0},
    "LD":         {"market_cr_units": 39,  "weight_g": 4.9,  "deposit_inr": 1.0},
}

# Total DRS-eligible market: 186.3 Cr units/year (from PnL), but total market is 259 Cr
TOTAL_MARKET_CR_UNITS = 259
DRS_ELIGIBLE_CR_UNITS = 186.3

# ═══════════════════════════════════════════════════════════════
# 5. RETURN RATES BY YEAR (from PnL Model)
# ═══════════════════════════════════════════════════════════════
RETURN_RATES = {
    "FY27": {"total": 0.40, "PET": 0.50, "Glass": 0.60, "HDPE": 0.40, "MLP": 0.30, "AL Cans": 0.45, "Tetra Pack": 0.30, "LD": 0.30},
    "FY28": {"total": 0.61, "PET": 0.65, "Glass": 0.70, "HDPE": 0.60, "MLP": 0.55, "AL Cans": 0.60, "Tetra Pack": 0.55, "LD": 0.55},
    "FY29": {"total": 0.72, "PET": 0.75, "Glass": 0.85, "HDPE": 0.70, "MLP": 0.65, "AL Cans": 0.70, "Tetra Pack": 0.65, "LD": 0.65},
    "FY30": {"total": 0.75, "PET": 0.80, "Glass": 0.85, "HDPE": 0.75, "MLP": 0.70, "AL Cans": 0.75, "Tetra Pack": 0.70, "LD": 0.70},
    "FY31": {"total": 0.80, "PET": 0.85, "Glass": 0.85, "HDPE": 0.80, "MLP": 0.75, "AL Cans": 0.80, "Tetra Pack": 0.75, "LD": 0.75},
}

# ═══════════════════════════════════════════════════════════════
# 6. HORECA-SPECIFIC ASSUMPTIONS (TWEAKABLE)
# ═══════════════════════════════════════════════════════════════

# What % of total returned quantity comes from HoReCa channel
HORECA_SHARE_OF_RETURNS = 0.35  # 35% — HoReCa is ~35% of total alcohol returns

# Pickup frequency distribution (% of HoReCas in each bucket)
PICKUP_FREQUENCY = {
    "daily":        0.20,    # 20% — high-volume bars, large restaurants
    "alternate":    0.30,    # 30% — medium restaurants, hotels
    "twice_weekly": 0.30,    # 30% — smaller restaurants, cafes
    "weekly":       0.20,    # 20% — guesthouses, homestays, low-volume
}

# Daily waste generation distribution (bottles/day per HoReCa)
# This varies by establishment type and size
WASTE_GENERATION = {
    # By HoReCa type
    "Bar":           {"mean": 80, "min": 30, "max": 200},
    "Restaurant":    {"mean": 25, "min": 5,  "max": 100},
    "Hotel":         {"mean": 40, "min": 10, "max": 150},
    "Resort":        {"mean": 60, "min": 20, "max": 200},
    "Beach Shack":   {"mean": 50, "min": 15, "max": 150},
    "Cafe":          {"mean": 10, "min": 2,  "max": 40},
    "Guesthouse":    {"mean": 8,  "min": 2,  "max": 30},
    "Homestay/Villa":{"mean": 5,  "min": 1,  "max": 20},
    "Lodging (Other)":{"mean": 5, "min": 1,  "max": 20},
    "Other":         {"mean": 5,  "min": 1,  "max": 15},
}

# Size tier multipliers (applied to waste generation)
SIZE_MULTIPLIERS = {
    "Large":   2.0,
    "Medium":  1.0,
    "Small":   0.5,
    "Micro":   0.25,
    "Unknown": 0.5,
}

# Material mix at HoReCa (what materials they generate)
# HoReCas are predominantly glass (alcohol bottles)
HORECA_MATERIAL_MIX = {
    "Glass":      0.65,   # 65% glass bottles (wine, beer, spirits)
    "PET":        0.15,   # 15% PET (water, soft drinks)
    "AL Cans":    0.10,   # 10% aluminium cans (beer cans)
    "HDPE":       0.03,
    "MLP":        0.02,
    "Tetra Pack": 0.03,
    "LD":         0.02,
}

# Average weight per bottle at HoReCa (weighted by glass-heavy mix)
AVG_BOTTLE_WEIGHT_G = sum(
    HORECA_MATERIAL_MIX[mat] * MATERIALS[mat]["weight_g"]
    for mat in MATERIALS
)  # ~175g average

# ═══════════════════════════════════════════════════════════════
# 7. OPERATIONAL PARAMETERS (TWEAKABLE)
# ═══════════════════════════════════════════════════════════════

# Pickup windows
PICKUP_WINDOWS = [
    {"name": "Morning", "start": "06:00", "end": "11:00", "hours": 5.0},
    {"name": "Evening", "start": "15:00", "end": "17:00", "hours": 2.0},
]
TOTAL_PICKUP_HOURS = sum(w["hours"] for w in PICKUP_WINDOWS)  # 7 hours

# Scanning at HoReCa
SCAN_RATE_PER_MIN = 20          # bottles per minute
AVG_SETUP_TIME_MIN = 3          # walk in, greet, set up scanner

# Travel parameters
ROAD_FACTOR = 1.4               # Actual road distance / straight-line distance
AVG_INTER_HORECA_DIST_KM = 1.5  # Average distance between consecutive HoReCas in a cluster
LAST_HORECA_TO_WAREHOUSE_KM = 15 # Average return distance (last stop → warehouse)

# Warehouse operations
WAREHOUSE_QUEUE_TIME_MIN = 10   # Average waiting time at warehouse (queuing)
# Unloading time is per fleet type (see FLEET_TYPES)

# Trips per day
MAX_TRIPS_PER_DAY = 2           # From PnL Model assumption

# Seasonality
PEAK_MONTHS = [10, 11, 12, 1, 2]  # Oct-Feb (Goa tourist season)
PEAK_FACTOR = 1.20              # +20%
NORMAL_FACTOR = 0.86            # -14%

# YoY growth
MARKET_GROWTH_YOY = 0.05        # 5%

# ═══════════════════════════════════════════════════════════════
# 8. ALCOHOL-SERVING FILTER
# ═══════════════════════════════════════════════════════════════
# Which alcohol signals to include for reverse logistics
ALCOHOL_SIGNALS_INCLUDE = ["Confirmed", "Likely", "Inferred"]
# This gives ~4,116 HoReCas. If we include "Possible" → ~10,600

# ═══════════════════════════════════════════════════════════════
# 9. MODEL SCENARIOS
# ═══════════════════════════════════════════════════════════════
SCENARIOS = {
    "conservative": {
        "label": "Conservative",
        "horeca_count_override": None,
        "waste_gen_percentile": 25,
        "pickup_freq_override": None,
        "return_rate_year": "FY27",
        "ptm_year": "FY27",
        "ptm_period": "normal",
    },
    "base": {
        "label": "Base Case",
        "horeca_count_override": None,
        "waste_gen_percentile": 50,
        "pickup_freq_override": None,
        "return_rate_year": "FY28",
        "ptm_year": "FY28",
        "ptm_period": "normal",
    },
    "aggressive": {
        "label": "Aggressive / Peak Season",
        "horeca_count_override": None,
        "waste_gen_percentile": 75,
        "pickup_freq_override": None,
        "return_rate_year": "FY29",
        "ptm_year": "FY29",
        "ptm_period": "peak",
    },
}

# ═══════════════════════════════════════════════════════════════
# 10. PUT TO MARKET — PnL Monthly Data (Cr units/month)
# ═══════════════════════════════════════════════════════════════
# Pattern: 7 normal months (Apr-Sep + Mar) + 5 peak months (Oct-Feb)
# Source: PnL Model DRS Put to Market schedule
PUT_TO_MARKET = {
    "FY27": {
        "normal": {"PET": 0.1, "HDPE": 0.0, "MLP": 0.0, "Glass": 1.7, "AL Cans": 0.2, "Tetra Pack": 0.0, "LD": 0.0},
        "peak":   {"PET": 0.2, "HDPE": 0.0, "MLP": 0.0, "Glass": 2.4, "AL Cans": 0.22, "Tetra Pack": 0.0, "LD": 0.0},
        "ramp_months": 2,  # Apr-May are 0 (DRS not yet launched)
    },
    "FY28": {
        "normal": {"PET": 2.7, "HDPE": 1.1, "MLP": 4.7, "Glass": 2.0, "AL Cans": 0.7, "Tetra Pack": 1.3, "LD": 2.3},
        "peak":   {"PET": 3.8, "HDPE": 1.5, "MLP": 6.5, "Glass": 2.8, "AL Cans": 0.9, "Tetra Pack": 1.8, "LD": 3.2},
    },
    "FY29": {
        "normal": {"PET": 2.9, "HDPE": 1.1, "MLP": 4.9, "Glass": 2.1, "AL Cans": 0.7, "Tetra Pack": 1.3, "LD": 2.4},
        "peak":   {"PET": 4.0, "HDPE": 1.6, "MLP": 6.8, "Glass": 2.9, "AL Cans": 1.0, "Tetra Pack": 1.9, "LD": 3.4},
    },
    "FY30": {
        "normal": {"PET": 3.0, "HDPE": 1.2, "MLP": 5.1, "Glass": 2.2, "AL Cans": 0.7, "Tetra Pack": 1.4, "LD": 2.5},
        "peak":   {"PET": 4.2, "HDPE": 1.6, "MLP": 7.2, "Glass": 3.1, "AL Cans": 1.0, "Tetra Pack": 2.0, "LD": 3.6},
    },
    "FY31": {
        "normal": {"PET": 3.1, "HDPE": 1.2, "MLP": 5.4, "Glass": 2.3, "AL Cans": 0.8, "Tetra Pack": 1.5, "LD": 2.7},
        "peak":   {"PET": 4.4, "HDPE": 1.7, "MLP": 7.5, "Glass": 3.2, "AL Cans": 1.1, "Tetra Pack": 2.1, "LD": 3.7},
    },
}

# ═══════════════════════════════════════════════════════════════
# 11. HORECA CONSUMPTION SHARE OF TOTAL PUT-TO-MARKET
# ═══════════════════════════════════════════════════════════════
# Flat 50% assumption: half of all DRS universe flows through HoReCa channel
# Applied uniformly across all materials (simpler, validated with PnL team)
HORECA_SHARE_OF_RETURNS = 0.50

# Per-material shares kept for backward compatibility but defaulting to flat rate
HORECA_CONSUMPTION_SHARE = {
    "Glass":      0.50,
    "AL Cans":    0.50,
    "PET":        0.50,
    "Tetra Pack": 0.50,
    "HDPE":       0.50,
    "MLP":        0.50,
    "LD":         0.50,
}

# ═══════════════════════════════════════════════════════════════
# 11b. PNL CSV DATA SOURCE
# ═══════════════════════════════════════════════════════════════
# PTM data is read from this CSV (exported from PnL Google Sheet MoM tab)
# If file exists, it overrides the hardcoded PUT_TO_MARKET above
import os as _os
PNL_CSV_PATH = _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)),
    "data",
    "pnl.csv"
)

# ═══════════════════════════════════════════════════════════════
# 12. CALIBRATION CONTROLS
# ═══════════════════════════════════════════════════════════════
# If calibrated avg per HoReCa exceeds this, auto-include "Possible" alcohol signal
CALIBRATION_REASONABLENESS_THRESHOLD = 150  # bottles/day per HoReCa
# Original WASTE_GENERATION above is kept as relative weight ratios between types
# Actual magnitudes are overridden by PTM calibration
