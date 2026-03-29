"""Vercel serverless function for daily client discovery.

This function runs on a cron schedule (Monday-Friday at 8:00 AM IST)
and automatically adds 10 companies to the Google Sheet.
"""

import asyncio
import sys
import os
import json
from pathlib import Path
from datetime import datetime
import pytz

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from scheduler.daily_runner import DailyClientDiscovery
except ImportError as e:
    print(f"Import error: {e}")
    # Fallback for debugging
    sys.path.append('/var/task')
    from scheduler.daily_runner import DailyClientDiscovery


def handler(request):
    """Vercel serverless function handler for daily discovery."""
    
    async def run_discovery():
        try:
            # Log start time
            ist = pytz.timezone('Asia/Kolkata')
            start_time = datetime.now(ist)
            print(f"Starting daily discovery at {start_time.strftime('%Y-%m-%d %H:%M:%S IST')}")
            
            # Initialize and run discovery
            discovery = DailyClientDiscovery()
            await discovery.initialize()
            result = await discovery.run_daily_discovery()
            
            # Log results
            print(f"Discovery completed: {result}")
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                },
                'body': json.dumps({
                    'success': result['success'],
                    'companies_added': result.get('companies_added', 0),
                    'indian_companies': result.get('indian_companies', 0),
                    'international_companies': result.get('international_companies', 0),
                    'execution_time': result.get('execution_time', ''),
                    'message': 'Daily discovery completed successfully' if result['success'] else 'Discovery failed',
                    'companies': result.get('companies', [])
                })
            }
            
        except Exception as e:
            error_msg = f"Daily discovery failed: {str(e)}"
            print(f"Error: {error_msg}")
            
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                },
                'body': json.dumps({
                    'success': False,
                    'error': error_msg,
                    'companies_added': 0
                })
            }
    
    # Run the async function
    return asyncio.run(run_discovery())


# For manual testing
if __name__ == "__main__":
    # Test the function locally
    class MockRequest:
        pass
    
    result = handler(MockRequest())
    print("Test result:", result)