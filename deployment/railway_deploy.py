"""Railway deployment configuration for Tatvix AI Client Discovery System.

Railway.app provides free hosting for Python applications with cron-like scheduling.
"""

import os
from pathlib import Path

# Railway deployment script
RAILWAY_START_COMMAND = """
#!/bin/bash
cd /app
python -m scheduler.daily_runner
"""

# Procfile for Railway
PROCFILE_CONTENT = """
worker: python -m scheduler.daily_runner
"""

# Railway configuration
RAILWAY_CONFIG = {
    "name": "tatvix-client-discovery",
    "description": "Automated client discovery system for Tatvix Technologies",
    "environment": "production",
    "build_command": "pip install -r requirements.txt",
    "start_command": "python -m scheduler.daily_runner"
}

def create_railway_files():
    """Create necessary files for Railway deployment."""
    
    # Create Procfile
    with open("Procfile", "w") as f:
        f.write(PROCFILE_CONTENT.strip())
    
    # Create start script
    with open("start.sh", "w") as f:
        f.write(RAILWAY_START_COMMAND.strip())
    
    # Make start script executable
    os.chmod("start.sh", 0o755)
    
    print("Railway deployment files created:")
    print("- Procfile")
    print("- start.sh")
    print("\nNext steps:")
    print("1. Create account at railway.app")
    print("2. Connect your GitHub repository")
    print("3. Deploy from GitHub")
    print("4. Set environment variables in Railway dashboard")

if __name__ == "__main__":
    create_railway_files()