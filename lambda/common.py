import boto3
import json
from decimal import Decimal
import base64
from io import BytesIO
from requests_toolbelt.multipart import decoder

# AWS clients for local environment
S3 = boto3.client(
    "s3",
    region_name="us-east-1",
    endpoint_url="http://host.docker.internal:4566",
    aws_access_key_id="test",
    aws_secret_access_key="test"
)
BUCKET_NAME = "my-bucket"

DYNAMODB = boto3.resource(
    "dynamodb",
    region_name="us-east-1",
    endpoint_url="http://host.docker.internal:8000",
    aws_access_key_id="test",
    aws_secret_access_key="test"
)

INVOICE_TABLE = DYNAMODB.Table("Invoices")
EMPLOYEE_TABLE = DYNAMODB.Table("Employees")

def make_response(status_code, body, headers=None):
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
    if isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

def get_employee(employee_id):
    resp = EMPLOYEE_TABLE.get_item(Key={"employee_id": employee_id})
    return resp.get("Item")

def parse_multipart(event):
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
