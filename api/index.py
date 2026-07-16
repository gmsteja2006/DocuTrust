import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "docutrust" / "backend"))

from main import app

# FastAPI app is automatically exposed to Vercel
