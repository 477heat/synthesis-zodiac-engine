import json
import os
import csv
from datetime import datetime
# Made on Gemini Phase3.1 Lambda Update
# --------------------------------------------------------------------
# 1. Initialization and Data Loading
# --------------------------------------------------------------------
# Define paths to your data files (assuming they are bundled with the Lambda)
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
WESTERN_CSV_PATH = os.path.join(DATA_DIR, 'NEWER RANGES - Sheet1-Western Zodiac.csv')
CHINESE_CSV_PATH = os.path.join(DATA_DIR, 'NEWER RANGES - Sheet2-Chinese Zodiac.csv')

def load_csv_data(filepath):
    """Loads a CSV file into a list of dictionaries."""
    data = []
    if os.path.exists(filepath):
        with open(filepath, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    return data

# Pre-load data in the global scope so it caches during Lambda "warm" starts
western_zodiac_data = load_csv_data(WESTERN_CSV_PATH)
chinese_zodiac_data = load_csv_data(CHINESE_CSV_PATH)

# --------------------------------------------------------------------
# 2. Core Logic Resolvers
# --------------------------------------------------------------------
def resolve_western_sign(dob_date):
    """
    Resolves the Western sign using ONLY the MM/DD.
    Handles the wrap-around bug (e.g., Capricorn ending in January).
    """
    month_day = dob_date.strftime("%m/%d")
    
    for row in western_zodiac_data:
        start_md = row['Start Date mm/dd'].strip()
        end_md = row['End Date mm/dd'].strip()
        
        # Standard range (e.g., 03/25 to 04/16)
        if start_md <= end_md:
            if start_md <= month_day <= end_md:
                return row
        # Wrap-around range (e.g., 12/26 to 01/16)
        else:
            if month_day >= start_md or month_day <= end_md:
                return row

    raise ValueError(f"No matching Western sign found for MM/DD: {month_day}. Check CSV completeness.")

def resolve_chinese_sign(dob_date):
    """
    Resolves the Chinese sign by checking if the FULL DOB falls 
    within the specific Year's Start and End Dates.
    """
    for row in chinese_zodiac_data:
        # Clean the string to handle either YYYY/MM/DD or YYYY-MM-DD from the CSV
        start_str = row['Start Date'].strip().replace('/', '-')
        end_str = row['End Date'].strip().replace('/', '-')
        
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        
        if start_date <= dob_date <= end_date:
            return row
            
    raise ValueError(f"No matching Chinese sign found for DOB: {dob_date}. Date may be out of bounds of the CSV.")

def calculate_age_and_badge(dob_date, current_date):
    """Calculates age and assigns the badge based on the Master Spec."""
    age = current_date.year - dob_date.year - ((current_date.month, current_date.day) < (dob_date.month, dob_date.day))
    
    # Adhering to the Master Spec ranges
    if age < 18:
        badge = "Apprentice" # Fallback for underage
    elif 18 <= age < 24:
        badge = "Noob"
    elif 24 <= age < 30:
        badge = "Novice"
    elif 30 <= age < 45:
        badge = "Adept" # Bridging the gap
    elif 45 <= age < 55:
        badge = "Venerable"
    else:
        badge = "Elder"
        
    return age, badge

def calculate_synergy(western_element, chinese_element):
    """
    Evaluates Synergy.
    Harmonious (+20% Boost): Triggered when Western Element matches Chinese Element.
    """
    # Safe checks just in case element data is missing or complex (like Fire-Earth cusp)
    w_elements = [e.strip().lower() for e in western_element.split('-')] if western_element else []
    c_element = chinese_element.strip().lower() if chinese_element else ""
    
    if c_element in w_elements:
        return {"stance": "Harmonious", "modifier": 1.2}
    
    # Placeholder for other stances (Contradictory, Mirror, Balanced)
    # You can expand this with your element_interactions.json logic later
    return {"stance": "Balanced", "modifier": 1.0}

# --------------------------------------------------------------------
# 3. Main Lambda Handler
# --------------------------------------------------------------------
def lambda_handler(event, context):
    try:
        # 1. Parse Input
        body = json.loads(event.get('body', '{}'))
        dob_str = body.get('dob')
        
        if not dob_str:
            raise ValueError("Missing 'dob' field. Please provide YYYY-MM-DD (ISO 8601).")
            
        # Enforce ISO 8601 format (YYYY-MM-DD)
        try:
            dob_date = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid date format for '{dob_str}'. Please use YYYY-MM-DD.")
            
        current_date = datetime.now().date()
        
        # 2. Resolve Signs from CSVs
        western_sign = resolve_western_sign(dob_date)
        chinese_sign = resolve_chinese_sign(dob_date)
        
        # Extract base properties
        w_name = western_sign.get('Zodiac Sign', 'Unknown Sign')
        w_traits = western_sign.get('Western Personality Traits', '')
        
        c_animal = chinese_sign.get('Zodiac Sign', 'Unknown Sign')
        c_element = chinese_sign.get('Element', 'Unknown Element')
        
        # 3. Determine Age & Badge
        age, badge = calculate_age_and_badge(dob_date, current_date)
        
        # 4. Synergy Calculation (Requires Western Element to be present somewhere, assuming passed or hardcoded)
        # *Note: The provided CSV snippet for Western didn't show 'Element', so we pass empty string or map it.
        # Assuming you will merge your western_zodiac.json element data here:
        western_element_placeholder = "Fire" # Replace with actual lookup
        synergy = calculate_synergy(western_element_placeholder, c_element)
        
        # 5. Build and Format the Output
        # (Using dummy stat data scaled to max 1000 to satisfy the architectural spec)
        profile = {
            "title": f"The Avatar ({c_element} {c_animal} / {w_name})", # Matches spec formatting
            "badge": badge,
            "stats": {
                "vitality": min(int(620 * synergy["modifier"]), 1000),
                "intellect": min(int(410 * synergy["modifier"]), 1000),
                "spirit": min(int(380 * synergy["modifier"]), 1000),
                "charisma": min(int(550 * synergy["modifier"]), 1000),
                "vigor": min(int(710 * synergy["modifier"]), 1000),
                "intuition": min(int(320 * synergy["modifier"]), 1000),
                "resolve": min(int(780 * synergy["modifier"]), 1000)
            },
            "synergy": synergy,
            "traits": {
                "strengths": w_traits, # Pulling from the CSV
                "shortcomings": "Pending Integration", # Pull from JSON
                "physical": "Pending Integration",     # Pull from JSON
                "rulingZones": []                      # Pull from JSON
            },
            "mirrorPhase": "Dormant"
        }
        
        # Return exact JSON structure
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
//  Untitled.swift
//  SynthesisisZodiacEngine
//
//  Created by Tony Brewer on 5/2/26.
//

