import json
from common import make_response, verify_refresh_token

def lambda_handler(event, context):
    try:
        # accept refresh token from cookie or body
        headers = event.get("headers", {}) or {}
        cookie = headers.get("Cookie") or headers.get("cookie") or ""
        body = json.loads(event.get("body") or "{}")

        refresh_token = body.get("refresh_token")
        if not refresh_token and "refresh_token=" in cookie:
            # crude cookie parse
            for part in cookie.split(";"):
                part = part.strip()
                if part.startswith("refresh_token="):
                    refresh_token = part.split("=", 1)[1].strip()
                    break

        email = (body.get("email") or "").strip().lower()
        if not email or not refresh_token:
            return make_response(400, {"error": "email and refresh_token are required"})

        ok, payload = verify_refresh_token(email, refresh_token)
        if not ok:
            return make_response(401, {"error": "invalid or expired refresh token"})

        # payload contains new access + refresh (rotated)
        headers_out = {
            "Content-Type": "application/json",
        }
        try:
            # also rotate the cookie
            new_refresh = json.loads(payload)["refresh_token"]
            headers_out["Set-Cookie"] = "refresh_token=" + new_refresh + "; HttpOnly; Path=/; Max-Age=2592000; SameSite=Lax"
        except Exception:
            pass

        return make_response(200, payload, headers=headers_out)

    except Exception as e:
        return make_response(500, {"error": str(e)})
