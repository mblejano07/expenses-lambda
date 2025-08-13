import os
import time
import hmac
import hashlib
import secrets
import json
import base64
from decimal import Decimal
from io import BytesIO

import boto3
import jwt
from requests_toolbelt.multipart import decoder

# =========================================================
# AWS CONFIGURATION (Switch between Local and Production)
# =========================================================

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Local endpoints for development (LocalStack / DynamoDB Local)
LOCALSTACK_URL = os.getenv("LOCALSTACK_URL", "http://host.docker.internal:4566")
LOCAL_DYNAMO_URL = os.getenv("LOCAL_DYNAMO_URL", "http://host.docker.internal:8000")

# =========================================================
# S3 CLIENT
# =========================================================
S3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    endpoint_url=LOCALSTACK_URL,        # ✅ Remove for production (real AWS S3)
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
)
BUCKET_NAME = os.getenv("BUCKET_NAME", "my-bucket")  # ✅ Replace in production

# =========================================================
# DynamoDB CLIENT & TABLES
# =========================================================
DYNAMODB = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    endpoint_url=LOCAL_DYNAMO_URL,      # ✅ Remove for production (real AWS DynamoDB)
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
)

INVOICE_TABLE = DYNAMODB.Table("Invoices")
EMPLOYEE_TABLE = DYNAMODB.Table("Employees")
OTP_TABLE = DYNAMODB.Table("OtpStore")
REFRESH_TOKENS_TABLE = DYNAMODB.Table("RefreshTokens")  # Requires SAM resource

# =========================================================
# SES CLIENT
# =========================================================
EMAIL_SOURCE = os.getenv("EMAIL_SOURCE", "noreply@example.com")
SES_MOCK_MODE = os.getenv("SES_MOCK_MODE", "true").lower() == "true"
SES_ENDPOINT_URL = os.getenv("SES_ENDPOINT_URL", None)

if SES_MOCK_MODE:
    SES = boto3.client(
        "ses",
        region_name=AWS_REGION,
        endpoint_url=SES_ENDPOINT_URL or LOCALSTACK_URL,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
    )
else:
    SES = boto3.client("ses", region_name=AWS_REGION)  # Uses prod creds/roles

# =========================================================
# RESPONSES & UTILS
# =========================================================
def make_response(status_code, body, headers=None):
    """Standard API Gateway Lambda proxy response."""
    if headers is None:
        headers = {"Content-Type": "application/json"}
    if not isinstance(body, str):
        body = json.dumps(body)
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": body,
    }

def decimal_to_float(obj):
    """Convert DynamoDB Decimal values to Python float."""
    if isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

def get_employee(employee_id):
    """Fetch employee details from DynamoDB."""
    resp = EMPLOYEE_TABLE.get_item(Key={"employee_id": employee_id})
    return resp.get("Item")

def parse_multipart(event):
    """Parse multipart/form-data requests (file uploads)."""
    form_data = {}
    file_data = None

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    content_type = headers.get("content-type")
    if not content_type or not content_type.startswith("multipart/form-data"):
        return form_data, file_data

    body_bytes = base64.b64decode(event["body"]) if event.get("isBase64Encoded") else (event.get("body") or "").encode("utf-8")
    multipart_data = decoder.MultipartDecoder(body_bytes, content_type)

    for part in multipart_data.parts:
        content_disposition = part.headers.get(b"Content-Disposition", b"")
        if b"filename" in content_disposition:
            filename_bytes = content_disposition.split(b"filename=")[1].strip(b'"')
            file_data = {
                "filename": filename_bytes.decode("utf-8", "ignore"),
                "content": part.content,
            }
        else:
            name_bytes = content_disposition.split(b"name=")[1].strip(b'"')
            try:
                form_data[name_bytes.decode("utf-8")] = part.content.decode("utf-8")
            except UnicodeDecodeError:
                form_data[name_bytes.decode("utf-8")] = part.content.decode("latin-1")

    return form_data, file_data

def is_valid_workmail_user(email):
    with open("workmail.json") as f:
        data = json.load(f)
    return email.lower() in (user.lower() for user in data.get("users", []))

# =========================================================
# AUTH CONFIG (JWT + Refresh)
# =========================================================
JWT_SECRET = os.getenv("JWT_SECRET", "local-secret")  # 🔒 In prod: AWS Secrets Manager
ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "900"))         # 15 min
REFRESH_TOKEN_TTL_SECONDS = int(os.getenv("REFRESH_TOKEN_TTL_SECONDS", "2592000"))   # 30 days
REFRESH_TOKEN_PEPPER = os.getenv("REFRESH_TOKEN_PEPPER", "change-me")                # 🔒 Secrets Manager
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_WINDOW_SECONDS = int(os.getenv("OTP_WINDOW_SECONDS", "900"))  # 15 min for rate limit window

def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

