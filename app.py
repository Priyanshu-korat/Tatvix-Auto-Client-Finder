"""Simple Flask app for Vercel deployment.

This provides a web interface and API endpoints for the 
Tatvix AI Client Discovery System.
"""

import asyncio
import sys
import os
import json
from pathlib import Path
from datetime import datetime
import pytz

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from flask import Flask, jsonify, request
    from scheduler.daily_runner import DailyClientDiscovery
except ImportError:
    # If Flask is not available, create a minimal WSGI app
    class Flask:
        def __init__(self, name):
            self.name = name
        def route(self, path, **kwargs):
            def decorator(f):
                return f
            return decorator
        def run(self, **kwargs):
            pass
    
    def jsonify(data):
        return json.dumps(data)
    
    class request:
        method = 'GET'

app = Flask(__name__)

@app.route('/')
def home():
    """Home page with system information."""
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    return f"""
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
            .button {{ background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; margin: 5px; }}
            .button:hover {{ background: #2980b9; }}
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
                <h3>🔗 Quick Actions</h3>
                <a href="/api/daily-discovery" class="button">🚀 Run Discovery Now</a>
                <a href="/api/status" class="button">📊 Get Status (JSON)</a>
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

@app.route('/api/status')
def status():
    """Get system status."""
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    status_info = {
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
    
    return jsonify(status_info)

@app.route('/api/daily-discovery', methods=['GET', 'POST'])
def daily_discovery():
    """Run daily discovery process."""
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
        return jsonify(result)
        
    except Exception as e:
        error_response = {
            'success': False,
            'error': str(e),
            'companies_added': 0
        }
        return jsonify(error_response), 500

# WSGI application for Vercel
application = app

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)