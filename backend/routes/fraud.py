"""
Geospatial Fraud Detection — Impossible travel check + account suspension.
Tracks login IP/geo, computes travel feasibility, auto-suspends on fraud.
"""
import logging
import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

fraud_router = APIRouter()

# Maximum speeds (km/h) for travel feasibility
MAX_AIR_SPEED_KMH = 900
MAX_RAIL_SPEED_KMH = 300
MAX_ROAD_SPEED_KMH = 120
REACTIVATION_FEE_INR = 2500


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points on Earth in kilometers."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _is_impossible_travel(distance_km: float, elapsed_seconds: float) -> dict:
    """Check if the distance is physically impossible to cover in the elapsed time."""
    elapsed_hours = max(elapsed_seconds / 3600, 0.001)

    air_possible = distance_km <= MAX_AIR_SPEED_KMH * elapsed_hours
    rail_possible = distance_km <= MAX_RAIL_SPEED_KMH * elapsed_hours
    road_possible = distance_km <= MAX_ROAD_SPEED_KMH * elapsed_hours

    required_speed = distance_km / elapsed_hours

    return {
        "distance_km": round(distance_km, 1),
        "elapsed_hours": round(elapsed_hours, 2),
        "required_speed_kmh": round(required_speed, 1),
        "air_feasible": air_possible,
        "rail_feasible": rail_possible,
        "road_feasible": road_possible,
        "is_impossible": not air_possible,  # Impossible if even air travel can't cover it
    }


async def _get_ip_geo(ip: str) -> dict | None:
    """Get approximate geolocation from IP using ip-api.com (free, no key)."""
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return None
    try:
        import requests
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=status,lat,lon,city,regionName,country,isp", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "lat": data.get("lat", 0),
                    "lon": data.get("lon", 0),
                    "city": data.get("city", ""),
                    "region": data.get("regionName", ""),
                    "country": data.get("country", ""),
                    "isp": data.get("isp", ""),
                }
    except Exception as exc:
        logger.debug("IP geo lookup failed for %s: %s", ip, exc)
    return None


async def check_impossible_travel(user_key: str, ip: str, user_agent: str) -> dict | None:
    """Check if this login constitutes impossible travel from the last session.
    Returns fraud_info dict if suspicious, None if clean."""
    geo = await _get_ip_geo(ip)
    if not geo or (geo["lat"] == 0 and geo["lon"] == 0):
        return None

    # Record this session
    now = datetime.now(timezone.utc)
    session_doc = {
        "session_id": str(uuid.uuid4()),
        "user_key": user_key,
        "ip": ip,
        "user_agent": user_agent,
        "geo": geo,
        "ts": now.isoformat(),
        "ts_epoch": now.timestamp(),
    }

    # Find last session for this user
    last_session = await _state.db.login_sessions.find_one(
        {"user_key": user_key},
        {"_id": 0},
        sort=[("ts_epoch", -1)],
    )

    # Store current session
    await _state.db.login_sessions.insert_one(session_doc)

    if not last_session or not last_session.get("geo"):
        return None

    last_geo = last_session["geo"]
    last_ts = last_session.get("ts_epoch", 0)

    if last_geo.get("lat") == 0 and last_geo.get("lon") == 0:
        return None

    elapsed_seconds = now.timestamp() - last_ts
    if elapsed_seconds <= 0:
        return None

    distance_km = _haversine_km(
        last_geo["lat"], last_geo["lon"],
        geo["lat"], geo["lon"]
    )

    # Skip if same city/region (small distance)
    if distance_km < 50:
        return None

    travel_check = _is_impossible_travel(distance_km, elapsed_seconds)

    if travel_check["is_impossible"]:
        return {
            "fraud_detected": True,
            "current_location": f"{geo['city']}, {geo['region']}, {geo['country']}",
            "previous_location": f"{last_geo.get('city', '')}, {last_geo.get('region', '')}, {last_geo.get('country', '')}",
            "distance_km": travel_check["distance_km"],
            "elapsed_hours": travel_check["elapsed_hours"],
            "required_speed_kmh": travel_check["required_speed_kmh"],
            "ip": ip,
            "previous_ip": last_session.get("ip", ""),
            "user_agent": user_agent,
        }
    return None


