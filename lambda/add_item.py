import json
from common import make_response, INVOICE_TABLE

def lambda_handler(event, context):
    try:
        reference_id = event["pathParameters"]["reference_id"]
        item = json.loads(event.get("body", "{}"))
        required_fields = ["id", "particulars", "project_class", "account", "vatable", "amount"]

        for field in required_fields:
            if field not in item:
                return make_response(400, {"error": f"Missing item field: {field}"})

        invoice = INVOICE_TABLE.get_item(Key={"reference_id": reference_id})
        if "Item" not in invoice:
            return make_response(404, {"error": "Invoice not found"})

        items = invoice["Item"].get("items", [])
        items.append(item)

        INVOICE_TABLE.update_item(
            Key={"reference_id": reference_id},
            UpdateExpression="SET items = :items",
            ExpressionAttributeValues={":items": items}
        )
        return make_response(200, {"message": "Item added", "data": item})

    except Exception as e:
        return make_response(500, {"error": str(e)})
