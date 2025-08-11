import os
import json
import time
import jwt  # you might need to add this to requirements.txt
from common import make_response, DYNAMODB, OTP_TABLE
from common import JWT_SECRET

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        email = body.get("email")
        otp_code = body.get("otp_code")

        if not email or not otp_code:
            return make_response(400, {"error": "Email and OTP code are required"})

        response = OTP_TABLE.get_item(Key={"email": email})
        item = response.get("Item")

        if not item:
            return make_response(400, {"error": "OTP not found or expired"})

        if int(time.time()) > item.get("expires_at", 0):
            return make_response(400, {"error": "OTP expired"})

        if otp_code != item.get("otp_code"):
            return make_response(400, {"error": "Invalid OTP code"})

        # OTP is valid, generate JWT token for session
        payload = {
            "email": email,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600  # 1 hour expiry
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        # Optionally: delete OTP after successful validation
        OTP_TABLE.delete_item(Key={"email": email})

        return make_response(200, {"message": "OTP verified", "token": token})

    except Exception as e:
        return make_response(500, {"error": str(e)})
