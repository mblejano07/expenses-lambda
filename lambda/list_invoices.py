import json
from common import format_response, INVOICE_TABLE, decimal_to_float, verify_jwt_from_event, EMPLOYEE_TABLE
from boto3.dynamodb.conditions import Attr

def get_employee_by_email(email):
    """
    Helper function to fetch an employee by their email from the EMPLOYEE_TABLE.
    This is used to "hydrate" the invoice data with full employee details.
    It also handles converting the DynamoDB set for access_role to a list.
    """
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
    Lambda function to fetch paginated invoice records from DynamoDB,
    with dynamic access control based on the user's role.

    - Admin and Approver users can see all invoices.
    - Standard users can only see invoices they have encoded.

    Query parameters:
        - limit (optional): max number of items per page (default: 10)
        - last_evaluated_key (optional): JSON-encoded key from previous page
    """
    # 1. Verify JWT and get user email
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message=error)

    user_email = payload.get("email")
    if not user_email:
        return format_response(401, message="Missing email in token payload")

    # 2. Fetch the employee record to check their role
    try:
        employee_response = EMPLOYEE_TABLE.get_item(Key={"email": user_email.lower()})
        employee = employee_response.get("Item")
        
        if not employee:
            return format_response(403, message="Employee record not found for user: " + user_email)
        
        # Ensure the access_role is a list for easy checking
        access_role = employee.get("access_role", [])
        if isinstance(access_role, set):
            access_role = list(access_role)
            
        is_admin_or_approver = "admin" in access_role or "approver" in access_role
        
        # Use the employee's email to filter invoices for standard users
        user_employee_email = employee.get("email")
        if not user_employee_email:
             return format_response(403, message="Employee email not available for filtering")

    except Exception as e:
        return format_response(500, message="Error fetching user's employee record", errors={"exception": str(e)})


    try:
        query_params = event.get("queryStringParameters", {}) or {}
        limit = int(query_params.get("limit", 10))

        scan_kwargs = {"Limit": limit}
        last_key_raw = query_params.get("last_evaluated_key")
        if last_key_raw:
            try:
                scan_kwargs["ExclusiveStartKey"] = json.loads(last_key_raw)
            except json.JSONDecodeError:
                return format_response(400, message="Invalid 'last_evaluated_key' format")

        # 3. Apply a filter expression for non-admin/approver users
        # This is the key part of the logic. If the user is NOT an admin or approver,
        # we filter the list to only show their encoded invoices.
        if not is_admin_or_approver:
            scan_kwargs["FilterExpression"] = Attr('encoder').eq(user_employee_email)

        # 4. Perform scan
        response = INVOICE_TABLE.scan(**scan_kwargs)
        invoices_raw = [decimal_to_float(item) for item in response.get("Items", [])]

        # 5. Enrich the invoice data with full employee details for display
        invoices_with_details = []
        for invoice in invoices_raw:
            # Re-check the access_role for each employee object to ensure it's a list
            # Look up the full employee object for the encoder
            encoder_data = invoice.get("encoder")
            if isinstance(encoder_data, str):
                encoder_employee = get_employee_by_email(encoder_data)
                invoice["encoder"] = encoder_employee or {"email": encoder_data, "first_name": "Unknown", "last_name": "User"}
            else:
                if isinstance(encoder_data.get("access_role"), set):
                    encoder_data["access_role"] = list(encoder_data["access_role"])
                invoice["encoder"] = encoder_data or {"email": "Unknown", "first_name": "Unknown", "last_name": "User"}

            # Look up the full employee object for the payee
            payee_data = invoice.get("payee")
            if isinstance(payee_data, str):
                payee_employee = get_employee_by_email(payee_data)
                invoice["payee"] = payee_employee or {"email": payee_data, "first_name": "Unknown", "last_name": "User"}
            else:
                if isinstance(payee_data.get("access_role"), set):
                    payee_data["access_role"] = list(payee_data["access_role"])
                invoice["payee"] = payee_data or {"email": "Unknown", "first_name": "Unknown", "last_name": "User"}

            # Look up the full employee object for the approver
            approver_data = invoice.get("approver")
            if isinstance(approver_data, str):
                approver_employee = get_employee_by_email(approver_data)
                invoice["approver"] = approver_employee or {"email": approver_data, "first_name": "Unknown", "last_name": "User"}
            else:
                if isinstance(approver_data.get("access_role"), set):
                    approver_data["access_role"] = list(approver_data["access_role"])
                invoice["approver"] = approver_data or {"email": "Unknown", "first_name": "Unknown", "last_name": "User"}

            invoices_with_details.append(invoice)

        result = {
            "invoices": invoices_with_details,
            "last_evaluated_key": None
        }

        if "LastEvaluatedKey" in response:
            last_eval_key = decimal_to_float(response["LastEvaluatedKey"])
            result["last_evaluated_key"] = json.dumps(last_eval_key)

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
