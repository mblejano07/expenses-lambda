from common import format_response, INVOICE_TABLE, verify_jwt_from_event

def lambda_handler(event, context):
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message=error)

    try:
        path_params = event.get("pathParameters", {}) or {}
        reference_id = path_params.get("reference_id")
        item_id = path_params.get("item_id")

        if not reference_id or not item_id:
            return format_response(400, message="reference_id and item_id are required in path")

        invoice = INVOICE_TABLE.get_item(Key={"reference_id": reference_id})
        if "Item" not in invoice:
            return format_response(404, message="Invoice not found")

        items = invoice["Item"].get("items", [])
        filtered_items = [i for i in items if str(i.get("id")) != item_id]

        if len(filtered_items) == len(items):
            return format_response(404, message="Item not found in invoice")

        INVOICE_TABLE.update_item(
            Key={"reference_id": reference_id},
            UpdateExpression="SET items = :items",
            ExpressionAttributeValues={":items": filtered_items}
        )

        return format_response(200, message=f"Item {item_id} deleted successfully")

    except Exception as e:
        return format_response(
            500,
            message="Internal Server Error",
            errors={"exception": str(e)}
        )
