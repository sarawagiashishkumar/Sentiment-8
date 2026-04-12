"""
Payment System — Razorpay + Offline QR Payment with admin verification.
Razorpay keys are stored in MongoDB (configurable via Admin Dashboard).
"""
import base64
import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

import services.app_state as _state
from deps import get_current_user

logger = logging.getLogger(__name__)

payments_router = APIRouter()

REACTIVATION_FEE_INR = 2500
REACTIVATION_FEE_PAISE = REACTIVATION_FEE_INR * 100


async def _get_razorpay_config() -> dict:
    """Fetch Razorpay config from MongoDB (set by admin)."""
    doc = await _state.db.system_meta.find_one({"key": "razorpay_config"}, {"_id": 0})
    return doc or {}


async def _get_razorpay_client():
    """Create Razorpay client from stored credentials."""
    config = await _get_razorpay_config()
    key_id = config.get("key_id", "")
    key_secret = config.get("key_secret", "")
    if not key_id or not key_secret:
        return None
    import razorpay
    return razorpay.Client(auth=(key_id, key_secret))


# ── Admin: Configure Razorpay Keys ────────────────────────────────────────────

class RazorpayConfigRequest(BaseModel):
    key_id: str
    key_secret: str
    upi_id: str | None = None  # For QR code generation


@payments_router.post("/admin/payments/configure")
async def configure_razorpay(
    config: RazorpayConfigRequest,
    admin_user: dict = Depends(get_current_user),
):
    """Admin sets Razorpay API credentials."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")

    await _state.db.system_meta.update_one(
        {"key": "razorpay_config"},
        {"$set": {
            "key": "razorpay_config",
            "key_id": config.key_id.strip(),
            "key_secret": config.key_secret.strip(),
            "upi_id": (config.upi_id or "").strip(),
            "configured_by": admin_user.get("username"),
            "configured_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"configured": True}


@payments_router.get("/admin/payments/config-status")
async def get_payment_config_status(admin_user: dict = Depends(get_current_user)):
    """Check if Razorpay is configured."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")
    config = await _get_razorpay_config()
    return {
        "razorpay_configured": bool(config.get("key_id")),
        "upi_configured": bool(config.get("upi_id")),
        "configured_by": config.get("configured_by"),
        "configured_at": config.get("configured_at"),
    }


# ── Admin: Payment Verification ──────────────────────────────────────────────

@payments_router.get("/admin/payments/pending")
async def list_pending_payments(admin_user: dict = Depends(get_current_user)):
    """List all pending offline payments awaiting verification."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")
    cursor = _state.db.payments.find(
        {"method": "offline", "status": "pending_verification"},
        {"_id": 0, "proof_image": 0},  # Exclude large image from list
    ).sort("created_at", -1).limit(50)
    payments = await cursor.to_list(50)
    # Enrich with username
    for p in payments:
        user = await _state.db.app_users.find_one({"user_key": p.get("user_key", "")}, {"_id": 0, "username": 1})
        p["username"] = (user or {}).get("username", "Unknown")
    return {"payments": payments, "count": len(payments)}


@payments_router.get("/admin/payments/{payment_id}/proof")
async def get_payment_proof(payment_id: str, admin_user: dict = Depends(get_current_user)):
    """Get the uploaded proof image for a payment."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")
    doc = await _state.db.payments.find_one({"payment_id": payment_id}, {"_id": 0, "proof_image": 1})
    if not doc or not doc.get("proof_image"):
        raise HTTPException(404, "No proof image found")
    return {"proof_image": doc["proof_image"]}


@payments_router.post("/admin/payments/{payment_id}/verify")
async def verify_offline_payment(
    payment_id: str,
    action: str = "approve",
    admin_user: dict = Depends(get_current_user),
):
    """Approve or reject an offline payment."""
    if admin_user.get("role") not in ("owner", "sub_admin"):
        raise HTTPException(403, "Admin only")

    payment = await _state.db.payments.find_one({"payment_id": payment_id}, {"_id": 0, "proof_image": 0})
    if not payment:
        raise HTTPException(404, "Payment not found")

    now = datetime.now(timezone.utc).isoformat()

    if action == "approve":
        await _state.db.payments.update_one(
            {"payment_id": payment_id},
            {"$set": {"status": "verified", "verified_at": now, "verified_by": admin_user.get("username")}},
        )
        # Reactivate user account
        await _state.db.app_users.update_one(
            {"user_key": payment["user_key"]},
            {"$set": {"suspended": False, "suspended_at": None, "suspended_reason": None, "reactivation_fee": 0}},
        )
        # Resolve related fraud incident
        await _state.db.fraud_incidents.update_many(
            {"user_key": payment["user_key"], "status": "pending"},
            {"$set": {"status": "resolved_paid", "resolved_at": now, "resolved_by": admin_user.get("username")}},
        )
        return {"verified": True, "action": "approved", "user_reactivated": True}
    else:
        await _state.db.payments.update_one(
            {"payment_id": payment_id},
            {"$set": {"status": "rejected", "verified_at": now, "verified_by": admin_user.get("username")}},
        )
        return {"verified": False, "action": "rejected"}


