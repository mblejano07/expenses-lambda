from common import make_response, INVOICE_TABLE, verify_jwt_from_event

def lambda_handler(event, context):
    payload, error = verify_jwt_from_event(event)
    if error:
        return make_response(401, {"error": error})
    try:
        reference_id = event["pathParameters"]["reference_id"]
        INVOICE_TABLE.delete_item(Key={"reference_id": reference_id})
        return make_response(200, {"message": "Invoice deleted"})
    except Exception as e:
        return make_response(500, {"error": str(e)})
