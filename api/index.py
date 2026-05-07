import sys
from pathlib import Path

# Make dashboard modules importable
sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

from app import app

# Vercel expects the WSGI app to be named 'app'
