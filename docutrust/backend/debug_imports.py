import sys
print("1. Starting...", flush=True)

print("2. Importing config...", flush=True)
from config import settings
print("   OK", flush=True)

print("3. Importing database...", flush=True)
from database import connect_db
print("   OK", flush=True)

print("4. Importing FastAPI...", flush=True)
from fastapi import FastAPI
print("   OK", flush=True)

print("5. Importing api.upload router...", flush=True)
from api.upload import router as upload_router
print("   OK - upload", flush=True)

print("6. Importing api.query router...", flush=True)
from api.query import router as query_router
print("   OK - query", flush=True)

print("7. All imports successful!")
