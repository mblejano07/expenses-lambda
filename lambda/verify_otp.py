# verify_otp.py
import json, time, hmac
from common import make_response, OTP_TABLE, hash_otp, issue_tokens

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        email = (body.get("email") or "").strip().lower()
        otp_code = (body.get("otp_code") or "").strip()

        if not email or not otp_code:
            return make_response(400, {"error": "Email and OTP code are required"})

        resp = OTP_TABLE.get_item(Key={"email": email})
        item = resp.get("Item")
        if not item:
            return make_response(400, {"error": "OTP not found or expired"})

        if int(time.time()) > int(item.get("expires_at", 0)):
            return make_response(400, {"error": "OTP expired"})

        # verify hashed OTP
        expected = hash_otp(otp_code, item["salt"])
        if not hmac.compare_digest(expected, item["otp_hash"]):
            return make_response(400, {"error": "Invalid OTP code"})

        # success: delete OTP and issue tokens
        OTP_TABLE.delete_item(Key={"email": email})
        access_token, refresh_token, refresh_exp = issue_tokens(email)

        # OPTIONAL: set refresh token as HttpOnly cookie (works with API GW + CORS config)
        headers = {
            "Content-Type": "application/json",
            # Adjust cookie attributes for your domain/HTTPS
            "Set-Cookie": f"refresh_token={refresh_token}; HttpOnly; Path=/; Max-Age=2592000; SameSite=Lax"
        }
        return make_response(200, {
            "message": "OTP verified",
            "access_token": access_token,
            "refresh_token": refresh_token,  # also in cookie for SPA convenience
            "refresh_expires_at": refresh_exp
        }, headers=headers)

    except Exception as e:
        return make_response(500, {"error": str(e)})
