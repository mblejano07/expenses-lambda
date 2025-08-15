import json
from common import format_response, INVOICE_TABLE, decimal_to_float, EMPLOYEE_TABLE

def get_employee_by_email(email):
    """
    Helper function to fetch an employee by their email from the EMPLOYEE_TABLE.
    This is used to "hydrate" the invoice data with full employee details.
    """
    # Ensure a consistent case for email lookup
    if not email:
        return None
    response = EMPLOYEE_TABLE.get_item(Key={"email": email.lower()})
    employee = response.get("Item")
    if employee:
        # Check if the access_role is a set and convert it to a list if so
        if isinstance(employee.get("access_role"), set):
            employee["access_role"] = list(employee["access_role"])
    return employee

def lambda_handler(event, context):
    """
    Lambda function to fetch paginated invoice records from DynamoDB.
    This version retrieves ALL invoices without any user-specific filtering.
    """
    try:
        query_params = event.get("queryStringParameters", {}) or {}
        limit = int(query_params.get("limit", 10))

        # Build scan parameters
        scan_kwargs = {"Limit": limit}
        last_key_raw = query_params.get("last_evaluated_key")
        if last_key_raw:
            try:
                scan_kwargs["ExclusiveStartKey"] = json.loads(last_key_raw)
            except json.JSONDecodeError:
                return format_response(400, message="Invalid 'last_evaluated_key' format")

        # Perform a scan of the entire invoice table
        response = INVOICE_TABLE.scan(**scan_kwargs)
        invoices_raw = [decimal_to_float(item) for item in response.get("Items", [])]
        
        # Enrich the invoice data with full employee details for display
        invoices_with_details = []
        for invoice in invoices_raw:
            # Look up the full employee object for the encoder
            encoder_data = invoice.get("encoder")
            if isinstance(encoder_data, str):
                encoder_employee = get_employee_by_email(encoder_data)
                invoice["encoder"] = encoder_employee or {"email": encoder_data, "first_name": "Unknown", "last_name": "User"}
            else:
                # The data is already a dictionary, so we use it directly
                # Also, check if the access_role within the dictionary is a set and convert it
                if isinstance(encoder_data.get("access_role"), set):
                    encoder_data["access_role"] = list(encoder_data["access_role"])
                invoice["encoder"] = encoder_data or {"email": "Unknown", "first_name": "Unknown", "last_name": "User"}

            # Look up the full employee object for the payee
            payee_data = invoice.get("payee")
            if isinstance(payee_data, str):
                payee_employee = get_employee_by_email(payee_data)
                invoice["payee"] = payee_employee or {"email": payee_data, "first_name": "Unknown", "last_name": "User"}
            else:
                # Check for set in access_role and convert
                if isinstance(payee_data.get("access_role"), set):
                    payee_data["access_role"] = list(payee_data["access_role"])
                invoice["payee"] = payee_data or {"email": "Unknown", "first_name": "Unknown", "last_name": "User"}
                    
            # Look up the full employee object for the approver
            approver_data = invoice.get("approver")
            if isinstance(approver_data, str):
                approver_employee = get_employee_by_email(approver_data)
                invoice["approver"] = approver_employee or {"email": approver_data, "first_name": "Unknown", "last_name": "User"}
            else:
                # Check for set in access_role and convert
                if isinstance(approver_data.get("access_role"), set):
                    approver_data["access_role"] = list(approver_data["access_role"])
                invoice["approver"] = approver_data or {"email": "Unknown", "first_name": "Unknown", "last_name": "User"}

            invoices_with_details.append(invoice)

        result = {
            "invoices": invoices_with_details,
            "last_evaluated_key": None
        }

        if "LastEvaluatedKey" in response:
            # We must also ensure the LastEvaluatedKey is serializable if it contains sets
            last_eval_key = decimal_to_float(response["LastEvaluatedKey"])
            result["last_evaluated_key"] = json.dumps(last_eval_key)

        return format_response(
            200,
            message="All invoices retrieved successfully",
            data=result
        )

    except Exception as e:
        return format_response(
            500,
            message="Internal Server Error",
            errors={"exception": str(e)}
        )