# ── User: Razorpay Payment ────────────────────────────────────────────────────

@payments_router.post("/payments/create-order")
async def create_razorpay_order(purpose: str = "reactivation"):
    """Create a Razorpay order for reactivation fee (no auth needed — user is suspended)."""
    rz_client = await _get_razorpay_client()
    if not rz_client:
        raise HTTPException(503, "Payment gateway not configured. Use offline payment.")

    order = rz_client.order.create({
        "amount": REACTIVATION_FEE_PAISE,
        "currency": "INR",
        "receipt": f"reactivation_{uuid.uuid4().hex[:8]}",
        "payment_capture": 1,
    })

    config = await _get_razorpay_config()
    return {
        "order_id": order["id"],
        "amount": REACTIVATION_FEE_PAISE,
        "currency": "INR",
        "key_id": config.get("key_id", ""),
    }


class PaymentVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    user_key: str


@payments_router.post("/payments/verify")
async def verify_razorpay_payment(payload: PaymentVerifyRequest):
    """Verify Razorpay payment signature and reactivate account."""
    rz_client = await _get_razorpay_client()
    if not rz_client:
        raise HTTPException(503, "Payment gateway not configured")

    # Verify signature
    try:
        rz_client.utility.verify_payment_signature({
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature": payload.razorpay_signature,
        })
    except Exception:
        raise HTTPException(400, "Payment verification failed — signature mismatch")

    now = datetime.now(timezone.utc).isoformat()

    # Record payment
    await _state.db.payments.insert_one({
        "payment_id": str(uuid.uuid4()),
        "user_key": payload.user_key,
        "method": "razorpay",
        "razorpay_order_id": payload.razorpay_order_id,
        "razorpay_payment_id": payload.razorpay_payment_id,
        "amount": REACTIVATION_FEE_INR,
        "purpose": "reactivation",
        "status": "verified",
        "created_at": now,
        "verified_at": now,
    })

    # Reactivate user
    await _state.db.app_users.update_one(
        {"user_key": payload.user_key},
        {"$set": {"suspended": False, "suspended_at": None, "suspended_reason": None, "reactivation_fee": 0}},
    )
    await _state.db.fraud_incidents.update_many(
        {"user_key": payload.user_key, "status": "pending"},
        {"$set": {"status": "resolved_paid", "resolved_at": now}},
    )

    return {"verified": True, "reactivated": True}


# ── User: Offline QR Payment ──────────────────────────────────────────────────

@payments_router.get("/payments/qr-code")
async def get_payment_qr():
    """Generate UPI QR code for offline payment."""
    config = await _get_razorpay_config()
    upi_id = config.get("upi_id", "")

    if not upi_id:
        return {"qr_available": False, "message": "UPI payment not configured. Contact admin."}

    # Generate UPI deep link
    upi_link = f"upi://pay?pa={upi_id}&pn=TradingPlatform&am={REACTIVATION_FEE_INR}&cu=INR&tn=AccountReactivation"

    # Generate QR code as base64
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=2)
        qr.add_data(upi_link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_base64 = base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return {"qr_available": False, "message": "QR generation failed"}

    return {
        "qr_available": True,
        "qr_image": f"data:image/png;base64,{qr_base64}",
        "upi_id": upi_id,
        "amount": REACTIVATION_FEE_INR,
        "upi_link": upi_link,
    }


class OfflinePaymentUpload(BaseModel):
    user_key: str
    notes: str = ""


@payments_router.post("/payments/offline-upload")
async def upload_offline_proof(
    user_key: str,
    notes: str = "",
    file: UploadFile = File(...),
):
    """Upload payment proof screenshot for admin verification."""
    if not file:
        raise HTTPException(400, "Screenshot file required")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 5MB)")

    # Store as base64 in MongoDB
    proof_b64 = base64.b64encode(content).decode()
    content_type = file.content_type or "image/png"

    now = datetime.now(timezone.utc)
    payment_id = str(uuid.uuid4())

    await _state.db.payments.insert_one({
        "payment_id": payment_id,
        "user_key": user_key,
        "method": "offline",
        "amount": REACTIVATION_FEE_INR,
        "purpose": "reactivation",
        "status": "pending_verification",
        "proof_image": f"data:{content_type};base64,{proof_b64}",
        "notes": notes,
        "created_at": now.isoformat(),
    })

    # Notify admin via CRM
    user = await _state.db.app_users.find_one({"user_key": user_key}, {"_id": 0, "username": 1})
    username = (user or {}).get("username", "Unknown")
    await _state.db.crm_messages.insert_one({
        "message_id": str(uuid.uuid4()),
        "from_user_key": user_key,
        "from_username": username,
        "to": "admin",
        "subject": f"Offline Payment Proof — {username}",
        "body": f"User '{username}' uploaded payment proof for account reactivation (INR {REACTIVATION_FEE_INR}). Notes: {notes or 'None'}",
        "type": "payment_proof",
        "status": "unread",
        "ts": now.isoformat(),
        "ts_epoch": now.timestamp(),
        "payment_id": payment_id,
    })

    return {"uploaded": True, "payment_id": payment_id, "message": "Payment proof submitted. Admin will verify within 24 hours."}
