from common import make_response, INVOICE_TABLE, decimal_to_float

def lambda_handler(event, context):
    try:
        reference_id = event["pathParameters"]["reference_id"]
        response = INVOICE_TABLE.get_item(Key={"reference_id": reference_id})
        if "Item" in response:
            return make_response(200, decimal_to_float(response["Item"]))
        return make_response(404, {"error": "Invoice not found"})
    except Exception as e:
        return make_response(500, {"error": str(e)})
