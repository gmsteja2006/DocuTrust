import sys
import os
from pathlib import Path

# Add backend to path BEFORE any other imports
backend_dir = str(Path(__file__).parent.parent / "docutrust" / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Also ensure the backend's parent is NOT in the path to avoid confusion
project_root = str(Path(__file__).parent.parent)

# Remove project root from path if present (prevents root 'api/' from shadowing backend 'api/')
sys.path = [p for p in sys.path if os.path.normpath(p) != os.path.normpath(project_root)]

from main import app  # noqa: E402

# Vercel exposes the `app` ASGI application automatically
