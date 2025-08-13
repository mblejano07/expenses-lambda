from common import format_response, INVOICE_TABLE, decimal_to_float, verify_jwt_from_event

def lambda_handler(event, context):
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message=error)

    try:
        path_params = event.get("pathParameters", {}) or {}
        reference_id = path_params.get("reference_id")

        if not reference_id:
            return format_response(400, message="reference_id is required in path")

        response = INVOICE_TABLE.get_item(Key={"reference_id": reference_id})

        if "Item" in response:
            return format_response(
                200,
                message="Invoice retrieved successfully",
                data=decimal_to_float(response["Item"])
            )

        return format_response(404, message="Invoice not found")

    except Exception as e:
        return format_response(
            500,
            message="Internal Server Error",
            errors={"exception": str(e)}
        )
