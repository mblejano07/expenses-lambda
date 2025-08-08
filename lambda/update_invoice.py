import json
from common import make_response, INVOICE_TABLE

def lambda_handler(event, context):
    try:
        reference_id = event["pathParameters"]["reference_id"]
        body = json.loads(event.get("body", "{}"))
        allowed_fields = ["company_name", "tin", "transaction_date", "items"]

        existing = INVOICE_TABLE.get_item(Key={"reference_id": reference_id})
        if "Item" not in existing:
            return make_response(404, {"error": "Invoice not found"})

        update_expr = []
        expr_attr_values = {}
        for field in allowed_fields:
            if field in body:
                update_expr.append(f"{field} = :{field}")
                expr_attr_values[f":{field}"] = body[field]

        if not update_expr:
            return make_response(400, {"error": "No valid fields to update"})

        INVOICE_TABLE.update_item(
            Key={"reference_id": reference_id},
            UpdateExpression="SET " + ", ".join(update_expr),
            ExpressionAttributeValues=expr_attr_values
        )
        return make_response(200, {"message": "Invoice updated"})

    except Exception as e:
        return make_response(500, {"error": str(e)})
