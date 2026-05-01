import os
from datetime import datetime, date

# Load all static data at cold start
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
with open(os.path.join(DATA_DIR, 'western_zodiac.json'), 'r') as f:
    western_zodiac = json.load(f)
with open(os.path.join(DATA_DIR, 'chinese_zodiac.json'), 'r') as f:
    chinese_zodiac = json.load(f)
with open(os.path.join(DATA_DIR, 'element_interactions.json'), 'r') as f:
    element_interactions = json.load(f)
with open(os.path.join(DATA_DIR, 'stat_templates.json'), 'r') as f:
    stat_templates = json.load(f)

def validate_input(event):
    """Parse and validate DOB, return (dob_date, current_date)."""
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

def resolve_western(dob):
    """Assign Western sign/cusp; cusps take precedence."""
    month_day = dob.strftime('%m-%d')
    # check cusps first
    for entry in western_zodiac:
        if entry['type'] == 'cusp':
            if entry['start'] <= month_day <= entry['end']:
                return entry
    # then signs
    for entry in western_zodiac:
        if entry['type'] == 'sign':
            if entry['start'] <= month_day <= entry['end']:
                return entry
    raise ValueError("No matching Western sign found.")

def resolve_chinese(dob):
    """Find Chinese animal/element by exact year boundaries."""
    for entry in chinese_zodiac:
        start = datetime.strptime(entry['start'], '%Y-%m-%d').date()
        end = datetime.strptime(entry['end'], '%Y-%m-%d').date()
        if start <= dob <= end:
            return entry
    raise ValueError("No matching Chinese designation found.")

def compute_base_stats(west, chin):
    """Sum Western base + Chinese base + element weighting."""
    stats = {k: 0 for k in stat_templates['element_weight_bonuses']['Wood'].keys()}
    # Western base
    for k, v in west['base_stats'].items():
        stats[k] += v
    # Chinese animal base
    for k, v in chin['base_stats'].items():
        stats[k] += v
    # Chinese element weight bonus
    elem = chin['element']
    if elem in stat_templates['element_weight_bonuses']:
        for k, v in stat_templates['element_weight_bonuses'][elem].items():
            stats[k] += v
    return stats

def evaluate_synergy(west, chin, stats):
    """Determine stance (Harmonious/Contradictory/Mirror) and apply modifiers."""
    west_elem = west['element']
    chin_elem = chin['element']
    west_name = west['name']
    chin_animal = chin['animal']
    stance = None
    modifier = 1.0

    # check mirror first (highest priority)
    mirror_pairs = element_interactions['mirror_pairs']
    if west_name in mirror_pairs and mirror_pairs[west_name] == chin_animal:
        stance = "Mirror"
        for k in stats:
            stats[k] += element_interactions['mirror_bonus']
    elif chin_elem in element_interactions['harmony_map'].get(west_elem, []):
        stance = "Harmonious"
        modifier = element_interactions['harmonious_multiplier']
        # multiply all stats by 1.2
        for k in stats:
            stats[k] = stats[k] * modifier
    elif chin_elem in element_interactions['clash_map'].get(west_elem, []):
        stance = "Contradictory"
        # apply specific stat shifts per contradictory_modifiers
        for k in stats:
            factor = element_interactions['contradictory_modifiers'].get(k, 1.0)
            stats[k] = stats[k] * factor
    else:
        stance = "Neutral"

    # enforce cap
    cap = stat_templates['stat_cap']
    for k in stats:
        if stats[k] > cap:
            stats[k] = cap
    return stance, modifier, stats

def apply_age_multiplier(stats, age):
    """Age coefficient: increase stats slowly with age."""
    base_mult = 1.0 + (age - stat_templates['age']['min_age']) / 250.0
    for k in stats:
        stats[k] = stats[k] * base_mult
    return stats

def get_badge(age):
    """Return badge name based on age bracket."""
    badges = stat_templates['age']['badges']
    for badge, (low, high) in badges.items():
        if low <= age <= high:
            return badge
    return ""

def assemble_traits(west, chin):
    """Merge qualitative traits."""
    strengths = f"{west['qualities']} {chin['qualities']}"
    shortcomings = f"{west['shortcomings']} {chin['shortcomings']}"
    physical = f"{west['physical_traits']} {chin['physical_tendencies']}"
    ruling_zones = west['ruling_zones']
    return strengths, shortcomings, physical, ruling_zones

def generate_title(west, chin):
    """Sovereign designation: Chinese designation / Western name."""
    return f"{chin['designation']} / {west['name']}"

def lambda_handler(event, context):
    try:
        dob, curr, age = validate_input(event)
        west = resolve_western(dob)
        chin = resolve_chinese(dob)

        # base stats
        stats = compute_base_stats(west, chin)

        # synergy
        stance, modifier, stats = evaluate_synergy(west, chin, stats)

        # age
        stats = apply_age_multiplier(stats, age)
        # recap after age multiplication
        cap = stat_templates['stat_cap']
        for k in stats:
            if stats[k] > cap:
                stats[k] = cap

        # round all stats to integers
        stats = {k: int(round(v)) for k, v in stats.items()}

        badge = get_badge(age)
        strengths, shortcomings, physical, ruling_zones = assemble_traits(west, chin)
        title = generate_title(west, chin)

        # stance description in natural language
        stance_desc = {
            "Harmonious": "Harmonious: A natural alignment that amplifies your innate gifts across all dimensions.",
            "Contradictory": "Inner Turmoil: A volatile blend that sharply heightens your instincts and drive, but erodes your endurance and composure.",
            "Mirror": "Pure Spirit: A rare celestial mirror that bestows a profound, balanced enhancement to your core being.",
            "Neutral": "Balanced: No elemental conflict or harmony—your path unfolds through personal will."
        }

        profile = {
            "sovereign_designation": title,
            "badge": badge,
            "stats": stats,
            "synergy": {
                "stance": stance_desc.get(stance, stance),
                "numerical_modifier": modifier if stance != "Mirror" else None,
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

        response = {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"profile": profile})
        }
        return response

    except ValueError as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": str(e)})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error."})
        }
