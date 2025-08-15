import json, time, random, secrets, os
from common import (
    format_response,  # ✅ Use standardized response helper
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

        # ✅ Validation
        if not email:
            return format_response(400, message="Validation Error", errors={"email": "Email is required"})
        if not is_valid_workmail_user(email):
            return format_response(403, message="Unauthorized Email", errors={"email": "Email is not authorized"})

        # ✅ Rate-limit check
        now = int(time.time())
        window_start = now - OTP_WINDOW_SECONDS

        existing = OTP_TABLE.get_item(Key={"email": email}).get("Item") or {}
        attempts = int(existing.get("attempts", 0))
        first_attempt_at = int(existing.get("first_attempt_at", now))

        if first_attempt_at < window_start:
            attempts = 0
            first_attempt_at = now

        if attempts >= OTP_MAX_ATTEMPTS:
            return format_response(429, message="Too many OTP requests", errors={"rate_limit": "Try again later"})

        # ✅ Generate OTP and hash
        otp_code = generate_otp()
        salt = secrets.token_hex(8)
        otp_hash = hash_otp(otp_code, salt)
        expires_at = now + OTP_TTL_SECONDS

        item = {
            "email": email,
            "otp_hash": otp_hash,
            "salt": salt,
            "expires_at": expires_at,
            "attempts": attempts + 1,
            "first_attempt_at": first_attempt_at
        }

        # For local testing only
        if os.environ.get("WORKMAIL_ORGANIZATION_ID") == "local-dev":
            item["otp_code"] = otp_code

        try:
            print("Putting item to DynamoDB:", item)
            OTP_TABLE.put_item(Item=item)
        except Exception as e:
            print("DynamoDB put_item failed:", e)
            raise

        # OTP_TABLE.put_item(Item=item)

        # ✅ Send OTP
        send_otp_email(email, otp_code)

        return format_response(200, message="OTP sent successfully", data={"email": email})

    except Exception as e:
        return format_response(500, message="Internal Server Error", errors={"exception": str(e)})
