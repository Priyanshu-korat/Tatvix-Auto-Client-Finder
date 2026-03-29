"""Module entry point for Tatvix AI Client Discovery System.

This allows the system to be run as a module using:
python -m tatvix-ai-client-finder
"""

import asyncio
from main import main

if __name__ == "__main__":
    asyncio.run(main())