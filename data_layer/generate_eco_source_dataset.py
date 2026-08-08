"""
generate_eco_source_dataset.py
==============================

Generates realistic PLC-controlled telecom-site time-series telemetry for the
"Eco-Source Optimizer" Week-2 MVP backend + rule-based optimizer.

System spec (see accompanying plan):
  - Battery bank: 24 V DC nominal LFP (Lithium Iron Phosphate), 8S configuration.
  - Pack capacity: 300 Ah usable (7.68 kWh @ 25.6 V).
  - Region: Pakistan grid, 50 Hz nominal, 230 V single-phase site feed.
  - Timezone: Asia/Karachi (UTC+05:00), ISO-8601 timestamps.

Stress scenarios are injected via deterministic schedules (grid-outage windows,
grid-flap windows, generator fuel depletion) so the Week-2 rule engine can be
validated against low-SoC blocks, grid instability, low fuel, frequent switching,
stale timestamps and manual overrides.

Output:
  - eco_source_telemetry.csv          (11,520 rows: 4 sites x 30 days x 15-min)

Run:
    python generate_eco_source_dataset.py
"""

import csv
import math
import random
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 20250729
random.seed(SEED)

# ---------------------------------------------------------------------------
# Global constants (documented in the data dictionary)
# ---------------------------------------------------------------------------
TZ = timezone(timedelta(hours=5))          # Asia/Karachi (UTC+05:00)
START = datetime(2025, 1, 1, 0, 0, 0, tzinfo=TZ)
INTERVAL_MIN = 15
INTERVAL_H = INTERVAL_MIN / 60.0
DAYS = 30
ROWS_PER_SITE = int(DAYS * 24 * 60 / INTERVAL_MIN)   # 2880
TICKS_PER_DAY = int(24 * 60 / INTERVAL_MIN)          # 96

# Battery pack (24 V LFP 8S)
PACK_CAPACITY_AH = 300.0
R_INTERNAL = 0.010                          # ohms, pack internal resistance
V_MIN = 20.0                                # 0% safe cutoff
V_MAX = 29.2                                # 100% full/float
C_RATE_MAX_A = 150.0                        # 0.5C magnitude limit
CHARGE_CAP_KW = 3.0                         # inverter/charger charge power cap

# Safety thresholds (align with data_layer/safety_thresholds.yaml intent)
CRITICAL_SOC = 20.0                         # hard discharge floor (24 V cutoff)
LOW_SOC = 30.0                              # low battery warning / de-preference
GEN_STOP_SOC = 80.0                         # generator hysteresis upper bound
LOW_FUEL = 15.0                             # low generator fuel warning
THERMAL_RISK_C = 45.0                       # battery thermal-risk threshold

# Generator fuel tank
FUEL_TANK_L = 100.0

# Tariff (NEPRA-style time-of-use)
PEAK_START_HOUR = 18
PEAK_END_HOUR = 22                          # peak = [18:00, 22:00)
PRICE_OFFPEAK = 22.0                        # PKR/kWh base
PRICE_PEAK = 55.0                           # PKR/kWh base

# 24 V LFP (8S) open-circuit-voltage vs SoC curve (held constant everywhere)
OCV_SOC = [0, 10, 20, 40, 60, 80, 95, 100]
OCV_V = [20.0, 24.8, 25.6, 26.0, 26.4, 26.6, 27.2, 29.2]

COLUMNS = [
    "site_id", "timestamp", "tower_load_kw", "solar_power_kw", "solar_irradiance",
    "battery_soc", "battery_health", "battery_status", "battery_voltage",
    "battery_current", "battery_temperature", "grid_available", "grid_power_kw",
    "grid_voltage", "grid_frequency_hz", "electricity_price", "tariff_type",
    "generator_available", "generator_status", "generator_power_kw", "fuel_level",
    "fuel_consumption_lph", "temperature", "humidity", "wind_speed", "rainfall",
    "energy_consumption_kwh", "power_source", "equipment_status",
]