# -------- OTP hashing (salt + pepper) --------
def hash_otp(otp: str, salt: str) -> str:
    """
    Hash OTP for storage: sha256(pepper || ":" || salt || ":" || otp)
    Store only (otp_hash, salt). Do NOT store the raw OTP.
    """
    return _sha256_hex((REFRESH_TOKEN_PEPPER + ":" + salt + ":" + otp).encode())

# -------- Access & Refresh issuing --------
def issue_tokens(email: str):
    """
    Issue short-lived access token (JWT) + long-lived opaque refresh token.
    Refresh token is stored as a hash in DynamoDB and rotated on use.
    Returns: (access_token, refresh_token_combined, refresh_expires_at)
    """
    now = int(time.time())

    # Access token (JWT)
    access_payload = {
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL_SECONDS,
    }
    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm="HS256")

    # Refresh token: opaque secret split into token_id + raw; only store hash of raw
    token_id = secrets.token_urlsafe(16)
    refresh_raw = secrets.token_urlsafe(48)
    refresh_hash = _sha256_hex((REFRESH_TOKEN_PEPPER + ":" + refresh_raw).encode())
    refresh_expires_at = now + REFRESH_TOKEN_TTL_SECONDS

    REFRESH_TOKENS_TABLE.put_item(Item={
        "email": email,
        "token_id": token_id,
        "hash": refresh_hash,
        "created_at": now,
        "expires_at": refresh_expires_at,
        "rotated": False,
    })

    combined_refresh = f"{token_id}.{refresh_raw}"
    return access_token, combined_refresh, refresh_expires_at

def rotate_refresh_token(email: str, token_id: str):
    """Mark a refresh token as rotated (one-time use)."""
    try:
        REFRESH_TOKENS_TABLE.update_item(
            Key={"email": email, "token_id": token_id},
            UpdateExpression="SET rotated = :r",
            ExpressionAttributeValues={":r": True},
        )
    except Exception as e:
        # best-effort; don't fail the auth flow if we can't mark it
        print(f"rotate_refresh_token warning: {e}")

def verify_refresh_token(email: str, combined: str):
    """
    Verify and rotate refresh token.
    combined format: "<token_id>.<raw>"
    Returns (ok: bool, result: dict|None)
      If ok: result = {"access_token": ..., "refresh_token": ...}
    """
    if not combined or "." not in combined:
        return False, None

    token_id, raw = combined.split(".", 1)
    # Lookup stored token by (email, token_id)
    resp = REFRESH_TOKENS_TABLE.get_item(Key={"email": email, "token_id": token_id})
    item = resp.get("Item")
    if not item:
        return False, None

    now = int(time.time())
    if now > int(item.get("expires_at", 0)):
        return False, None
    if item.get("rotated"):
        return False, None

    expected = _sha256_hex((REFRESH_TOKEN_PEPPER + ":" + raw).encode())
    if not hmac.compare_digest(expected, item["hash"]):
        return False, None

    # Rotate old and issue new pair
    rotate_refresh_token(email, token_id)
    new_access, new_refresh, _ = issue_tokens(email)
    return True, {"access_token": new_access, "refresh_token": new_refresh}

# -------- Access token verification from API Gateway event --------
def verify_jwt_from_event(event):
    headers = event.get("headers", {}) or {}
    auth_header = headers.get("Authorization") or headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, "Missing or invalid Authorization header"

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None, "Invalid token type"
        return payload, None
    except jwt.ExpiredSignatureError:
        return None, "Token expired"
    except jwt.InvalidTokenError:
        return None, "Invalid token"

# =========================================================
# (Optional) COGNITO HELPERS — ignore if using custom auth
# =========================================================
# try:
#     COGNITO_IDP = boto3.client(
#         "cognito-idp",
#         region_name=AWS_REGION,
#         endpoint_url=LOCALSTACK_URL,  # Remove for production
#         aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
#         aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
#     )
#     USER_POOL_ID = os.getenv("USER_POOL_ID", "your_user_pool_id")
#     CLIENT_ID = os.getenv("CLIENT_ID", "your_app_client_id")
# except Exception:
#     COGNITO_IDP = None
#     USER_POOL_ID = None
#     CLIENT_ID = None

# def cognito_request_otp(email):
#     if not COGNITO_IDP or not CLIENT_ID:
#         raise RuntimeError("Cognito client not configured")
#     return COGNITO_IDP.initiate_auth(
#         AuthFlow="CUSTOM_AUTH",
#         AuthParameters={"USERNAME": email},
#         ClientId=CLIENT_ID,
#     )

# def cognito_verify_otp(email, otp_code, session):
#     if not COGNITO_IDP or not CLIENT_ID:
#         raise RuntimeError("Cognito client not configured")
#     return COGNITO_IDP.respond_to_auth_challenge(
#         ClientId=CLIENT_ID,
#         ChallengeName="CUSTOM_CHALLENGE",
#         Session=session,
#         ChallengeResponses={
#             "USERNAME": email,
#             "ANSWER": otp_code,
#         },
#     )
