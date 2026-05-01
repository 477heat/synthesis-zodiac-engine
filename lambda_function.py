import json
import os
import traceback
from datetime import datetime, date

# --------------------------------------------------------------------
# Load all static data at cold start
# --------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

with open(os.path.join(DATA_DIR, 'western_zodiac.json'), 'r') as f:
    data = json.load(f)
    western_zodiac = data["western_zodiac"] if isinstance(data, dict) else data

with open(os.path.join(DATA_DIR, 'chinese_zodiac.json'), 'r') as f:
    data = json.load(f)
    chinese_zodiac = data["chinese_zodiac"] if isinstance(data, dict) else data

with open(os.path.join(DATA_DIR, 'element_interactions.json'), 'r') as f:
    element_interactions = json.load(f)

with open(os.path.join(DATA_DIR, 'stat_templates.json'), 'r') as f:
    stat_templates = json.load(f)

# --------------------------------------------------------------------
# 1. Validate input
# --------------------------------------------------------------------
def validate_input(event):
    """Parse and validate DOB, return (dob_date, current_date, age)."""
    body = json.loads(event.get('body', '{}'))
    dob_str = body.get('dob')
    cur_str = body.get('currentDate')

    if not dob_str:
        raise ValueError("Missing 'dob' field.")

    try:
        dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError("Invalid date format. Use YYYY-MM-DD.")

    if cur_str:
        try:
            curr = datetime.strptime(cur_str, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError("Invalid currentDate format.")
    else:
        curr = date.today()

    if dob > curr:
        raise ValueError("Date of birth cannot be in the future.")

    age = curr.year - dob.year - ((curr.month, curr.day) < (dob.month, dob.day))
    if age < stat_templates['age']['min_age']:
        raise ValueError(f"Age must be at least {stat_templates['age']['min_age']}.")

    return dob, curr, age

# --------------------------------------------------------------------
# 2. Western sign/cusp
# --------------------------------------------------------------------
def resolve_western(dob):
    """Assign Western sign/cusp; cusps take precedence."""
    month_day = dob.strftime('%m-%d')
    for entry in western_zodiac:
        if entry['type'] == 'cusp':
            if entry['start'] <= month_day <= entry['end']:
                return entry
    for entry in western_zodiac:
        if entry['type'] == 'sign':
            if entry['start'] <= month_day <= entry['end']:
                return entry
    raise ValueError("No matching Western sign found.")

# --------------------------------------------------------------------
# 3. Chinese designation
# --------------------------------------------------------------------
def resolve_chinese(dob):
    for entry in chinese_zodiac:
        for dr in entry['date_ranges']:
            start = datetime.strptime(dr['start'], '%Y-%m-%d').date()
            end = datetime.strptime(dr['end'], '%Y-%m-%d').date()
            if start <= dob <= end:
                return entry
    raise ValueError("No matching Chinese designation found.")

# --------------------------------------------------------------------
# 4. Base stats (unchanged)
# --------------------------------------------------------------------
def compute_base_stats(west, chin):
    stats = {
        "vitality": 0, "intellect": 0, "spirit": 0,
        "charisma": 0, "vigor": 0, "intuition": 0, "resolve": 0
    }
    for k, v in west['base_stats'].items():
        stats[k] += v
    for k, v in chin['base_stats'].items():
        stats[k] += v
    elem = chin['element']
    if elem in stat_templates['element_weight_bonuses']:
        for k, v in stat_templates['element_weight_bonuses'][elem].items():
            stats[k] += v
    return stats

# --------------------------------------------------------------------
# 5. SYNERGY (the only function that changed!)
# --------------------------------------------------------------------
def evaluate_synergy(west, chin, stats):
    """
    Determine stance using Wu Xing elemental cycles.
    Mirror (animal‑based) is still highest priority.
    """
    chin_element = chin['element']          # e.g. "Wood"
    chin_animal = chin['animal']            # e.g. "Snake"
    west_name = west['name']                # e.g. "Taurus" or "Aries-Taurus Cusp"
    west_element_raw = west['element']      # e.g. "Earth" or "Fire-Earth"

    mirror_pairs = element_interactions['mirror_pairs']

    # ---------- MIRROR (unchanged animal logic) ----------
    # Case 1: Plain animal match, e.g. "Dragon" -> "Aries"
    if chin_animal in mirror_pairs and mirror_pairs[chin_animal] == west_name:
        stance = "Mirror"
        for k in stats:
            stats[k] += element_interactions['mirror_bonus']
        return stance, None, stats

    # Case 2: Cusp combo, e.g. "Rat-Aries" -> "Pisces-Aries"
    animal_sign_combo = f"{chin_animal}-{west_name.split()[0]}"
    if animal_sign_combo in mirror_pairs and mirror_pairs[animal_sign_combo] == west_name:
        stance = "Mirror"
        for k in stats:
            stats[k] += element_interactions['mirror_bonus']
        return stance, None, stats

    # ---------- ELEMENTAL HARMONY / CLASH ----------
    # Chinese element (fixed for the person) vs ALL Western elements (cusp may have two)
    west_elements = set(west_element_raw.split('-'))

    harmony_list = element_interactions['harmony_map'].get(chin_element, [])
    clash_list   = element_interactions['clash_map'].get(chin_element, [])

    if west_elements.intersection(clash_list):
        stance = "Contradictory"
        # Apply per‑stat modifiers (no universal multiplier)
        for stat, factor in element_interactions['contradictory_modifiers'].items():
            if stat in stats:
                stats[stat] *= factor
        modifier = 1.0   # signal that individual factors were used

    elif west_elements.intersection(harmony_list):
        stance = "Harmonious"
        mult = element_interactions['harmonious_multiplier']
        for k in stats:
            stats[k] *= mult
        modifier = mult

    else:
        stance = "Balanced"   # (used to be "Neutral")
        modifier = 1.0

    # Enforce stat cap
    cap = stat_templates['stat_cap']
    for k in stats:
        if stats[k] > cap:
            stats[k] = cap

    return stance, modifier, stats

# --------------------------------------------------------------------
# 6. Age multiplier
# --------------------------------------------------------------------
def apply_age_multiplier(stats, age):
    base_mult = 1.0 + (age - stat_templates['age']['min_age']) / 250.0
    for k in stats:
        stats[k] *= base_mult
    return stats

# --------------------------------------------------------------------
# 7. Badge
# --------------------------------------------------------------------
def get_badge(age):
    badges = stat_templates['age']['badges']
    for badge, (low, high) in badges.items():
        if low <= age <= high:
            return badge
    return ""

# --------------------------------------------------------------------
# 8. Merge traits
# --------------------------------------------------------------------
def assemble_traits(west, chin):
    strengths = f"{west['qualities']} {chin['qualities']}"
    shortcomings = f"{west['shortcomings']} {chin['shortcomings']}"
    physical = f"{west['physical_traits']} {chin['physical_tendencies']}"
    ruling_zones = west['ruling_zones']
    return strengths, shortcomings, physical, ruling_zones

# --------------------------------------------------------------------
# 9. Title
# --------------------------------------------------------------------
def generate_title(west, chin):
    return f"{chin['designation']} / {west['name']}"

# --------------------------------------------------------------------
# 10. Main Lambda handler
# --------------------------------------------------------------------
def lambda_handler(event, context):
    try:
        dob, curr, age = validate_input(event)
        west = resolve_western(dob)
        chin = resolve_chinese(dob)

        stats = compute_base_stats(west, chin)
        stance, modifier, stats = evaluate_synergy(west, chin, stats)

        stats = apply_age_multiplier(stats, age)
        cap = stat_templates['stat_cap']
        for k in stats:
            if stats[k] > cap:
                stats[k] = cap

        stats = {k: int(round(v)) for k, v in stats.items()}

        badge = get_badge(age)
        strengths, shortcomings, physical, ruling_zones = assemble_traits(west, chin)
        title = generate_title(west, chin)

        # Friendly descriptions
        stance_desc_map = {
            "Harmonious": "Harmonious: A natural alignment that amplifies your innate gifts across all dimensions.",
            "Contradictory": "Inner Turmoil: A volatile blend that sharply heightens your instincts and drive, but erodes your endurance and composure.",
            "Mirror": "Pure Spirit: A rare celestial mirror that bestows a profound, balanced enhancement to your core being.",
            "Balanced": "Balanced: No elemental conflict or harmony—your path unfolds through personal will."
        }

        profile = {
            "sovereign_designation": title,
            "badge": badge,
            "stats": stats,
            "synergy": {
                "stance": stance_desc_map.get(stance, stance),
                "numerical_modifier": modifier if stance == "Harmonious" else (modifier if stance == "Contradictory" else None),
                "mirror_bonus_applied": stance == "Mirror"
            },
            "traits": {
                "strengths": strengths,
                "shortcomings": shortcomings,
                "physical": physical,
                "rulingZones": ruling_zones
            },
            "mirrorPhase": "Dormant"
        }

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"profile": profile})
        }

    except ValueError as e:
        return {"statusCode": 400, "body": json.dumps({"error": str(e)})}
    except Exception as e:
        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
