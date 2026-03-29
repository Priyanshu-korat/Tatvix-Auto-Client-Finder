"""Gradio app for Hugging Face Spaces deployment.

This provides a web interface and automated scheduling for the 
Tatvix AI Client Discovery System.
"""

import gradio as gr
import asyncio
import schedule
import threading
import time
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import json

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scheduler.daily_runner import DailyClientDiscovery

# Global variables
discovery_system = None
scheduler_running = False
last_execution_result = {"status": "Not run yet", "timestamp": ""}

async def initialize_system():
    """Initialize the discovery system."""
    global discovery_system
    try:
        discovery_system = DailyClientDiscovery()
        await discovery_system.initialize()
        return "✅ System initialized successfully"
    except Exception as e:
        return f"❌ Initialization failed: {str(e)}"

def run_discovery_manual():
    """Manual trigger for discovery."""
    global discovery_system, last_execution_result
    
    if not discovery_system:
        return "❌ System not initialized. Please wait for initialization to complete."
    
    try:
        # Run discovery
        result = asyncio.run(discovery_system.run_daily_discovery())
        
        # Update last execution result
        last_execution_result = {
            "status": "Success" if result['success'] else "Failed",
            "timestamp": result.get('execution_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')),
            "companies_added": result.get('companies_added', 0),
            "indian_companies": result.get('indian_companies', 0),
            "international_companies": result.get('international_companies', 0),
            "companies": result.get('companies', [])
        }
        
        if result['success']:
            companies_list = "\n".join([f"• {comp['name']} ({comp['country']}) - {comp['industry']}" 
                                      for comp in result.get('companies', [])])
            
            return f"""🎉 Discovery completed successfully!

📊 Results:
• Total companies added: {result.get('companies_added', 0)}
• Indian companies: {result.get('indian_companies', 0)}
• International companies: {result.get('international_companies', 0)}
• Execution time: {result.get('execution_time', 'N/A')}

📋 Companies added:
{companies_list}

✅ All companies have validated websites and enhanced emails!
"""
        else:
            return f"❌ Discovery failed: {result.get('error', 'Unknown error')}"
            
    except Exception as e:
        last_execution_result = {
            "status": "Error",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S IST'),
            "error": str(e)
        }
        return f"❌ Error running discovery: {str(e)}"

def get_system_status():
    """Get current system status."""
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    status_info = f"""🚀 Tatvix AI Client Discovery System

⏰ Current Time (IST): {current_time.strftime('%Y-%m-%d %H:%M:%S')}
📅 Schedule: Monday-Friday at 8:00 AM IST
🎯 Target: 10 companies per day (3-4 Indian companies)
🔄 Scheduler Status: {'Running' if scheduler_running else 'Starting...'}

📊 Last Execution:
• Status: {last_execution_result['status']}
• Time: {last_execution_result['timestamp']}
• Companies Added: {last_execution_result.get('companies_added', 'N/A')}

✨ Features:
• Website validation (only working websites)
• Enhanced email generation
• Comprehensive Tatvix service descriptions
• Google Sheets integration
• Indian company prioritization
• Automated scheduling
"""
    
    return status_info

def get_next_run_time():
    """Get next scheduled run time."""
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    # Calculate next weekday at 8 AM IST
    next_run = current_time.replace(hour=8, minute=0, second=0, microsecond=0)
    
    # If it's past 8 AM today, move to next day
    if current_time.hour >= 8:
        next_run += timedelta(days=1)
    
    # Skip weekends
    while next_run.weekday() >= 5:  # 5=Saturday, 6=Sunday
        next_run += timedelta(days=1)
    
    return f"⏰ Next scheduled run: {next_run.strftime('%A, %Y-%m-%d at 8:00 AM IST')}"

def run_scheduler():
    """Background scheduler function."""
    global scheduler_running
    
    # Set up the schedule
    schedule.every().monday.at("08:00").do(lambda: asyncio.run(discovery_system.scheduled_run()) if discovery_system else None)
    schedule.every().tuesday.at("08:00").do(lambda: asyncio.run(discovery_system.scheduled_run()) if discovery_system else None)
    schedule.every().wednesday.at("08:00").do(lambda: asyncio.run(discovery_system.scheduled_run()) if discovery_system else None)
    schedule.every().thursday.at("08:00").do(lambda: asyncio.run(discovery_system.scheduled_run()) if discovery_system else None)
    schedule.every().friday.at("08:00").do(lambda: asyncio.run(discovery_system.scheduled_run()) if discovery_system else None)
    
    scheduler_running = True
    print("🕐 Scheduler started - will run Monday-Friday at 8:00 AM IST")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

# Initialize system on startup
asyncio.run(initialize_system())

# Start background scheduler
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# Create Gradio interface
with gr.Blocks(
    title="Tatvix AI Client Discovery System",
    theme=gr.themes.Soft(),
    css="""
    .gradio-container {
        max-width: 1200px !important;
    }
    .status-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    """
) as demo:
    
    gr.Markdown("""
    # 🚀 Tatvix AI Client Discovery System
    
    **Automated client discovery system that finds and validates potential clients for Tatvix Technologies**
    
    ✨ **Features:** Website validation • Enhanced emails • Indian company focus • Google Sheets integration
    """)
    
    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("## 📊 System Control")
            
            with gr.Row():
                status_btn = gr.Button("📋 Get System Status", variant="secondary", size="lg")
                manual_run_btn = gr.Button("🚀 Run Discovery Now", variant="primary", size="lg")
            
            next_run_btn = gr.Button("⏰ Next Scheduled Run", variant="secondary")
            
        with gr.Column(scale=3):
            output_display = gr.Textbox(
                label="System Output",
                lines=20,
                max_lines=30,
                placeholder="Click buttons above to see system status or run discovery...",
                show_copy_button=True
            )
    
    gr.Markdown("""
    ## 🎯 How It Works
    
    1. **Automated Schedule:** Runs Monday-Friday at 8:00 AM IST
    2. **Company Selection:** Finds 10 companies per day (3-4 Indian companies guaranteed)
    3. **Website Validation:** Only adds companies with working, reachable websites
    4. **Email Generation:** Creates personalized emails highlighting all Tatvix services
    5. **Google Sheets:** Automatically adds validated leads to your spreadsheet
    
    ## 📈 Daily Results
    - **Target:** 10 companies/day = 50 companies/week = 200+ companies/month
    - **Quality:** 100% validated websites and personalized emails
    - **Focus:** Indian startup prioritization for better conversion rates
    """)
    
    # Button click handlers
    status_btn.click(
        fn=get_system_status,
        outputs=output_display,
        show_progress=True
    )
    
    manual_run_btn.click(
        fn=run_discovery_manual,
        outputs=output_display,
        show_progress=True
    )
    
    next_run_btn.click(
        fn=get_next_run_time,
        outputs=output_display,
        show_progress=True
    )
    
    # Auto-refresh status on load
    demo.load(
        fn=get_system_status,
        outputs=output_display
    )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        share=False
    )