# ---------------------------------------------------------------------------
# Site profiles
# ---------------------------------------------------------------------------
SITES = {
    "SITE_001": {  # solar-rich baseline, stable grid
        "solar_kwp": 6.0, "load_base": 2.5, "load_amp": 0.8,
        "n_outages": 6, "outage_dur": (2, 8), "n_flaps": 3, "flap_dur": (6, 12),
        "grid_instab_prob": 0.004, "refuel_days": 14,
        "tmean": 25.0, "tamp": 8.0, "soh": 98.0, "gen_fault_prob": 0.0006,
        "soc0": 85.0, "fuel0": 90.0, "deep_discharge": [],
    },
    "SITE_002": {  # grid-unstable site
        "solar_kwp": 3.0, "load_base": 2.0, "load_amp": 0.7,
        "n_outages": 42, "outage_dur": (4, 24), "n_flaps": 14, "flap_dur": (8, 14),
        "grid_instab_prob": 0.06, "refuel_days": 8,
        "tmean": 28.0, "tamp": 9.0, "soh": 88.0, "gen_fault_prob": 0.0015,
        "soc0": 70.0, "fuel0": 85.0, "deep_discharge": [],
    },
    "SITE_003": {  # generator-dependent, weak/absent grid, small solar
        "solar_kwp": 2.0, "load_base": 1.5, "load_amp": 0.5,
        "n_outages": 60, "outage_dur": (6, 52), "n_flaps": 12, "flap_dur": (8, 14),
        "grid_instab_prob": 0.03, "refuel_days": 22,
        "tmean": 30.0, "tamp": 10.0, "soh": 82.0, "gen_fault_prob": 0.0025,
        "soc0": 60.0, "fuel0": 32.0,
        # deep-discharge events: (start_tick, duration_ticks) with grid outage
        # AND generator lockout -> battery driven to the 24 V critical floor.
        "deep_discharge": [(900, 48), (2100, 40)],
    },
    "SITE_004": {  # well-behaved baseline, mostly grid + solar
        "solar_kwp": 4.0, "load_base": 2.2, "load_amp": 0.7,
        "n_outages": 8, "outage_dur": (2, 10), "n_flaps": 4, "flap_dur": (6, 12),
        "grid_instab_prob": 0.008, "refuel_days": 14,
        "tmean": 24.0, "tamp": 7.0, "soh": 95.0, "gen_fault_prob": 0.0008,
        "soc0": 80.0, "fuel0": 90.0, "deep_discharge": [],
    },
}


# ---------------------------------------------------------------------------
# Physics / helper functions
# ---------------------------------------------------------------------------
def ocv_from_soc(soc):
    """Interpolate open-circuit pack voltage from SoC using the 24 V LFP curve."""
    soc = max(0.0, min(100.0, soc))
    for i in range(len(OCV_SOC) - 1):
        lo, hi = OCV_SOC[i], OCV_SOC[i + 1]
        if lo <= soc <= hi:
            frac = (soc - lo) / (hi - lo) if hi > lo else 0.0
            return OCV_V[i] + frac * (OCV_V[i + 1] - OCV_V[i])
    return OCV_V[-1]


def terminal_voltage(soc, current_a):
    """Terminal voltage = OCV(SoC) + I*R_internal, clamped to curve bounds."""
    v = ocv_from_soc(soc) + current_a * R_INTERNAL
    return max(V_MIN, min(V_MAX, v))


def solar_generation(hour_frac, kwp, rain_mm, cloud):
    """Bell-curve solar generation scaled by irradiance and derated by weather.

    Returns (solar_power_kw, irradiance_wm2). Zero outside daylight (06:00-18:00).
    """
    if hour_frac < 6.0 or hour_frac > 18.0:
        return 0.0, 0.0
    bell = max(0.0, math.sin(math.pi * (hour_frac - 6.0) / 12.0))
    clear_irr = 1050.0 * bell                     # up to ~1050 W/m2 clear sky
    rain_derate = max(0.35, 1.0 - rain_mm / 30.0)
    cloud_derate = 1.0 - cloud
    irradiance = max(0.0, min(1200.0, clear_irr * cloud_derate * rain_derate))
    power = max(0.0, min(kwp, kwp * (irradiance / 1000.0)))
    return power, irradiance


