"""Main Vercel serverless function entry point.

This serves as the main handler for Vercel deployment and provides
a web interface to monitor the daily discovery system.
"""

import asyncio
import sys
import os
import json
from pathlib import Path
from datetime import datetime
import pytz
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

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


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler."""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/api/daily-discovery':
            # Run the daily discovery
            self.run_daily_discovery()
        elif parsed_path.path == '/api/status':
            # Return status information
            self.send_status()
        else:
            # Default response
            self.send_welcome()
    
    def do_POST(self):
        """Handle POST requests (for cron jobs)."""
        if self.path == '/api/daily-discovery':
            self.run_daily_discovery()
        else:
            self.send_error(404, "Not Found")
    
    def run_daily_discovery(self):
        """Run the daily discovery process."""
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
                    'success': result['success'],
                    'companies_added': result.get('companies_added', 0),
                    'indian_companies': result.get('indian_companies', 0),
                    'international_companies': result.get('international_companies', 0),
                    'execution_time': result.get('execution_time', ''),
                    'message': 'Daily discovery completed successfully' if result['success'] else 'Discovery failed',
                    'companies': result.get('companies', [])
                }
                
            except Exception as e:
                error_msg = f"Daily discovery failed: {str(e)}"
                print(f"Error: {error_msg}")
                
                return {
                    'success': False,
                    'error': error_msg,
                    'companies_added': 0
                }
        
        try:
            # Run the async function
            result = asyncio.run(run_discovery())
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_response = {
                'success': False,
                'error': str(e),
                'companies_added': 0
            }
            self.wfile.write(json.dumps(error_response, indent=2).encode())
    
    def send_status(self):
        """Send system status."""
        ist = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist)
        
        status = {
            'system': 'Tatvix AI Client Discovery System',
            'status': 'Running',
            'current_time_ist': current_time.strftime('%Y-%m-%d %H:%M:%S IST'),
            'schedule': 'Monday-Friday at 8:00 AM IST',
            'target': '10 companies per day (3-4 Indian companies)',
            'features': [
                'Website validation',
                'Enhanced email generation',
                'Comprehensive Tatvix service descriptions',
                'Google Sheets integration'
            ],
            'endpoints': {
                '/api/daily-discovery': 'Run daily discovery manually',
                '/api/status': 'Get system status'
            }
        }
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status, indent=2).encode())
    
    def send_welcome(self):
        """Send welcome page."""
        ist = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist)
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Tatvix AI Client Discovery System</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
                .status {{ background: #e8f5e8; padding: 15px; border-radius: 5px; border-left: 4px solid #27ae60; }}
                .info {{ background: #e3f2fd; padding: 15px; border-radius: 5px; border-left: 4px solid #2196f3; margin: 15px 0; }}
                .endpoint {{ background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0; font-family: monospace; }}
                ul {{ line-height: 1.6; }}
                .time {{ color: #7f8c8d; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚀 Tatvix AI Client Discovery System</h1>
                
                <div class="status">
                    <strong>✅ System Status:</strong> Running and Ready<br>
                    <span class="time">Current Time: {current_time.strftime('%Y-%m-%d %H:%M:%S IST')}</span>
                </div>
                
                <div class="info">
                    <h3>📋 System Configuration</h3>
                    <ul>
                        <li><strong>Schedule:</strong> Monday-Friday at 8:00 AM IST</li>
                        <li><strong>Target:</strong> 10 companies per day</li>
                        <li><strong>Indian Companies:</strong> 3-4 guaranteed per day</li>
                        <li><strong>Website Validation:</strong> Only working websites added</li>
                        <li><strong>Email Enhancement:</strong> Comprehensive Tatvix service descriptions</li>
                    </ul>
                </div>
                
                <div class="info">
                    <h3>🔗 API Endpoints</h3>
                    <div class="endpoint">GET /api/daily-discovery - Run daily discovery manually</div>
                    <div class="endpoint">GET /api/status - Get system status (JSON)</div>
                </div>
                
                <div class="info">
                    <h3>🎯 Features</h3>
                    <ul>
                        <li>Automated company discovery and validation</li>
                        <li>Website connectivity verification</li>
                        <li>Personalized email generation</li>
                        <li>Google Sheets integration</li>
                        <li>Indian company prioritization</li>
                        <li>Comprehensive service descriptions</li>
                    </ul>
                </div>
                
                <p style="text-align: center; color: #7f8c8d; margin-top: 30px;">
                    Powered by Tatvix Technologies | Deployed on Vercel
                </p>
            </div>
        </body>
        </html>
        """
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html_content.encode())


# For local testing
if __name__ == "__main__":
    from http.server import HTTPServer
    
    server = HTTPServer(('localhost', 8000), handler)
    print("Server running at http://localhost:8000")
    server.serve_forever()