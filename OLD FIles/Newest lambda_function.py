import json
import os
from datetime import datetime

# --------------------------------------------------------------------
# 1. Load JSON Data (new source of truth)
# --------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
WESTERN_JSON_PATH = os.path.join(DATA_DIR, 'western_zodiac.json')
CHINESE_JSON_PATH = os.path.join(DATA_DIR, 'chinese_zodiac.json')

def load_json_data(filepath):
    """Load JSON file and return its content."""
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# Pre-load data globally for warm Lambda containers
raw_west = load_json_data(WESTERN_JSON_PATH)
raw_chin = load_json_data(CHINESE_JSON_PATH)
WESTERN_ZODIAC = raw_west.get('western_zodiac', [])
CHINESE_ZODIAC = raw_chin.get('chinese_zodiac', [])

# --------------------------------------------------------------------
# 2. Core Resolution Functions (JSON‑based)
# --------------------------------------------------------------------
def resolve_western_sign(dob_date):
    """
    Resolve Western sign/cusp from JSON.
    Checks cusp entries first, then regular signs.
    Handles year‑wrap ranges (e.g., Capricorn).
    """
    month_day = dob_date.strftime("%m-%d")   # format matches JSON start/end
    # First pass: check all cusp entries
    for entry in WESTERN_ZODIAC:
        if entry.get('type') == 'cusp':
            start_md = entry['start']
            end_md = entry['end']
            if start_md <= end_md:
                if start_md <= month_day <= end_md:
                    return entry
            else:  # wrap‑around (e.g., Dec -> Jan)
                if month_day >= start_md or month_day <= end_md:
                    return entry
    # Second pass: regular signs
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
    """
    Resolve Chinese zodiac from JSON using date_ranges.
    Returns the full entry (animal, element, base_stats, etc.).
    """
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
    Evaluate synergy based on element compatibility.
    Harmonious (+20% boost) when Chinese element matches a Western element.
    (Advanced harmony/clash maps from element_interactions.json can be added later)
    """
    if not western_element or not chinese_element:
        return {"stance": "Balanced", "modifier": 1.0}
    w_parts = [e.strip().lower() for e in western_element.split('-')]
    c_elem = chinese_element.strip().lower()
    if c_elem in w_parts:
        return {"stance": "Harmonious", "modifier": 1.2}
    return {"stance": "Balanced", "modifier": 1.0}

def combine_stats(west_stats, chin_stats, modifier):
    """
    Combine Western and Chinese base_stats (element‑wise sum) and apply synergy modifier.
    Returns a dictionary with values capped at 1000 (though sums will be far lower).
    """
    combined = {}
    all_stats = ['vitality', 'intellect', 'spirit', 'charisma', 'vigor', 'intuition', 'resolve']
    for stat in all_stats:
        w_val = west_stats.get(stat, 0)
        c_val = chin_stats.get(stat, 0)
        combined[stat] = min(int((w_val + c_val) * modifier), 1000)
    return combined

# --------------------------------------------------------------------
# 3. Lambda Handler
# --------------------------------------------------------------------
def lambda_handler(event, context):
    try:
        # Parse input
        body = json.loads(event.get('body', '{}'))
        dob_str = body.get('dob')
        if not dob_str:
            raise ValueError("Missing 'dob' field. Use YYYY-MM-DD.")
        dob_date = datetime.strptime(dob_str, "%Y-%m-%d").date()
        current_date = datetime.now().date()

        # Resolve both zodiacs from JSON
        western_sign = resolve_western_sign(dob_date)
        chinese_sign = resolve_chinese_sign(dob_date)

        # Extract display names
        w_name = western_sign.get('name', 'Unknown')
        c_animal = chinese_sign.get('animal', 'Unknown')
        c_element = chinese_sign.get('element', 'Unknown')

        # Age & badge
        age, badge = calculate_age_and_badge(dob_date, current_date)

        # Synergy using real elements
        w_element = western_sign.get('element', '')
        synergy = calculate_synergy(w_element, c_element)

        # Combine stats from both sources
        west_stats = western_sign.get('base_stats', {})
        chin_stats = chinese_sign.get('base_stats', {})
        final_stats = combine_stats(west_stats, chin_stats, synergy['modifier'])

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
            "synergy": synergy,
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