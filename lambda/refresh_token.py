import json
from common import format_response, verify_refresh_token

def lambda_handler(event, context):
    try:
        # ✅ Accept refresh token from cookie or body
        headers = event.get("headers", {}) or {}
        cookie_header = headers.get("Cookie") or headers.get("cookie") or ""
        body = json.loads(event.get("body") or "{}")

        refresh_token = body.get("refresh_token")
        if not refresh_token and "refresh_token=" in cookie_header:
            for part in cookie_header.split(";"):
                part = part.strip()
                if part.startswith("refresh_token="):
                    refresh_token = part.split("=", 1)[1].strip()
                    break

        email = (body.get("email") or "").strip().lower()
        if not email or not refresh_token:
            return format_response(
                400,
                message="Validation Error",
                errors={
                    "email": "Required" if not email else None,
                    "refresh_token": "Required" if not refresh_token else None
                }
            )

        ok, payload = verify_refresh_token(email, refresh_token)
        if not ok:
            return format_response(401, message="Invalid or expired refresh token")

        # ✅ payload contains new access + refresh (rotated)
        try:
            payload_data = json.loads(payload) if isinstance(payload, str) else payload
        except Exception:
            payload_data = payload

        headers_out = {"Content-Type": "application/json"}
        new_refresh = payload_data.get("refresh_token")
        if new_refresh:
            headers_out["Set-Cookie"] = (
                f"refresh_token={new_refresh}; HttpOnly; Path=/; Max-Age=2592000; SameSite=Lax"
            )

        return format_response(
            200,
            message="Token refreshed successfully",
            data=payload_data
        ) | {"headers": headers_out}  # merge in cookie headers

    except Exception as e:
        return format_response(
            500,
            message="Internal Server Error",
            errors={"exception": str(e)}
        )
