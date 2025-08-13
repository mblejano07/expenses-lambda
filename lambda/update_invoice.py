import json
from common import format_response, INVOICE_TABLE, verify_jwt_from_event

def lambda_handler(event, context):
    """
    Updates invoice fields for the given reference_id.
    Only fields in allowed_fields can be updated.
    """
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message=error)

    try:
        reference_id = event.get("pathParameters", {}).get("reference_id")
        if not reference_id:
            return format_response(400, message="Missing reference_id in path parameters")

        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return format_response(400, message="Invalid JSON body")

        allowed_fields = ["company_name", "tin", "transaction_date", "items"]

        existing = INVOICE_TABLE.get_item(Key={"reference_id": reference_id})
        if "Item" not in existing:
            return format_response(404, message="Invoice not found")

        update_expr = []
        expr_attr_values = {}

        for field in allowed_fields:
            if field in body:
                update_expr.append(f"{field} = :{field}")
                expr_attr_values[f":{field}"] = body[field]

        if not update_expr:
            return format_response(400, message="No valid fields to update")

        INVOICE_TABLE.update_item(
            Key={"reference_id": reference_id},
            UpdateExpression="SET " + ", ".join(update_expr),
            ExpressionAttributeValues=expr_attr_values
        )

        return format_response(
            200,
            message="Invoice updated successfully",
            data={"reference_id": reference_id, "updated_fields": list(body.keys())}
        )

    except Exception as e:
        return format_response(
            500,
            message="Internal Server Error",
            errors={"exception": str(e)}
        )
