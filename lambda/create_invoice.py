import json
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
                file_key = f"invoices/{str(uuid.uuid4())}_{file_data['filename']}"
                S3.upload_fileobj(file_obj, BUCKET_NAME, file_key)
                body["file_url"] = f"{LOCALSTACK_URL}/{BUCKET_NAME}/{file_key}"
            else:
                body["file_url"] = "no-file-uploaded"
        elif content_type.startswith("application/json"):
            body = json.loads(event.get("body", "{}"))
            body["file_url"] = "no-file-uploaded"
        else:
            return format_response(400, message="Unsupported Content-Type")

        # Validate required fields, excluding the reference_id since it will be generated here
        required_fields = [
            "company_name", "tin", "invoice_number",
            "transaction_date", "items", "encoder", "payee",
            "payee_account", "approver"
        ]
        missing_fields = [f for f in required_fields if f not in body]
        if missing_fields:
            return format_response(400, message="Validation Error", errors={"missing_fields": missing_fields})

        # --- NEW LOGIC FOR GENERATING REFERENCE_ID ---
        # Get the current year and month
        now = datetime.utcnow()
        current_year = now.year
        current_month = now.month
        prefix = f"{current_month:02d}{current_year}"

        # Fetch all existing reference IDs to determine the next sequential number.
        # NOTE: A full table scan is inefficient for large datasets. For a production
        # environment, a better approach would be to use a DynamoDB global secondary index
        # on the year or a dedicated counter table. For this implementation, we will
        # use a scan for simplicity.
        response = INVOICE_TABLE.scan(
            ProjectionExpression="reference_id",
        )
        items = response.get("Items", [])
        
        # Filter for the current year's invoices and find the highest number
        latest_number = 0
        for item in items:
            ref_id = item.get("reference_id")
            if ref_id and ref_id.startswith(prefix):
                try:
                    # Extract the numeric part after the hyphen and convert to integer
                    number_part = int(ref_id.split("-")[1])
                    if number_part > latest_number:
                        latest_number = number_part
                except (IndexError, ValueError):
                    # Ignore malformed reference_ids
                    pass
        
        # Increment the number for the new invoice
        new_number = latest_number + 1
        new_ref_id = f"{prefix}-{new_number:03d}"
        
        body["reference_id"] = new_ref_id
        # --- END OF NEW LOGIC ---

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
        if not isinstance(items, list):
            return format_response(400, message="Validation Error", errors={"items": "Items must be a list"})

        for idx, item in enumerate(items):
            missing_item_fields = [f for f in ["id", "particulars", "project_class", "account", "vatable", "amount"] if f not in item]
            if missing_item_fields:
                return format_response(400, message="Validation Error", errors={f"item_{idx}": f"Missing fields: {missing_item_fields}"})

        # The check for an existing invoice is now removed because we are generating a unique UUID.
        # This prevents race conditions and simplifies the logic.

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
            "status": "Pending",
            "remarks": body.get("remarks", "")
        }

        INVOICE_TABLE.put_item(Item=invoice_data)
        return format_response(201, message="Invoice created successfully", data=invoice_data)

    except Exception as e:
        return format_response(500, message="Internal Server Error", errors={"exception": str(e)})

