import json
import boto3
import os
from common import format_response, DYNAMODB

def lambda_handler(event, context):
    """
    AWS Lambda function to retrieve a list of all accounts from the DynamoDB table.
    """
    try:
        # Use the global DYNAMODB resource from common.py to get the table
        accounts_table = DYNAMODB.Table(os.getenv("ACCOUNTS_TABLE_NAME", "AccountsTable"))
        
        # Scan the table to get all items.
        # Note: For a small list, a scan is efficient. For a large table, you might
        # consider more specific queries or pagination.
        response = accounts_table.scan()
        accounts = response.get('Items', [])
        
        # Extract just the account_name from each item to return a clean list of strings
        account_names = [item.get('account_name') for item in accounts if item.get('account_name')]
        
        # Return a successful response with the list of account names
        return format_response(200, message="Accounts retrieved successfully", data=account_names)
        
    except Exception as e:
        # If any error occurs, return an error response
        print(f"Error fetching accounts: {e}")
        return format_response(500, message="Internal Server Error", errors={"message": str(e)})

