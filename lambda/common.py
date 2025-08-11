import boto3
import json
from decimal import Decimal
import base64
from io import BytesIO
from requests_toolbelt.multipart import decoder

# =========================================================
# AWS CONFIGURATION (Switch between Local and Production)
# =========================================================

# ✅ Change this to your real AWS region when deploying
AWS_REGION = "us-east-1"

# ✅ Local endpoints for development (LocalStack / DynamoDB Local)
LOCALSTACK_URL = "http://host.docker.internal:4566"  # Local AWS service emulator
LOCAL_DYNAMO_URL = "http://host.docker.internal:8000"  # Local DynamoDB endpoint

# =========================================================
# S3 CLIENT
# =========================================================
S3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    endpoint_url=LOCALSTACK_URL,        # ✅ REMOVE for production (real AWS S3)
    aws_access_key_id="test",           # ✅ REMOVE for production (use IAM role or env credentials)
    aws_secret_access_key="test"        # ✅ REMOVE for production
)
BUCKET_NAME = "my-bucket"  # ✅ Replace with real bucket name in production

# =========================================================
# DynamoDB CLIENT
# =========================================================
DYNAMODB = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    endpoint_url=LOCAL_DYNAMO_URL,      # ✅ REMOVE for production (real AWS DynamoDB)
    aws_access_key_id="test",           # ✅ REMOVE for production
    aws_secret_access_key="test"        # ✅ REMOVE for production
)
INVOICE_TABLE = DYNAMODB.Table("Invoices")
EMPLOYEE_TABLE = DYNAMODB.Table("Employees")

# =========================================================
# COGNITO CLIENT
# =========================================================
COGNITO_IDP = boto3.client(
    "cognito-idp",
    region_name=AWS_REGION,
    endpoint_url=LOCALSTACK_URL,        # ✅ REMOVE for production (real AWS Cognito)
    aws_access_key_id="test",           # ✅ REMOVE for production
    aws_secret_access_key="test"        # ✅ REMOVE for production
)

# ✅ Replace with real values when deploying
USER_POOL_ID = "your_user_pool_id"
CLIENT_ID = "your_app_client_id"

# =========================================================
# COMMON UTILS
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
        "body": body
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

    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    content_type = headers.get("content-type")
    if not content_type or not content_type.startswith("multipart/form-data"):
        return form_data, file_data

    body_bytes = base64.b64decode(event["body"]) if event.get("isBase64Encoded") else event["body"].encode("utf-8")
    multipart_data = decoder.MultipartDecoder(body_bytes, content_type)

    for part in multipart_data.parts:
        content_disposition = part.headers.get(b"Content-Disposition", b"")
        if b"filename" in content_disposition:
            filename_bytes = content_disposition.split(b"filename=")[1].strip(b'"')
            file_data = {
                "filename": filename_bytes.decode("utf-8", "ignore"),
                "content": part.content
            }
        else:
            name_bytes = content_disposition.split(b"name=")[1].strip(b'"')
            try:
                form_data[name_bytes.decode("utf-8")] = part.content.decode("utf-8")
            except UnicodeDecodeError:
                form_data[name_bytes.decode("utf-8")] = part.content.decode("latin-1")

    return form_data, file_data

# =========================================================
# COGNITO UTILS
# =========================================================
def cognito_request_otp(email):
    """
    Send OTP to user email.
    Works with CUSTOM_AUTH flow in Cognito.
    """
    return COGNITO_IDP.initiate_auth(
        AuthFlow="CUSTOM_AUTH",
        AuthParameters={"USERNAME": email},
        ClientId=CLIENT_ID
    )

def cognito_verify_otp(email, otp_code, session):
    """
    Verify OTP and retrieve tokens from Cognito.
    """
    return COGNITO_IDP.respond_to_auth_challenge(
        ClientId=CLIENT_ID,
        ChallengeName="CUSTOM_CHALLENGE",
        Session=session,
        ChallengeResponses={
            "USERNAME": email,
            "ANSWER": otp_code
        }
    )
