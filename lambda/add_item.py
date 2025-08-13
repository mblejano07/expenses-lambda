import json
from common import format_response, INVOICE_TABLE, verify_jwt_from_event

def lambda_handler(event, context):
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message=error)

    try:
        path_params = event.get("pathParameters", {}) or {}
        reference_id = path_params.get("reference_id")

        if not reference_id:
            return format_response(400, message="reference_id is required in path")

        item = json.loads(event.get("body") or "{}")
        required_fields = [
            "id",
            "particulars",
            "project_class",
            "account",
            "vatable",
            "amount"
        ]

        for field in required_fields:
            if field not in item:
                return format_response(400, message=f"Missing item field: {field}")

        invoice = INVOICE_TABLE.get_item(Key={"reference_id": reference_id})
        if "Item" not in invoice:
            return format_response(404, message="Invoice not found")

        items = invoice["Item"].get("items", [])
        items.append(item)

        INVOICE_TABLE.update_item(
            Key={"reference_id": reference_id},
            UpdateExpression="SET items = :items",
            ExpressionAttributeValues={":items": items}
        )

        return format_response(
            200,
            message="Item added successfully",
            data=item
        )

    except Exception as e:
        return format_response(
            500,
            message="Internal Server Error",
            errors={"exception": str(e)}
        )
