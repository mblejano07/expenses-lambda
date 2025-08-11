import json
import uuid
from io import BytesIO
from datetime import datetime
from common import make_response, S3, BUCKET_NAME, INVOICE_TABLE, get_employee, parse_multipart, LOCALSTACK_URL, verify_jwt_from_event

def lambda_handler(event, context):
    payload, error = verify_jwt_from_event(event)
    if error:
        return make_response(401, {"error": error})
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
            return make_response(400, {"error": "Unsupported Content-Type"})

        # Validate required fields
        required_fields = [
            "reference_id", "company_name", "tin", "invoice_number", "transaction_date",
            "items", "encoder", "payee", "payee_account", "approver"
        ]
        for field in required_fields:
            if field not in body:
                return make_response(400, {"error": f"Missing field: {field}"})

        # Validate employees
        encoder = get_employee(body["encoder"])
        payee = get_employee(body["payee"])
        approver = get_employee(body["approver"])

        if not encoder:
            return make_response(400, {"error": f"Encoder {body['encoder']} not found"})
        if not payee:
            return make_response(400, {"error": f"Payee {body['payee']} not found"})
        if not approver:
            return make_response(400, {"error": f"Approver {body['approver']} not found"})
        if not approver.get("is_approver", False):
            return make_response(400, {"error": "Selected approver is not marked as approver"})

        # Validate invoice items
        items = json.loads(body["items"]) if isinstance(body["items"], str) else body["items"]
        for item in items:
            for f in ["id", "particulars", "project_class", "account", "vatable", "amount"]:
                if f not in item:
                    return make_response(400, {"error": f"Missing item field: {f}"})

        # Check for existing invoice
        existing = INVOICE_TABLE.get_item(Key={"reference_id": body["reference_id"]})
        if "Item" in existing:
            return make_response(409, {"error": "Invoice already exists"})

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
        return make_response(201, {"message": "Invoice created", "data": invoice_data})

    except Exception as e:
        return make_response(500, {"error": str(e)})
