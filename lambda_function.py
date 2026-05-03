# Engine 1.4
import json
import os
from datetime import datetime

# 1. Load JSON Data
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, 'data')

def load_json_data(filename):
    # Try data folder first, then base dir
    paths = [os.path.join(DATA_DIR, filename), os.path.join(BASE_DIR, filename)]
    for path in paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    return {}

# Pre-load data
raw_west = load_json_data('western_zodiac.json')
raw_chin = load_json_data('chinese_zodiac.json')
ELEMENT_INTERACTIONS = load_json_data('element_interactions.json')
STAT_TEMPLATES = load_json_data('stat_templates.json')

WESTERN_ZODIAC = raw_west.get('western_zodiac', [])
CHINESE_ZODIAC = raw_chin.get('chinese_zodiac', [])

# Extract interaction constants
HARMONY_MAP = ELEMENT_INTERACTIONS.get('harmony_map', {})
CLASH_MAP = ELEMENT_INTERACTIONS.get('clash_map', {})
MIRRORED_MAP = ELEMENT_INTERACTIONS.get('mirrored_spirits_map', {})
MIRRORED_MULT = ELEMENT_INTERACTIONS.get('mirrored_spirits_multiplier', 50)
HARMONY_MULT = ELEMENT_INTERACTIONS.get('harmony_multiplier', 1.2)
CONTRADICTORY_MODS = ELEMENT_INTERACTIONS.get('contradictory_modifiers', {})
ELEMENT_WEIGHTS = STAT_TEMPLATES.get('element_weight_bonuses', {})
STAT_CAP = STAT_TEMPLATES.get('stat_cap', 750)

def resolve_western_sign(dob_date):
    md = dob_date.strftime("%m-%d")
    # Check cusps first, then signs
    for entry_type in ['cusp', 'sign']:
        for entry in WESTERN_ZODIAC:
            if entry.get('type') == entry_type:
                s, e = entry['start'], entry['end']
                if (s <= e and s <= md <= e) or (s > e and (md >= s or md <= e)):
                    return entry
    raise ValueError(f"Western sign not found for {md}")

def resolve_chinese_sign(dob_date):
    for entry in CHINESE_ZODIAC:
        for dr in entry.get('date_ranges', []):
            start = datetime.strptime(dr['start'], "%Y-%m-%d").date()
            end = datetime.strptime(dr['end'], "%Y-%m-%d").date()
            if start <= dob_date <= end:
                return entry
    raise ValueError(f"Chinese zodiac not found for {dob_date}")

def calculate_synergy(w_name, w_elem, c_animal, c_elem):
    """Calculates stance and multipliers based on element and spirit pairing."""
    w_e = w_elem.split('-')[0].capitalize() # Handle Fire-Earth types
    c_e = c_elem.capitalize()
    
    # 1. Check Mirrored Spirits (Highest Priority)
    # Check single (Rat) or dual (Rat-Aries) mapping
    pairing_key = f"{c_animal}-{w_name}"
    if MIRRORED_MAP.get(c_animal) == w_name or MIRRORED_MAP.get(pairing_key):
        return {"stance": "Mirrored", "multiplier": MIRRORED_MULT, "mods": None}

    # 2. Check Clash
    if c_e in CLASH_MAP.get(w_e, []):
        return {"stance": "Contradictory", "multiplier": 1.0, "mods": CONTRADICTORY_MODS}

    # 3. Check Harmony
    if c_e in HARMONY_MAP.get(w_e, []):
        return {"stance": "Harmonious", "multiplier": HARMONY_MULT, "mods": None}

    return {"stance": "Balanced", "multiplier": 1.0, "mods": None}

def lambda_handler(event, context):
    try:
        # Support both direct invocation and API Gateway
        body = event if 'dob' in event else json.loads(event.get('body', '{}'))
        dob_str = body.get('dob')
        if not dob_str:
            return {"statusCode": 400, "body": json.dumps({"error": "Missing 'dob' (YYYY-MM-DD)"})}
        
        dob_date = datetime.strptime(dob_str, "%Y-%m-%d").date()
        current_date = datetime.now().date()

        w_sign = resolve_western_sign(dob_date)
        c_sign = resolve_chinese_sign(dob_date)
        
        # Synergy
        synergy = calculate_synergy(w_sign['name'], w_sign['element'], c_sign['animal'], c_sign['element'])
        
        # Stat Calculation
        stats = {}
        for s in ['vitality', 'intellect', 'spirit', 'charisma', 'vigor', 'intuition', 'resolve']:
            base = w_sign['base_stats'].get(s, 0) + c_sign['base_stats'].get(s, 0)
            val = base * synergy['multiplier']
            if synergy['mods'] and s in synergy['mods']:
                val *= synergy['mods'][s]
            val += ELEMENT_WEIGHTS.get(c_sign['element'], {}).get(s, 0)
            stats[s] = min(int(val), STAT_CAP)

        # Age/Badge
        age = current_date.year - dob_date.year - ((current_date.month, current_date.day) < (dob_date.month, dob_date.day))
        badge = "Corpus Exanime"
        for b, r in STAT_TEMPLATES['age']['badges'].items():
            if r[0] <= age <= r[1]:
                badge = b
                break

        profile = {
            "title": f"The Avatar ({c_sign['element']} {c_sign['animal']} / {w_sign['name']})",
            "badge": badge,
            "age": age,
            "stats": stats,
            "synergy": {"stance": synergy['stance'], "multiplier": synergy['multiplier']},
            "traits": {
                "strengths": w_sign.get('qualities'),
                "shortcomings": w_sign.get('shortcomings'),
                "physical": w_sign.get('physical_traits') or c_sign.get('physical_tendencies')
            }
        }

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"profile": profile})
        }

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

# Local Testing Logic
if __name__ == "__main__":
    test_event = {"body": json.dumps({"dob": "1990-05-20"})}
    print(lambda_handler(test_event, None))
