"""
DocuTrust Client Profiles API — Manage settings profiles for different clients/departments.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from models import ClientProfile
from database import client_profiles_collection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Client Profiles"])


@router.get("/profiles")
async def list_profiles():
    """List all available client profiles."""
    col = client_profiles_collection()
    cursor = col.find({}, {"_id": 0}).sort("created_at", 1)
    profiles = await cursor.to_list(length=100)
    return {"profiles": profiles}


@router.post("/profiles", response_model=ClientProfile)
async def create_profile(profile: ClientProfile):
    """Create a new client/settings profile."""
    col = client_profiles_collection()

    # Check if profile_id already exists
    existing = await col.find_one({"profile_id": profile.profile_id})
    if existing:
        raise HTTPException(status_code=400, detail=f"Profile ID '{profile.profile_id}' already exists.")

    # If this profile is active, deactivate others
    if profile.is_active:
        await col.update_many({}, {"$set": {"is_active": False}})

    profile_dict = profile.model_dump()
    profile_dict["created_at"] = datetime.now(timezone.utc)
    
    await col.insert_one(profile_dict)
    logger.info(f"👤 Profile created: {profile.profile_id} - '{profile.name}'")
    return profile


@router.put("/profiles/{profile_id}/activate")
async def activate_profile(profile_id: str):
    """Set a profile as the currently active configuration."""
    col = client_profiles_collection()

    # Verify profile exists
    profile = await col.find_one({"profile_id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found.")

    # Deactivate all and activate selected
    await col.update_many({}, {"$set": {"is_active": False}})
    await col.update_one({"profile_id": profile_id}, {"$set": {"is_active": True}})

    logger.info(f"⚡ Active profile changed to: {profile_id}")
    return {"message": f"Profile '{profile_id}' is now active.", "profile_id": profile_id}


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    """Delete a client profile."""
    if profile_id == "default":
        raise HTTPException(status_code=400, detail="The default profile cannot be deleted.")

    col = client_profiles_collection()

    # Check if profile exists and is active
    profile = await col.find_one({"profile_id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found.")

    if profile.get("is_active"):
        # Activate default before deleting
        await col.update_one({"profile_id": "default"}, {"$set": {"is_active": True}})
        logger.info("Deactivating active profile before deletion, falling back to 'default'")

    await col.delete_one({"profile_id": profile_id})
    logger.info(f"🗑️ Profile deleted: {profile_id}")
    return {"message": f"Profile '{profile_id}' deleted successfully."}
