from common import format_response, INVOICE_TABLE, verify_jwt_from_event

def lambda_handler(event, context):
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message=error)

    try:
        reference_id = event.get("pathParameters", {}).get("reference_id")
        if not reference_id:
            return format_response(400, message="Missing reference_id in path")

        INVOICE_TABLE.delete_item(Key={"reference_id": reference_id})
        return format_response(200, message="Invoice deleted successfully")

    except Exception as e:
        return format_response(
            500,
            message="Internal Server Error",
            errors={"exception": str(e)}
        )
