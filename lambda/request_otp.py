# request_otp.py
import json, time, random, secrets, os
from common import (
    make_response,
    OTP_TABLE,
    is_valid_workmail_user,
    hash_otp,
    SES,
    EMAIL_SOURCE,
    SES_MOCK_MODE,
    OTP_MAX_ATTEMPTS,
    OTP_WINDOW_SECONDS
)

OTP_TTL_SECONDS = 300  # 5 minutes

def send_otp_email(email, otp_code):
    subject = "Your OTP Code"
    body_text = f"Your OTP code is: {otp_code}\nIt is valid for 5 minutes."
    try:
        SES.send_email(
            Source=EMAIL_SOURCE,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": body_text}}
            },
        )
    except Exception as e:
        print(f"Error sending email: {e}")
        if not SES_MOCK_MODE:
            raise

def generate_otp():
    return f"{random.randint(100000, 999999)}"

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        email = (body.get("email") or "").strip().lower()
        if not email:
            return make_response(400, {"error": "Email is required"})
        if not is_valid_workmail_user(email):
            return make_response(403, {"error": "Email is not authorized"})

        # rate-limit window
        now = int(time.time())
        window_start = now - OTP_WINDOW_SECONDS

        # get current counters (if any)
        existing = OTP_TABLE.get_item(Key={"email": email}).get("Item") or {}
        attempts = int(existing.get("attempts", 0))
        first_attempt_at = int(existing.get("first_attempt_at", now))

        if first_attempt_at < window_start:
            # reset window
            attempts = 0
            first_attempt_at = now

        if attempts >= OTP_MAX_ATTEMPTS:
            return make_response(429, {"error": "Too many OTP requests. Try again later."})

        # generate + hash
        otp_code = generate_otp()
        salt = secrets.token_hex(8)
        otp_hash = hash_otp(otp_code, salt)
        expires_at = now + OTP_TTL_SECONDS

        # Build the DynamoDB item
        item = {
            "email": email,
            "otp_hash": otp_hash,
            "salt": salt,
            "expires_at": expires_at,
            "attempts": attempts + 1,
            "first_attempt_at": first_attempt_at
        }

        # ✅ For local testing, store raw OTP (never in production)
        if os.environ.get("WORKMAIL_ORGANIZATION_ID") == "local-dev":
            item["otp_code"] = otp_code

        OTP_TABLE.put_item(Item=item)

        send_otp_email(email, otp_code)
        return make_response(200, {"message": "OTP sent"})

    except Exception as e:
        return make_response(500, {"error": str(e)})