def ambient_temperature(hour_frac, tmean, tamp):
    """Diurnal ambient: min ~05:00, max ~15:00."""
    return tmean + tamp * math.sin(2 * math.pi * (hour_frac - 9.0) / 24.0)


def tariff_for_hour(hour):
    return "peak" if PEAK_START_HOUR <= hour < PEAK_END_HOUR else "off_peak"


def fuel_burn_lph(gen_power_kw):
    """OEM-style diesel burn curve: baseline + load term."""
    if gen_power_kw <= 0:
        return 0.0
    return 0.5 + 0.32 * gen_power_kw               # ~0.5 idle .. ~3.1 @ 8 kW


def alternate_safe_source(chosen, solar_ok, grid_ok, batt_ok, gen_ok):
    """Pick a different SAFE source for manual-override simulation."""
    options = []
    if solar_ok:
        options.append("solar")
    if grid_ok:
        options.append("grid")
    if batt_ok:
        options.append("battery")
    if gen_ok:
        options.append("generator")
    options = [o for o in options if o != chosen]
    return random.choice(options) if options else None


# ---------------------------------------------------------------------------
# Deterministic stress schedules
# ---------------------------------------------------------------------------
def build_schedules(cfg, rng):
    """Return (outage[], flap[], gen_lockout[]) arrays over the timeline."""
    outage = [False] * ROWS_PER_SITE
    flap = [False] * ROWS_PER_SITE
    gen_lockout = [False] * ROWS_PER_SITE
    for _ in range(cfg["n_outages"]):
        start = rng.randint(0, ROWS_PER_SITE - 1)
        dur = rng.randint(*cfg["outage_dur"])
        for k in range(start, min(ROWS_PER_SITE, start + dur)):
            outage[k] = True
    for _ in range(cfg["n_flaps"]):
        start = rng.randint(0, ROWS_PER_SITE - 1)
        dur = rng.randint(*cfg["flap_dur"])
        for k in range(start, min(ROWS_PER_SITE, start + dur)):
            flap[k] = True
            outage[k] = False                    # flap needs the grid to return
    # deep-discharge events: grid outage + generator lockout together
    for start, dur in cfg.get("deep_discharge", []):
        for k in range(start, min(ROWS_PER_SITE, start + dur)):
            outage[k] = True
            flap[k] = False
            gen_lockout[k] = True
    return outage, flap, gen_lockout


