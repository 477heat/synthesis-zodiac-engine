#Engine 1.3
import json
import os
from datetime import datetime

# 1. Load JSON Data (zodiac signs + interactions + templates)

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
WESTERN_JSON_PATH = os.path.join(DATA_DIR, 'western_zodiac.json')
CHINESE_JSON_PATH = os.path.join(DATA_DIR, 'chinese_zodiac.json')

BASE_DIR = os.path.dirname(__file__)
ELEMENT_INTERACTIONS_PATH = os.path.join(BASE_DIR, 'element_interactions.json')
STAT_TEMPLATES_PATH = os.path.join(BASE_DIR, 'stat_templates.json')

def load_json_data(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# Pre-load all data globally for warm Lambda containers
raw_west = load_json_data(WESTERN_JSON_PATH)
raw_chin = load_json_data(CHINESE_JSON_PATH)
WESTERN_ZODIAC = raw_west.get('western_zodiac', [])
CHINESE_ZODIAC = raw_chin.get('chinese_zodiac', [])

ELEMENT_INTERACTIONS = load_json_data(ELEMENT_INTERACTIONS_PATH)
STAT_TEMPLATES = load_json_data(STAT_TEMPLATES_PATH)

# Extract needed sub‑structures
HARMONY_MAP = ELEMENT_INTERACTIONS.get('harmony_map', {})
CLASH_MAP = ELEMENT_INTERACTIONS.get('clash_map', {})
HARMONY_MULTIPLIER = ELEMENT_INTERACTIONS.get('harmony_multiplier', 1.2)
CONTRADICTORY_MODIFIERS = ELEMENT_INTERACTIONS.get('contradictory_modifiers', {})

ELEMENT_WEIGHT_BONUSES = STAT_TEMPLATES.get('element_weight_bonuses', {})
STAT_CAP = STAT_TEMPLATES.get('stat_cap', 750)

# --------------------------------------------------------------------
# 2. Core Resolution Functions
# --------------------------------------------------------------------
def resolve_western_sign(dob_date):
    """Resolve Western sign/cusp from JSON (unchanged)."""
    month_day = dob_date.strftime("%m-%d")
    # Cusp check first
    for entry in WESTERN_ZODIAC:
        if entry.get('type') == 'cusp':
            start_md = entry['start']
            end_md = entry['end']
            if start_md <= end_md:
                if start_md <= month_day <= end_md:
                    return entry
            else:
                if month_day >= start_md or month_day <= end_md:
                    return entry
    # Regular sign check
    for entry in WESTERN_ZODIAC:
        if entry.get('type') == 'sign':
            start_md = entry['start']
            end_md = entry['end']
            if start_md <= end_md:
                if start_md <= month_day <= end_md:
                    return entry
            else:
                if month_day >= start_md or month_day <= end_md:
                    return entry
    raise ValueError(f"No Western sign/cusp found for {month_day}")

def resolve_chinese_sign(dob_date):
    """Resolve Chinese zodiac from JSON using date ranges."""
    for entry in CHINESE_ZODIAC:
        for dr in entry.get('date_ranges', []):
            start_date = datetime.strptime(dr['start'], "%Y-%m-%d").date()
            end_date = datetime.strptime(dr['end'], "%Y-%m-%d").date()
            if start_date <= dob_date <= end_date:
                return entry
    raise ValueError(f"No Chinese zodiac found for {dob_date}")

def calculate_age_and_badge(dob_date, current_date):
    """Calculate age and assign mastery badge per spec ranges."""
    age = current_date.year - dob_date.year - (
        (current_date.month, current_date.day) < (dob_date.month, dob_date.day)
    )
    if age < 1:
        badge = "Tiro"
    elif 6 <= age < 12:
        badge = "Abecedarian"
    elif 13 <= age < 20:
        badge = "Discipulus"
    elif 21 <= age < 33:
        badge = "Scholaris"
    elif 34 <= age < 45:
        badge = "Adeptus"
    elif 45 <= age < 60:
        badge = "Magister"
    elif 61 <= age < 105:
        badge = "Laureatus"
    else:
        badge = "Corpus Exanime"
    return age, badge

def calculate_synergy(western_element, chinese_element):
    """
    Evaluate synergy using element_interactions.json.
    Returns: {
        'stance': 'Harmonious' | 'Contradictory' | 'Balanced',
        'multiplier': float,  # global multiplier for base stats
        'contradictory_mods': dict | None  # per‑stat multipliers if contradictory
    }
    """
    if not western_element or not chinese_element:
        return {"stance": "Balanced", "multiplier": 1.0, "contradictory_mods": None}

    w_elem = western_element.strip().lower().capitalize()  # e.g. "Fire"
    c_elem = chinese_element.strip().lower().capitalize()

    # Check clash first (overrides harmony)
    clash_list = CLASH_MAP.get(w_elem, [])
    if c_elem in clash_list:
        return {
            "stance": "Contradictory",
            "multiplier": 1.0,
            "contradictory_mods": CONTRADICTORY_MODIFIERS.copy()
        }

    # Check harmony
    harmony_list = HARMONY_MAP.get(w_elem, [])
    if c_elem in harmony_list:
        return {
            "stance": "Harmonious",
            "multiplier": HARMONY_MULTIPLIER,
            "contradictory_mods": None
        }

    # Default balanced
    return {"stance": "Balanced", "multiplier": 1.0, "contradictory_mods": None}

def combine_stats(west_stats, chin_stats, synergy_info, chinese_element):
    """
    Combine Western and Chinese base_stats, apply synergy (global multiplier,
    plus contradictory per‑stat modifiers), then add element weight bonuses,
    and finally enforce the stat cap.
    """
    global_multiplier = synergy_info.get('multiplier', 1.0)
    contradictory_mods = synergy_info.get('contradictory_mods')

    all_stats = ['vitality', 'intellect', 'spirit', 'charisma', 'vigor', 'intuition', 'resolve']
    combined = {}

    # 1) Base combination + global multiplier
    for stat in all_stats:
        w_val = west_stats.get(stat, 0)
        c_val = chin_stats.get(stat, 0)
        combined[stat] = (w_val + c_val) * global_multiplier

    # 2) Apply contradictory per‑stat modifiers (if any)
    if contradictory_mods:
        for stat, factor in contradictory_mods.items():
            if stat in combined:
                combined[stat] *= factor

    # 3) Add element weight bonuses (based on Chinese element)
    bonuses = ELEMENT_WEIGHT_BONUSES.get(chinese_element, {})
    for stat, bonus in bonuses.items():
        if stat in combined:
            combined[stat] += bonus

    # 4) Enforce master stat cap (from stat_templates.json)
    for stat in all_stats:
        combined[stat] = min(int(combined[stat]), STAT_CAP)

    return combined

# --------------------------------------------------------------------
# 3. Lambda Handler
# --------------------------------------------------------------------
def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        dob_str = body.get('dob')
        if not dob_str:
            raise ValueError("Missing 'dob' field. Use YYYY-MM-DD.")
        dob_date = datetime.strptime(dob_str, "%Y-%m-%d").date()
        current_date = datetime.now().date()

        # Resolve both zodiacs from JSON
        western_sign = resolve_western_sign(dob_date)
        chinese_sign = resolve_chinese_sign(dob_date)

        w_name = western_sign.get('name', 'Unknown')
        c_animal = chinese_sign.get('animal', 'Unknown')
        c_element = chinese_sign.get('element', 'Unknown')
        w_element = western_sign.get('element', '')

        # Age & badge
        age, badge = calculate_age_and_badge(dob_date, current_date)

        # Synergy using external maps
        synergy = calculate_synergy(w_element, c_element)

        # Combine stats – note synergy_info and chinese_element passed
        west_stats = western_sign.get('base_stats', {})
        chin_stats = chinese_sign.get('base_stats', {})
        final_stats = combine_stats(west_stats, chin_stats, synergy, c_element)

        # Traits (fallback to empty strings if missing)
        traits = {
            "strengths": western_sign.get('qualities', ''),
            "shortcomings": western_sign.get('shortcomings', ''),
            "physical": western_sign.get('physical_traits', ''),
            "rulingZones": western_sign.get('ruling_zones', [])
        }

        # Build profile
        profile = {
            "title": f"The Avatar ({c_element} {c_animal} / {w_name})",
            "badge": badge,
            "stats": final_stats,
            "synergy": {
                "stance": synergy['stance'],
                "modifier": synergy['multiplier']
            },
            "traits": traits,
            "mirrorPhase": "Dormant"
        }

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"profile": profile})
        }

    except ValueError as ve:
        return {
            "statusCode": 400,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(ve)})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Internal Server Error", "details": str(e)})
        }
