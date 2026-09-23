"""Shared, explainable thresholds for the AML analysis pipeline."""

# Role gates and confidence thresholds (TEAM_PLAN, section 7.1).
CONS_MIN_IN_DEG = 5
DIST_MIN_OUT_DEG = 10
COORD_MIN_KEY_LINKS = 3
TRANSIT_PT = (0.8, 1.2)
TERMINAL_PT_MAX = 0.1

# Dates have day resolution; these are day gaps, not hour windows.
FAST_DAYS = 2
CHRONO_GAPS = {"any": 31, "7d": 7, "2d": 2}
PATH_GAP_DAYS = 7
SYNC_MIN_PAYERS = 3
HHI_DOMINANT = 0.5

# Bounds and data visibility controls.
NEAR_THRESHOLD = (5000, 7000)
TRUNC_TERMINAL_MIN_P = 0.6
AMBIGUOUS_MARGIN = 0.10
PAYER_MAX_OUT_DEG = 2
PAYER_MAX_OUT_TX = 2
PAYER_MAX_KZT = 100_000
PAYER_TARGET_MIN_IN_DEG = 5
EXT_FUNDING_PT = 2.0
EXT_FUNDING_MAX_TRACKED_OUT = 0.10
AGG_MIN_IN_DEG = 10
AGG_MIN_ONE_OFF = 0.8
AGG_MAX_HHI = 0.15
AGG_MIN_ACTIVE_DAYS = 12

# Weighted priority components and counter-signal multipliers.
PRIORITY_WEIGHTS = {
    "role": 0.30,
    "money": 0.30,
    "brokerage": 0.20,
    "volume": 0.10,
    "temporal": 0.10,
}
ROLE_WEIGHT = {
    "coordinator": 1.0,
    "consolidator": 0.8,
    "distributor": 0.7,
    "transit": 0.5,
    "terminal": 0.3,
    "peripheral": 0.1,
    "payer": 0.05,
}
MULT = {
    "no_chrono": 0.5,
    "external_funding": 0.7,
    "seed": 0.6,
    "seed_above_bottom": 0.8,
    "payer": 0.2,
    "excluded": 0.0,
}
CONF_LEVELS = (0.5, 0.75)
TOP_N = 30
RANDOM_SEED = 42