# ---------------------------------------------------------------------------
# Per-site simulation
# ---------------------------------------------------------------------------
def simulate_site(site_id, cfg):
    rng = random.Random(hash((SEED, site_id)) & 0xFFFFFFFF)
    outage, flap, gen_lockout = build_schedules(cfg, rng)

    rows = []
    override_idx = set()
    stale_idx = set()
    refuel_idx = set()

    soc = cfg["soc0"]
    soh = cfg["soh"]
    fuel = cfg["fuel0"]
    gen_latch = False
    cloud = rng.uniform(0.0, 0.4)
    rain_timer = 0
    rain_intensity = 0.0
    recent_sources = []
    last_timestamp = None

    for i in range(ROWS_PER_SITE):
        ts = START + timedelta(minutes=INTERVAL_MIN * i)

        # ---- staleness injection (~2%): repeat previous timestamp ---------
        stale = (rng.random() < 0.02) and (last_timestamp is not None)
        if stale:
            ts_out = last_timestamp
            stale_idx.add(i)
        else:
            ts_out = ts
            last_timestamp = ts
        # tariff/price derived from the EMITTED timestamp (internal consistency)
        hour = ts_out.hour
        hour_frac = ts_out.hour + ts_out.minute / 60.0

        # ---- scheduled refuel (fuel steps up only here) -------------------
        if i > 0 and i % (cfg["refuel_days"] * TICKS_PER_DAY) == 0:
            fuel = round(rng.uniform(92.0, 98.0), 1)
            refuel_idx.add(i)

        # ---- weather ------------------------------------------------------
        cloud = max(0.0, min(0.6, cloud + rng.uniform(-0.08, 0.08)))
        if rain_timer > 0:
            rain_timer -= 1
            rainfall = round(max(0.0, rain_intensity + rng.uniform(-2, 2)), 2)
        else:
            rainfall = 0.0
            if rng.random() < 0.01:
                rain_timer = rng.randint(2, 8)
                rain_intensity = rng.uniform(2, 30)
        temp = ambient_temperature(hour_frac, cfg["tmean"], cfg["tamp"])
        temp += rng.uniform(-1.0, 1.0)
        # Relative humidity: inversely tracks the diurnal temperature swing so
        # it breathes naturally between ~60% (hot afternoons) and ~95% (cool,
        # humid nights). 100% is reserved for heavy-rain / saturated air.
        humidity = 74.0 - (temp - cfg["tmean"]) * 1.7 + rng.uniform(-6.0, 6.0)
        if rainfall > 0.0:
            humidity += min(18.0, rainfall * 1.1)      # damp air during rain
        humidity = max(45.0, min(100.0, humidity))
        wind = max(0.0, min(25.0, abs(rng.gauss(4.5, 3.0))))


        # ---- load ---------------------------------------------------------
        diurnal = cfg["load_amp"] * math.sin(2 * math.pi * (hour_frac - 8.0) / 24.0)
        load = max(0.6, cfg["load_base"] + diurnal + rng.uniform(-0.15, 0.15))

        # ---- solar --------------------------------------------------------
        solar_kw, irradiance = solar_generation(hour_frac, cfg["solar_kwp"],
                                                 rainfall, cloud)

        # ---- grid state ---------------------------------------------------
        if flap[i]:
            grid_available = (i % 2 == 0)          # toggles each tick
            grid_unstable = False
        elif outage[i]:
            grid_available = False
            grid_unstable = False
        else:
            grid_available = True
            grid_unstable = rng.random() < cfg["grid_instab_prob"]

        if not grid_available:
            grid_voltage, grid_freq = 0.0, 0.0
        elif grid_unstable:
            if rng.random() < 0.5:                 # sag
                grid_voltage = round(rng.uniform(198.0, 216.0), 1)
                grid_freq = round(rng.uniform(49.3, 49.7), 2)
            else:                                   # swell (rare high excursion)
                grid_voltage = round(rng.uniform(244.0, 258.0), 1)
                grid_freq = round(rng.uniform(50.3, 50.8), 2)
        else:
            # Healthy feed: tight band, most readings 220-240 V / 49.8-50.2 Hz.
            grid_voltage = round(min(240.0, max(220.0, rng.gauss(230.0, 3.5))), 1)
            grid_freq = round(min(50.2, max(49.8, rng.gauss(50.0, 0.07))), 2)


        grid_ok = grid_available and not grid_unstable

        # ---- generator availability --------------------------------------
        gen_fault = rng.random() < cfg["gen_fault_prob"]
        gen_locked = gen_lockout[i]              # deep-discharge lockout window
        gen_available = (fuel > 0.0) and (not gen_fault) and (not gen_locked)

        # ---- tariff / price ----------------------------------------------
        tariff = tariff_for_hour(hour)
        if tariff == "peak":
            price = round(PRICE_PEAK + rng.uniform(-4, 6), 2)
        else:
            price = round(PRICE_OFFPEAK + rng.uniform(-3, 4), 2)

        # ---- cheapest-SAFE-source decision (ground truth) ----------------
        solar_ok = solar_kw >= load
        if solar_ok:
            source = "solar"
            gen_latch = False
        elif grid_ok:
            # peak-shave: prefer stored energy during expensive peak if healthy
            source = "battery" if (tariff == "peak" and soc > 55.0) else "grid"
            gen_latch = False
        else:
            # island mode: grid down or unstable, solar can't cover load
            if gen_latch and gen_available and soc < GEN_STOP_SOC:
                source = "generator"
            elif soc > LOW_SOC:
                source = "battery"
                gen_latch = False
            elif gen_available:
                source = "generator"
                gen_latch = True
            else:
                source = "battery"                 # emergency / forced fallback
                gen_latch = False
            if soc >= GEN_STOP_SOC:
                gen_latch = False

        # ---- manual override injection (~1%) -----------------------------
        batt_ok = soc > CRITICAL_SOC
        if rng.random() < 0.01:
            alt = alternate_safe_source(source, solar_ok, grid_ok, batt_ok,
                                        gen_available)
            if alt is not None:
                source = alt
                override_idx.add(i)

        # ---- energy balance / battery ------------------------------------
        gen_power = 0.0
        grid_power = 0.0
        # Charge power tapers as the pack fills (bulk -> absorption -> float),
        # so a healthy pack settles into a realistic 98-99.5% float band
        # instead of being pinned at exactly 100%.
        if soc < 90:
            charge_headroom_kw = CHARGE_CAP_KW
        elif soc < 97:
            charge_headroom_kw = 1.0
        elif soc < 99:
            charge_headroom_kw = 0.25
        else:
            charge_headroom_kw = 0.0

        if source == "solar":
            surplus = solar_kw - load
            if surplus > 0:
                net_batt_kw = min(surplus, charge_headroom_kw)
            else:
                net_batt_kw = max(-CHARGE_CAP_KW, surplus)
        elif source == "grid":
            grid_power = load + charge_headroom_kw
            net_batt_kw = charge_headroom_kw
        elif source == "generator":
            gen_power = load + charge_headroom_kw
            net_batt_kw = charge_headroom_kw
        else:  # battery
            net_batt_kw = -load
            # Protective low-voltage load-shed: outside a genuine emergency
            # (deep-discharge lockout) the BMS sheds load near the ~15% floor
            # instead of cratering to 0%. Telecom banks rarely go below 15-20%.
            if soc <= 16.0 and not gen_locked:
                net_batt_kw = 0.0


        ocv = ocv_from_soc(soc)
        current = net_batt_kw * 1000.0 / ocv
        current = max(-C_RATE_MAX_A, min(C_RATE_MAX_A, current))
        soc += current * INTERVAL_H / PACK_CAPACITY_AH * 100.0
        soc = max(0.0, min(100.0, soc))

        batt_voltage = terminal_voltage(soc, current)

        # battery temperature: ambient baseline + heating from |current|
        batt_temp = temp + 0.13 * abs(current) + rng.uniform(-0.5, 0.5)
        batt_temp = max(temp - 2.0, min(60.0, batt_temp))

        if batt_temp > THERMAL_RISK_C:
            batt_status = "fault"
        elif current > 2.0:
            batt_status = "charging"
        elif current < -2.0:
            batt_status = "discharging"
        else:
            batt_status = "idle"

        # ---- generator run-state + fuel update ---------------------------
        if source == "generator":
            gen_status = "running"
            lph = fuel_burn_lph(gen_power)
            fuel = max(0.0, fuel - (lph * INTERVAL_H) / FUEL_TANK_L * 100.0)
        elif gen_fault:
            gen_status = "fault"
            lph = 0.0
        else:
            gen_status = "stopped"
            lph = 0.0

        # ---- frequent-switching detection --------------------------------
        recent_sources.append(source)
        if len(recent_sources) > 4:
            recent_sources.pop(0)
        switches = sum(1 for a, b in zip(recent_sources, recent_sources[1:])
                       if a != b)
        frequent_switching = switches >= 3

        # ---- equipment_status derivation (priority ordered) --------------
        if stale:
            equip = "fault"
        elif soc <= CRITICAL_SOC:
            equip = "fault"
        elif batt_temp > THERMAL_RISK_C:
            equip = "fault"
        elif gen_status == "fault":
            equip = "fault"
        elif soc <= LOW_SOC:
            equip = "warning"
        elif fuel < LOW_FUEL:
            equip = "warning"
        elif grid_unstable:
            equip = "warning"
        elif frequent_switching:
            equip = "warning"
        else:
            equip = "ok"

        soh = max(70.0, soh - 0.00002 * abs(current))

        rows.append({
            "site_id": site_id,
            "timestamp": ts_out.isoformat(),
            "tower_load_kw": round(load, 3),
            "solar_power_kw": round(solar_kw, 3),
            "solar_irradiance": round(irradiance, 1),
            "battery_soc": round(soc, 2),
            "battery_health": round(soh, 2),
            "battery_status": batt_status,
            "battery_voltage": round(batt_voltage, 2),
            "battery_current": round(current, 2),
            "battery_temperature": round(batt_temp, 2),
            "grid_available": str(grid_available).lower(),
            "grid_power_kw": round(grid_power, 3),
            "grid_voltage": round(grid_voltage, 1),
            "grid_frequency_hz": round(grid_freq, 2),
            "electricity_price": round(price, 2),
            "tariff_type": tariff,
            "generator_available": str(gen_available).lower(),
            "generator_status": gen_status,
            "generator_power_kw": round(gen_power, 3),
            "fuel_level": round(fuel, 2),
            "fuel_consumption_lph": round(lph, 3),
            "temperature": round(temp, 2),
            "humidity": round(humidity, 1),
            "wind_speed": round(wind, 2),
            "rainfall": round(rainfall, 2),
            "energy_consumption_kwh": round(load * INTERVAL_H, 4),
            "power_source": source,
            "equipment_status": equip,
        })

    return rows, override_idx, stale_idx, refuel_idx


