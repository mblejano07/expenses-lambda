import json
import uuid
from io import BytesIO
from datetime import datetime
from common import (
    make_response, S3, BUCKET_NAME, INVOICE_TABLE, get_employee,
    parse_multipart, LOCALSTACK_URL, verify_jwt_from_event, format_response
)

def lambda_handler(event, context):
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message="Unauthorized", errors={"auth": error})

    try:
        headers = event.get("headers", {})
        content_type = headers.get("Content-Type") or headers.get("content-type", "")

        if content_type.startswith("multipart/form-data"):
            body, file_data = parse_multipart(event)
            if file_data:
                file_obj = BytesIO(file_data["content"])
                file_key = f"invoices/{uuid.uuid4()}_{file_data['filename']}"
                S3.upload_fileobj(file_obj, BUCKET_NAME, file_key)
                body["file_url"] = f"{LOCALSTACK_URL}/{BUCKET_NAME}/{file_key}"
            else:
                body["file_url"] = "no-file-uploaded"
        elif content_type.startswith("application/json"):
            body = json.loads(event.get("body", "{}"))
            body["file_url"] = "no-file-uploaded"
        else:
            return format_response(400, message="Unsupported Content-Type")

        # Validate required fields
        required_fields = [
            "reference_id", "company_name", "tin", "invoice_number",
            "transaction_date", "items", "encoder", "payee",
            "payee_account", "approver"
        ]
        missing_fields = [f for f in required_fields if f not in body]
        if missing_fields:
            return format_response(400, message="Validation Error", errors={"missing_fields": missing_fields})

        # Validate employees
        encoder = get_employee(body["encoder"])
        payee = get_employee(body["payee"])
        approver = get_employee(body["approver"])

        if not encoder:
            return format_response(400, message="Validation Error", errors={"encoder": f"{body['encoder']} not found"})
        if not payee:
            return format_response(400, message="Validation Error", errors={"payee": f"{body['payee']} not found"})
        if not approver:
            return format_response(400, message="Validation Error", errors={"approver": f"{body['approver']} not found"})
        if not approver.get("is_approver", False):
            return format_response(400, message="Validation Error", errors={"approver": "Selected approver is not marked as approver"})

        # Validate invoice items
        items = json.loads(body["items"]) if isinstance(body["items"], str) else body["items"]
        for idx, item in enumerate(items):
            missing_item_fields = [f for f in ["id", "particulars", "project_class", "account", "vatable", "amount"] if f not in item]
            if missing_item_fields:
                return format_response(400, message="Validation Error", errors={f"item_{idx}": f"Missing fields: {missing_item_fields}"})

        # Check for existing invoice
        existing = INVOICE_TABLE.get_item(Key={"reference_id": body["reference_id"]})
        if "Item" in existing:
            return format_response(409, message="Invoice already exists")

        # Prepare invoice data
        invoice_data = {
            "reference_id": body["reference_id"],
            "company_name": body["company_name"],
            "tin": body["tin"],
            "invoice_number": body["invoice_number"],
            "transaction_date": body["transaction_date"],
            "items": items,
            "encoder": encoder,
            "payee": payee,
            "payee_account": body["payee_account"],
            "approver": approver,
            "file_url": body.get("file_url", "no-file-uploaded"),
            "encoding_date": datetime.utcnow().isoformat(),
            "status": "Pending"
        }

        INVOICE_TABLE.put_item(Item=invoice_data)
        return format_response(201, message="Invoice created successfully", data=invoice_data)

    except Exception as e:
        return format_response(500, message="Internal Server Error", errors={"exception": str(e)})
