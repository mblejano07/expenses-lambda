import json
from common import EMPLOYEE_TABLE, format_response, verify_jwt_from_event

def lambda_handler(event, context):
    """
    Lambda function to list all employees from the DynamoDB table.
    """
    # Verify the JWT token to ensure the user is authenticated.
    # This assumes a successful login and token is sent in the header.
    payload, error = verify_jwt_from_event(event)
    if error:
        return format_response(401, message="Unauthorized", errors={"auth": error})

    try:
        # Scan the table to get all items. For a large number of employees,
        # you might want to consider pagination, but for this use case,
        # a simple scan is sufficient.
        response = EMPLOYEE_TABLE.scan()
        employees = response.get('Items', [])

        # The 'approver' flag is stored as a string or number, so
        # we'll convert it to a boolean to make it easier for the frontend.
        for employee in employees:
            if 'is_approver' in employee:
                employee['is_approver'] = bool(employee['is_approver'])

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