# ---------------------------------------------------------------------------
# Self-validation
# ---------------------------------------------------------------------------
def validate(all_rows, overrides, stales, refuels):
    errors = []
    counts = {
        "low_soc_block": 0, "stale": 0, "grid_instability": 0,
        "low_fuel": 0, "frequent_switching": 0, "manual_override": 0,
    }
    n = len(all_rows)

    # per-site ordered structure for switching detection
    per_site = {}
    for row in all_rows:
        per_site.setdefault(row["site_id"], []).append(row)

    for row in all_rows:
        site = row["site_id"]
        dt = datetime.fromisoformat(row["timestamp"])
        h = dt.hour + dt.minute / 60.0
        # 1. night solar must be zero
        if (h < 6.0 or h > 18.0) and (row["solar_power_kw"] > 0
                                      or row["solar_irradiance"] > 0):
            errors.append(f"{site} {row['timestamp']}: solar > 0 at night")
        # 2. SoC bounds
        if not (0.0 <= row["battery_soc"] <= 100.0):
            errors.append(f"{site}: SoC out of range {row['battery_soc']}")
        # 3. voltage bounds + curve consistency
        v = row["battery_voltage"]
        if not (V_MIN <= v <= V_MAX):
            errors.append(f"{site}: voltage out of range {v}")
        exp_v = terminal_voltage(row["battery_soc"], row["battery_current"])
        if abs(v - exp_v) > 0.35:
            errors.append(f"{site}: voltage {v} off curve (exp {exp_v:.2f})")
        # 4. no negative kW
        for col in ("tower_load_kw", "solar_power_kw", "grid_power_kw",
                    "generator_power_kw", "energy_consumption_kwh"):
            if row[col] < 0:
                errors.append(f"{site}: negative {col}={row[col]}")
        # 5. current magnitude
        if abs(row["battery_current"]) > C_RATE_MAX_A + 0.01:
            errors.append(f"{site}: |current| exceeds C-rate")
        # 6. generator consistency
        if row["generator_status"] != "running" and (
                row["generator_power_kw"] > 0 or row["fuel_consumption_lph"] > 0):
            errors.append(f"{site}: gen output while not running")
        # 7. grid consistency
        if row["grid_available"] == "false" and row["grid_power_kw"] > 0:
            errors.append(f"{site}: grid power while unavailable")
        # 8. tariff/price consistency (against emitted timestamp)
        if row["tariff_type"] != tariff_for_hour(dt.hour):
            errors.append(f"{site} {row['timestamp']}: tariff mismatch")
        # 9. price band matches tariff
        if row["tariff_type"] == "peak" and row["electricity_price"] < 40:
            errors.append(f"{site}: peak price too low {row['electricity_price']}")
        if row["tariff_type"] == "off_peak" and row["electricity_price"] > 40:
            errors.append(f"{site}: off-peak price too high")
        # 10. fuel bounds
        if not (0.0 <= row["fuel_level"] <= 100.0):
            errors.append(f"{site}: fuel out of range {row['fuel_level']}")

        # scenario counting
        if row["battery_soc"] <= CRITICAL_SOC:
            counts["low_soc_block"] += 1
        if row["fuel_level"] < LOW_FUEL:
            counts["low_fuel"] += 1
        if row["grid_available"] == "false" or (
                row["grid_available"] == "true" and (
                    row["grid_frequency_hz"] < 49.5
                    or row["grid_frequency_hz"] > 50.5
                    or row["grid_voltage"] < 210 or row["grid_voltage"] > 245)):
            counts["grid_instability"] += 1

    # monotonic-fuel check + frequent-switching per site
    for site, rws in per_site.items():
        refuel_set = refuels.get(site, set())
        for idx in range(1, len(rws)):
            a, b = rws[idx - 1], rws[idx]
            # fuel may only rise on a scheduled refuel tick
            if b["fuel_level"] > a["fuel_level"] + 0.01 and idx not in refuel_set:
                errors.append(f"{site}: fuel rose without refuel "
                              f"{a['fuel_level']}->{b['fuel_level']}")
        window = []
        for r in rws:
            window.append(r["power_source"])
            if len(window) > 4:
                window.pop(0)
            sw = sum(1 for x, y in zip(window, window[1:]) if x != y)
            if sw >= 3:
                counts["frequent_switching"] += 1

    counts["stale"] = sum(len(s) for s in stales.values())
    counts["manual_override"] = sum(len(o) for o in overrides.values())
    return errors, counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    all_rows = []
    overrides, stales, refuels = {}, {}, {}
    for site_id, cfg in SITES.items():
        rows, ov, st, rf = simulate_site(site_id, cfg)
        all_rows.extend(rows)
        overrides[site_id] = ov
        stales[site_id] = st
        refuels[site_id] = rf
        print(f"  generated {len(rows):5d} rows for {site_id}")

    out_csv = "eco_source_telemetry.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows -> {out_csv}")

    errors, counts = validate(all_rows, overrides, stales, refuels)
    n = len(all_rows)
    print("\n--- SELF-VALIDATION ---")
    if errors:
        print(f"FAILED: {len(errors)} issues. First 10:")
        for e in errors[:10]:
            print("   ", e)
    else:
        print("PASSED: no orphaned dependencies / impossible values detected.")

    print("\n--- SCENARIO COVERAGE (share of rows) ---")
    for k, c in counts.items():
        print(f"  {k:22s}: {c:6d}  ({100.0 * c / n:5.2f}%)")

    dist = {}
    for r in all_rows:
        dist[r["power_source"]] = dist.get(r["power_source"], 0) + 1
    print("\n--- power_source distribution ---")
    for k, c in sorted(dist.items()):
        print(f"  {k:10s}: {c:6d}  ({100.0 * c / n:5.2f}%)")

    eq = {}
    for r in all_rows:
        eq[r["equipment_status"]] = eq.get(r["equipment_status"], 0) + 1
    print("\n--- equipment_status distribution ---")
    for k, c in sorted(eq.items()):
        print(f"  {k:10s}: {c:6d}  ({100.0 * c / n:5.2f}%)")


if __name__ == "__main__":
    main()
