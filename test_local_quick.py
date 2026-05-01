import json
from lambda_function import lambda_handler

# Simulate an API Gateway event
event = {
    "body": json.dumps({
        "dob": "1992-05-20",
        "currentDate": "2026-05-01"
    })
}

# Call the Lambda handler exactly as AWS would
response = lambda_handler(event, None)

# Print the result nicely
print("Status Code:", response["statusCode"])
profile = json.loads(response["body"])
print(json.dumps(profile, indent=2))
