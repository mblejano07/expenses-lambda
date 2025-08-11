import os
import json
import random
import time
from common import make_response, SES, INVOICE_TABLE, DYNAMODB, OTP_TABLE, SES_MOCK_MODE, EMAIL_SOURCE
from common import is_valid_workmail_user  # from step 1

# OTP_TABLE = DYNAMODB.Table(os.getenv("OTP_TABLE_NAME", "OtpStore"))
OTP_TTL_SECONDS = 300  # OTP valid for 5 minutes

def send_otp_email(email, otp_code):
    subject = "Your OTP Code"
    body_text = f"Your OTP code is: {otp_code}\nIt is valid for 5 minutes."
    try:
        SES.send_email(
            Source=EMAIL_SOURCE,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": body_text}},
            }
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
        email = body.get("email")
        if not email:
            return make_response(400, {"error": "Email is required"})

        if not is_valid_workmail_user(email):
            return make_response(403, {"error": "Email is not authorized"})

        otp_code = generate_otp()
        expires_at = int(time.time()) + OTP_TTL_SECONDS

        OTP_TABLE.put_item(
            Item={
                "email": email,
                "otp_code": otp_code,
                "expires_at": expires_at
            }
        )
     
        send_otp_email(email, otp_code)

        return make_response(200, {"message": "OTP sent"})
    except Exception as e:
        return make_response(500, {"error": str(e)})
