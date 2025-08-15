import json
from common import EMPLOYEE_TABLE, format_response, verify_jwt_from_event

def lambda_handler(event, context):
    """
    Lambda function to list all employees from the DynamoDB table.
    """
    # Verify the JWT token to ensure the user is authenticated.
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message="Unauthorized", errors={"auth": error})

    try:
        # Perform a scan to get all items. Note: for very large tables,
        # a query with pagination is more efficient and cost-effective.
        response = EMPLOYEE_TABLE.scan()
        employees = response.get('Items', [])

        # Process each employee item to handle data types.
        for employee in employees:
            # DynamoDB's String Set (SS) is returned as a Python 'set' object,
            # which is not JSON serializable. We must convert it to a list.
            if 'access_role' in employee:
                employee['access_role'] = list(employee['access_role'])
            
            # The is_approver logic is no longer needed, as the 'access_role'
            # attribute is the single source of truth for an employee's roles.
            # The frontend can check for the presence of the 'approver' role.
        return format_response(
            200,
            message="Employees fetched successfully",
            data={
                "employees": employees
            }
        )

    except Exception as e:
        print(e)
        return format_response(
            500,
            message="An unexpected error occurred",
            errors={"internal": str(e)}
        )
