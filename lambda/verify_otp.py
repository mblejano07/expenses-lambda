import json, time, hmac
from common import format_response, OTP_TABLE, hash_otp, issue_tokens

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        email = (body.get("email") or "").strip().lower()
        otp_code = (body.get("otp_code") or "").strip()

        # ✅ Validation
        if not email or not otp_code:
            return format_response(
                400,
                message="Validation Error",
                errors={"email": "Required" if not email else None,
                        "otp_code": "Required" if not otp_code else None}
            )

        # ✅ Fetch OTP record
        resp = OTP_TABLE.get_item(Key={"email": email})
        item = resp.get("Item")
        if not item:
            return format_response(400, message="OTP not found or expired", errors={"otp_code": "Invalid or expired"})

        # ✅ Expiry check
        if int(time.time()) > int(item.get("expires_at", 0)):
            return format_response(400, message="OTP expired", errors={"otp_code": "Expired"})

        # ✅ Verify hashed OTP
        expected = hash_otp(otp_code, item["salt"])
        if not hmac.compare_digest(expected, item["otp_hash"]):
            return format_response(400, message="Invalid OTP code", errors={"otp_code": "Incorrect"})

        # ✅ OTP success — delete & issue tokens
        OTP_TABLE.delete_item(Key={"email": email})
        access_token, refresh_token, refresh_exp = issue_tokens(email)

        headers = {
            "Content-Type": "application/json",
            "Set-Cookie": (
                f"refresh_token={refresh_token}; "
                f"HttpOnly; Path=/; Max-Age=2592000; SameSite=Lax"
            )
        }

        return format_response(
            200,
            message="OTP verified successfully",
            data={
                "access_token": access_token,
                "refresh_token": refresh_token,  # Also in cookie
                "refresh_expires_at": refresh_exp
            }
        ) | {"headers": headers}  # ✅ Merge headers into API Gateway response

    except Exception as e:
        return format_response(500, message="Internal Server Error", errors={"exception": str(e)})
