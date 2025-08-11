from common import make_response, INVOICE_TABLE,verify_jwt_from_event

def lambda_handler(event, context):
    payload, error = verify_jwt_from_event(event)
    if error:
        return make_response(401, {"error": error})
    try:
        reference_id = event["pathParameters"]["reference_id"]
        item_id = event["pathParameters"]["item_id"]

        invoice = INVOICE_TABLE.get_item(Key={"reference_id": reference_id})
        if "Item" not in invoice:
            return make_response(404, {"error": "Invoice not found"})

        items = invoice["Item"].get("items", [])
        filtered_items = [i for i in items if str(i.get("id")) != item_id]

        if len(filtered_items) == len(items):
            return make_response(404, {"error": "Item not found"})

        INVOICE_TABLE.update_item(
            Key={"reference_id": reference_id},
            UpdateExpression="SET items = :items",
            ExpressionAttributeValues={":items": filtered_items}
        )
        return make_response(200, {"message": f"Item {item_id} deleted"})

    except Exception as e:
        return make_response(500, {"error": str(e)})