async def suspend_account_for_fraud(user_key: str, fraud_info: dict):
    """Suspend user account and create fraud record."""
    now = datetime.now(timezone.utc)

    # Suspend the user
    await _state.db.app_users.update_one(
        {"user_key": user_key},
        {"$set": {
            "suspended": True,
            "suspended_at": now.isoformat(),
            "suspended_reason": "impossible_travel",
            "reactivation_fee": REACTIVATION_FEE_INR,
        }},
    )

    # Create fraud record
    fraud_doc = {
        "fraud_id": str(uuid.uuid4()),
        "user_key": user_key,
        "type": "impossible_travel",
        "details": fraud_info,
        "status": "pending",
        "reactivation_fee": REACTIVATION_FEE_INR,
        "created_at": now.isoformat(),
        "resolved_at": None,
    }
    await _state.db.fraud_incidents.insert_one(fraud_doc)

    # Push notification to admin CRM
    user = await _state.db.app_users.find_one({"user_key": user_key}, {"_id": 0, "username": 1})
    username = (user or {}).get("username", "Unknown")
    await _state.db.crm_messages.insert_one({
        "message_id": str(uuid.uuid4()),
        "from_user_key": user_key,
        "from_username": username,
        "to": "admin",
        "subject": f"Fraud Login Attempt - {username}",
        "body": (
            f"Impossible travel detected for user '{username}'.\n"
            f"From: {fraud_info.get('previous_location', 'Unknown')}\n"
            f"To: {fraud_info.get('current_location', 'Unknown')}\n"
            f"Distance: {fraud_info.get('distance_km', 0)} km in {fraud_info.get('elapsed_hours', 0)} hours\n"
            f"Required speed: {fraud_info.get('required_speed_kmh', 0)} km/h (exceeds air travel)\n"
            f"Account auto-suspended. Reactivation fee: INR {REACTIVATION_FEE_INR}"
        ),
        "type": "fraud_alert",
        "status": "unread",
        "ts": now.isoformat(),
        "ts_epoch": now.timestamp(),
    })

    logger.warning("Account suspended for fraud: user_key=%s, distance=%.1f km", user_key, fraud_info.get("distance_km", 0))


# ── Admin Fraud Management Endpoints ──────────────────────────────────────────

@fraud_router.get("/admin/fraud-incidents")
async def list_fraud_incidents(
    status: str = "pending",
    admin_user: dict = Depends(get_current_user),
):
    """List fraud incidents (admin only)."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")

    query = {}
    if status != "all":
        query["status"] = status
    cursor = _state.db.fraud_incidents.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(100)
    incidents = await cursor.to_list(100)

    # Enrich with username
    for inc in incidents:
        user = await _state.db.app_users.find_one(
            {"user_key": inc.get("user_key", "")}, {"_id": 0, "username": 1}
        )
        inc["username"] = (user or {}).get("username", "Unknown")

    return {"incidents": incidents, "count": len(incidents)}


@fraud_router.post("/admin/fraud-incidents/{fraud_id}/resolve")
async def resolve_fraud_incident(
    fraud_id: str,
    action: str = "reactivate",
    admin_user: dict = Depends(get_current_user),
):
    """Resolve a fraud incident (reactivate or confirm)."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")

    incident = await _state.db.fraud_incidents.find_one(
        {"fraud_id": fraud_id}, {"_id": 0}
    )
    if not incident:
        raise HTTPException(404, "Fraud incident not found")

    now = datetime.now(timezone.utc).isoformat()

    if action == "reactivate":
        # Unsuspend user
        await _state.db.app_users.update_one(
            {"user_key": incident["user_key"]},
            {"$set": {"suspended": False, "suspended_at": None, "suspended_reason": None, "reactivation_fee": 0}},
        )
        await _state.db.fraud_incidents.update_one(
            {"fraud_id": fraud_id},
            {"$set": {"status": "resolved_reactivated", "resolved_at": now, "resolved_by": admin_user.get("username")}},
        )
    else:
        await _state.db.fraud_incidents.update_one(
            {"fraud_id": fraud_id},
            {"$set": {"status": "confirmed_fraud", "resolved_at": now, "resolved_by": admin_user.get("username")}},
        )

    return {"resolved": True, "fraud_id": fraud_id, "action": action}


class ReactivationRequest(BaseModel):
    message: str = ""


@fraud_router.post("/account/reactivation-request")
async def submit_reactivation_request(
    req: ReactivationRequest,
    request: Request,
):
    """Submit a reactivation request (from suspended user via contact form).
    Note: This endpoint doesn't require auth since the user is suspended."""
    # Get user from a special header or body
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")

    # Find most recent fraud incident by IP
    incident = await _state.db.fraud_incidents.find_one(
        {"details.ip": ip, "status": "pending"},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not incident:
        raise HTTPException(404, "No pending fraud incident found for your session")

    user_key = incident.get("user_key", "")
    user = await _state.db.app_users.find_one({"user_key": user_key}, {"_id": 0, "username": 1})
    username = (user or {}).get("username", "Unknown")

    now = datetime.now(timezone.utc)
    await _state.db.crm_messages.insert_one({
        "message_id": str(uuid.uuid4()),
        "from_user_key": user_key,
        "from_username": username,
        "to": "admin",
        "subject": f"Reactivation Request - {username}",
        "body": req.message or "User is requesting account reactivation.",
        "type": "reactivation_request",
        "status": "unread",
        "ts": now.isoformat(),
        "ts_epoch": now.timestamp(),
    })

    return {"submitted": True, "message": "Your reactivation request has been submitted. An admin will review it shortly."}
