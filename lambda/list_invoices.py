import json
from common import format_response, INVOICE_TABLE, decimal_to_float, verify_jwt_from_event

def lambda_handler(event, context):
    """
    Lambda function to fetch paginated invoice records from DynamoDB.

    Query parameters:
        - limit (optional): max number of items per page (default: 10)
        - last_evaluated_key (optional): JSON-encoded key from previous page
    """
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message=error)

    try:
        # Parse query parameters
        query_params = event.get("queryStringParameters") or {}
        try:
            limit = int(query_params.get("limit", 10))
        except ValueError:
            return format_response(400, message="Invalid 'limit' parameter")

        last_key_raw = query_params.get("last_evaluated_key")

        # Build scan parameters
        scan_kwargs = {"Limit": limit}
        if last_key_raw:
            try:
                scan_kwargs["ExclusiveStartKey"] = json.loads(last_key_raw)
            except json.JSONDecodeError:
                return format_response(400, message="Invalid 'last_evaluated_key' format")

        # Perform scan
        response = INVOICE_TABLE.scan(**scan_kwargs)

        invoices = [decimal_to_float(item) for item in response.get("Items", [])]
        result = {
            "invoices": invoices,
            "last_evaluated_key": None
        }

        if "LastEvaluatedKey" in response:
            result["last_evaluated_key"] = json.dumps(response["LastEvaluatedKey"])

        return format_response(
            200,
            message="Invoices retrieved successfully",
            data=result
        )

    except Exception as e:
        return format_response(
            500,
            message="Internal Server Error",
            errors={"exception": str(e)}
        )
