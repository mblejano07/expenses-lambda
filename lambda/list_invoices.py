from common import make_response, INVOICE_TABLE, decimal_to_float,verify_jwt_from_event

def lambda_handler(event, context):
    """
    Lambda function to fetch paginated invoice records from DynamoDB.
    
    Expected `event` query parameters:
        - limit (optional): max number of items per page (default: 10)
        - last_evaluated_key (optional): key from previous response for pagination
        - `last_evaluated_key` will be used by frontend to load next page
    """
    payload, error = verify_jwt_from_event(event)
    if error:
        return make_response(401, {"error": error})
    try:
        # Parse query parameters for pagination
        limit = int(event.get("queryStringParameters", {}).get("limit", 10))
        last_key = event.get("queryStringParameters", {}).get("last_evaluated_key")

        # Build scan parameters
        scan_kwargs = {"Limit": limit}
        if last_key:
            # Convert the key string back to dict
            # In frontend, you'll send this as JSON
            import json
            scan_kwargs["ExclusiveStartKey"] = json.loads(last_key)

        # Perform DynamoDB scan with pagination
        response = INVOICE_TABLE.scan(**scan_kwargs)

        # Convert DynamoDB Decimal types to float
        invoices = [decimal_to_float(item) for item in response.get("Items", [])]

        # Prepare response payload with pagination token if available
        result = {
            "invoices": invoices,
            "last_evaluated_key": None
        }
        if "LastEvaluatedKey" in response:
            import json
            result["last_evaluated_key"] = json.dumps(response["LastEvaluatedKey"])

        return make_response(200, result)

    except Exception as e:
        return make_response(500, {"error": str(e)})

