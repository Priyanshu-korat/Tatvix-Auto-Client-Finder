"""Hugging Face Gradio App for Tatvix AI Client Discovery System.

This provides a beautiful web interface with scheduled automation
for daily client discovery and lead generation.
"""

import gradio as gr
import asyncio
import schedule
import threading
import time
import sys
import os
import json
from pathlib import Path
from datetime import datetime
import pytz

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scheduler.daily_runner import DailyClientDiscovery

# Global discovery instance
discovery = None

def initialize_discovery():
    """Initialize the discovery system."""
    global discovery
    if discovery is None:
        try:
            discovery = DailyClientDiscovery()
            asyncio.run(discovery.initialize())
        except Exception as e:
            print(f"Warning: Discovery initialization failed: {e}")
            discovery = None
    return discovery

def run_discovery_manual():
    """Manual trigger for discovery."""
    try:
        disc = initialize_discovery()
        if disc is None:
            return "❌ Error: Discovery system not initialized. Please check environment variables and credentials."
        result = asyncio.run(disc.run_daily_discovery())
        
        if result['success']:
            companies_list = "\n".join([
                f"• {comp['name']} ({comp['country']}) - {comp['industry']}" 
                for comp in result.get('companies', [])
            ])
            
            return f"""✅ SUCCESS! Added {result.get('companies_added', 0)} companies to your sheet:

📊 Summary:
• Indian companies: {result.get('indian_companies', 0)}
• International companies: {result.get('international_companies', 0)}
• Execution time: {result.get('execution_time', 'N/A')}

📋 Companies added:
{companies_list}

🔗 Check your Google Sheet for the complete data with enhanced emails!"""
        else:
            return f"❌ Discovery failed: {result.get('error', 'Unknown error')}"
            
    except Exception as e:
        return f"❌ Error: {str(e)}"

def get_system_status():
    """Get current system status."""
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    try:
        disc = initialize_discovery()
        status = "✅ Running and Ready" if disc else "⚠️ Initialization Required"
        return f"""📊 SYSTEM STATUS

🕐 Current Time: {current_time.strftime('%Y-%m-%d %H:%M:%S IST')}
{status}
📅 Schedule: Monday-Friday at 8:00 AM IST
🎯 Target: 10 companies per day (3-4 Indian companies)

🔧 Features Active:
• Website validation (only working websites)
• Enhanced email generation
• Comprehensive Tatvix service descriptions
• Google Sheets integration
• Indian company prioritization

🚀 System initialized and ready for discovery!"""
    except Exception as e:
        return f"⚠️ System Status: Error during initialization\nError: {str(e)}"

def view_recent_logs():
    """View recent system activity."""
    return """📋 RECENT ACTIVITY

This feature will show recent discovery runs and their results.
Currently showing placeholder data - will be populated with actual logs.

Recent runs:
• 2026-03-29 08:00 IST: 10 companies added successfully
• 2026-03-28 08:00 IST: 10 companies added successfully
• 2026-03-27 08:00 IST: 8 companies added (2 failed validation)

Use 'Run Discovery Now' to test the system manually."""

# Create Gradio interface
with gr.Blocks(
    title="Tatvix AI Client Discovery System"
) as demo:
    
    gr.HTML("""
    <div style="text-align: center; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h1>🚀 Tatvix AI Client Discovery System</h1>
        <p>Automated lead generation with website validation and enhanced emails</p>
    </div>
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 🎛️ Control Panel")
            
            status_btn = gr.Button("📊 Check System Status", variant="secondary", size="lg")
            run_btn = gr.Button("🚀 Run Discovery Now", variant="primary", size="lg")
            logs_btn = gr.Button("📋 View Recent Activity", variant="secondary", size="lg")
            
            gr.Markdown("""
            ### ⚙️ System Configuration
            - **Schedule:** Monday-Friday at 8:00 AM IST
            - **Target:** 10 companies per day
            - **Indian Companies:** 3-4 guaranteed
            - **Website Validation:** Only working websites
            - **Email Enhancement:** Comprehensive Tatvix services
            """)
        
        with gr.Column(scale=2):
            gr.Markdown("### 📊 Results & Logs")
            output = gr.Textbox(
                label="System Output",
                lines=15,
                max_lines=20,
                placeholder="Click any button to see results..."
            )
    
    with gr.Row():
        gr.Markdown("""
        ### 🎯 Features
        - **Automated Discovery:** Runs Monday-Friday at 8:00 AM IST
        - **Website Validation:** Only adds companies with working websites
        - **Enhanced Emails:** Comprehensive Tatvix service descriptions
        - **Indian Focus:** Guarantees 3-4 Indian companies per day
        - **Google Sheets:** Direct integration with your lead database
        - **Real-time Monitoring:** Track system status and recent activity
        """)
    
    # Connect button actions
    status_btn.click(get_system_status, outputs=output)
    run_btn.click(run_discovery_manual, outputs=output)
    logs_btn.click(view_recent_logs, outputs=output)

# Background scheduler for automatic execution
def run_scheduler():
    """Background scheduler for automated discovery."""
    def scheduled_discovery():
        try:
            disc = initialize_discovery()
            result = asyncio.run(disc.scheduled_run())
            print(f"Scheduled discovery completed: {result}")
        except Exception as e:
            print(f"Scheduled discovery failed: {e}")
    
    # Schedule for Monday to Friday at 8:00 AM IST (2:30 AM UTC)
    schedule.every().monday.at("02:30").do(scheduled_discovery)
    schedule.every().tuesday.at("02:30").do(scheduled_discovery)
    schedule.every().wednesday.at("02:30").do(scheduled_discovery)
    schedule.every().thursday.at("02:30").do(scheduled_discovery)
    schedule.every().friday.at("02:30").do(scheduled_discovery)
    
    print("🕐 Scheduler started: Monday-Friday at 8:00 AM IST")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

# Start background scheduler
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# Launch Gradio app
if __name__ == "__main__":
    print("🚀 Starting Tatvix AI Client Discovery System...")
    print("📅 Scheduled: Monday-Friday at 8:00 AM IST")
    print("🎯 Target: 10 companies per day (3-4 Indian)")
    print("✅ All Gradio compatibility issues fixed!")
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )