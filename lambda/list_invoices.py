from common import make_response, INVOICE_TABLE, decimal_to_float

def lambda_handler(event, context):
    try:
        response = INVOICE_TABLE.scan()
        invoices = [decimal_to_float(item) for item in response.get("Items", [])]
        return make_response(200, invoices)
    except Exception as e:
        return make_response(500, {"error": str(e)})
