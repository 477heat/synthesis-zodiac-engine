
import json
from lambda_function import lambda_handler

event = {
    "body": "{\"dob\": \”1980-02-22}” 
}

try:
    response = lambda_handler(event, None)
    print(json.dumps(response, indent=2))
except Exception as e:
    print(f"Error: {e}")

