"""Heroku deployment configuration for Tatvix AI Client Discovery System.

Heroku provides free tier with Heroku Scheduler add-on for cron jobs.
"""

import json

# Heroku Procfile
HEROKU_PROCFILE = """
worker: python -m scheduler.daily_runner
"""

# Heroku app.json for easy deployment
HEROKU_APP_JSON = {
    "name": "tatvix-client-discovery",
    "description": "Automated client discovery system for Tatvix Technologies",
    "repository": "https://github.com/your-username/tatvix-client-discovery",
    "keywords": ["python", "automation", "client-discovery", "iot"],
    "env": {
        "GROQ_API_KEY": {
            "description": "Groq AI API key for analysis",
            "required": True
        },
        "GOOGLE_SHEETS_ID": {
            "description": "Google Sheets ID for data storage",
            "required": True
        },
        "GOOGLE_SHEETS_CREDENTIALS_PATH": {
            "description": "Path to Google service account credentials",
            "value": "credentials/google_service_account.json",
            "required": True
        },
        "ENVIRONMENT": {
            "description": "Environment setting",
            "value": "production",
            "required": False
        }
    },
    "addons": [
        {
            "plan": "heroku-postgresql:mini"
        },
        {
            "plan": "scheduler:standard"
        }
    ],
    "buildpacks": [
        {
            "url": "heroku/python"
        }
    ],
    "stack": "heroku-22"
}

# Heroku Scheduler command
SCHEDULER_COMMAND = "python -c 'import asyncio; from scheduler.daily_runner import DailyClientDiscovery; discovery = DailyClientDiscovery(); asyncio.run(discovery.scheduled_run())'"

def create_heroku_files():
    """Create necessary files for Heroku deployment."""
    
    # Create Procfile
    with open("Procfile", "w") as f:
        f.write(HEROKU_PROCFILE.strip())
    
    # Create app.json
    with open("app.json", "w") as f:
        json.dump(HEROKU_APP_JSON, f, indent=2)
    
    # Create runtime.txt
    with open("runtime.txt", "w") as f:
        f.write("python-3.11.6")
    
    print("Heroku deployment files created:")
    print("- Procfile")
    print("- app.json") 
    print("- runtime.txt")
    print("\nNext steps:")
    print("1. Create Heroku account")
    print("2. Install Heroku CLI")
    print("3. heroku create tatvix-client-discovery")
    print("4. Add Heroku Scheduler: heroku addons:create scheduler:standard")
    print("5. Configure scheduler: heroku addons:open scheduler")
    print(f"6. Add daily job: {SCHEDULER_COMMAND}")
    print("7. Set time: 02:30 UTC (8:00 AM IST)")
    print("8. Deploy: git push heroku main")

if __name__ == "__main__":
    create_heroku_files()