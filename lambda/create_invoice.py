import json
import uuid
from io import BytesIO
from datetime import datetime
from boto3.dynamodb.conditions import Key
from common import (
    S3, BUCKET_NAME, INVOICE_TABLE,
    parse_multipart, LOCALSTACK_URL, verify_jwt_from_event, format_response, EMPLOYEE_TABLE
)

# This is the updated get_employee helper function to use email as the primary key.
def get_employee(email):
    """Fetch employee details from DynamoDB using email as the primary key."""
    if not email:
        return None
    # Ensure the key is a dictionary with the primary key name
    resp = EMPLOYEE_TABLE.get_item(Key={"email": email.lower()})
    return resp.get("Item")

def lambda_handler(event, context):
    """
    Lambda function to create a new invoice record, handling both
    multipart/form-data and application/json requests.
    """
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message="Unauthorized", errors={"auth": error})

    try:
        req_headers = event.get("headers", {})
        content_type = req_headers.get("Content-Type") or req_headers.get("content-type", "")

        body = {}
        file_data = None
        body_from_event = event.get("body", "")

        # Check for an empty request body early to prevent parsing errors
        if not body_from_event:
            return format_response(400, message="Bad Request", errors={"body": "Request body is empty."})

        if content_type.startswith("multipart/form-data"):
            form_data_parts, file_data = parse_multipart(event)
            try:
                # Get the JSON string from the 'body' part and default to an empty JSON object if not found
                json_payload_str = form_data_parts.get("body", "{}")
                body = json.loads(json_payload_str)
            except json.JSONDecodeError as e:
                return format_response(400, message="Validation Error", errors={"body": f"Failed to parse JSON body from multipart form: {str(e)}"})
        elif content_type.startswith("application/json"):
            try:
                body = json.loads(body_from_event)
            except json.JSONDecodeError as e:
                return format_response(400, message="Bad Request", errors={"body": "Failed to parse JSON from request body: " + str(e)})
        else:
            return format_response(400, message="Unsupported Content-Type")

        if file_data:
            file_obj = BytesIO(file_data["content"])
            file_key = f"invoices/{str(uuid.uuid4())}_{file_data['filename']}"
            S3.upload_fileobj(file_obj, BUCKET_NAME, file_key)
            body["file_url"] = f"{LOCALSTACK_URL}/{BUCKET_NAME}/{file_key}"
        else:
            body["file_url"] = "no-file-uploaded"

        # Validate required fields
        required_fields = [
            "company_name", "tin", "invoice_number",
            "transaction_date", "items", "payee",
            "payee_account", "approver"
        ]
        missing_fields = [f for f in required_fields if f not in body]
        if missing_fields:
            return format_response(400, message="Validation Error", errors={"missing_fields": missing_fields})

        # --- LOGIC FOR GENERATING REFERENCE_ID ---
        now = datetime.utcnow()
        current_year = now.year
        current_month = now.month
        prefix = f"{current_month:02d}{current_year}"

        response = INVOICE_TABLE.scan(
            ProjectionExpression="reference_id",
        )
        items = response.get("Items", [])

        latest_number = 0
        for item in items:
            ref_id = item.get("reference_id")
            if ref_id and ref_id.startswith(prefix):
                try:
                    number_part = int(ref_id.split("-")[1])
                    if number_part > latest_number:
                        latest_number = number_part
                except (IndexError, ValueError):
                    pass

        new_number = latest_number + 1
        new_ref_id = f"{prefix}-{new_number:03d}"

        body["reference_id"] = new_ref_id
        # --- END OF LOGIC ---

        user_email = payload.get("email")
        if not user_email:
            return format_response(401, message="Missing email in token payload")

        encoder = get_employee(user_email)
        if not encoder:
            # The correct way to include a variable for debugging
            return format_response(403, message=f"Employee record not found for the logged-in user: {encoder}")

        payee_email = body.get("payee")
        approver_email = body.get("approver")
        approver = get_employee(approver_email)

        if not approver:
            return format_response(400, message="Validation Error", errors={"approver": f"Approver {approver_email} not found"})

        # Get the access_role, which is a DynamoDB Set, and convert it to a Python list
        approver_roles = list(approver.get("access_role", set()))

        if "approver" not in approver_roles:
            return format_response(400, message="Validation Error", errors={"approver": f"Selected approver is not marked as an approver. Roles found: {approver_roles}"})

        items_raw = body.get("items")
        if not items_raw:
             return format_response(400, message="Validation Error", errors={"items": "Items field is missing or empty."})

        if isinstance(items_raw, str):
            try:
                items = json.loads(items_raw)
            except json.JSONDecodeError as e:
                return format_response(400, message="Validation Error", errors={"items": f"Failed to parse items JSON: {str(e)}"})
        else:
            items = items_raw

        if not isinstance(items, list):
            return format_response(400, message="Validation Error", errors={"items": "Items must be a list"})

        for idx, item in enumerate(items):
            missing_item_fields = [f for f in ["particulars", "project_class", "account", "vatable", "amount"] if f not in item]
            if missing_item_fields:
                return format_response(400, message="Validation Error", errors={f"item_{idx}": f"Missing fields: {missing_item_fields}"})

        invoice_data = {
            "reference_id": new_ref_id,
            "company_name": body["company_name"],
            "tin": body["tin"],
            "invoice_number": body["invoice_number"],
            "transaction_date": body["transaction_date"],
            "items": items,
            "encoder": encoder.get("email"),
            "payee": payee_email, # Directly use the email from the request body
            "payee_account": body["payee_account"],
            "approver": approver.get("email"),
            "file_url": body.get("file_url", "no-file-uploaded"),
            "encoding_date": datetime.utcnow().isoformat(),
            "status": "Pending",
            "remarks": body.get("remarks", "")
        }

        INVOICE_TABLE.put_item(Item=invoice_data)
        return format_response(201, message="Invoice created successfully", data=invoice_data)

    except Exception as e:
        return format_response(500, message="Internal Server Error", errors={"exception": str(e)})

