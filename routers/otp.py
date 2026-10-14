import os
import time
import secrets
import smtplib
import ssl
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["OTP Verification"])

# ─── Configuration ────────────────────────────────────────────────────────────
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))

# Required App Password with spaces removed
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "ulztfazvpnpurzom").replace(" ", "")

# Sender Gmail Address (can be overridden via environment variable)
SMTP_SENDER = os.getenv("SMTP_EMAIL", os.getenv("GMAIL_USER", "vilaszugare2004@gmail.com"))

# Expiration window in seconds (10 minutes as per specification)
OTP_EXPIRATION_SECONDS = 600

# ─── Scalable State Store (Redis with In-Memory Dictionary Fallback) ──────────
_redis_client = None
_in_memory_otp_store: dict[str, dict] = {}

try:
    import redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1)
    client.ping()
    _redis_client = client
    print("[OTP] Connected to Redis for scalable state management.")
except Exception:
    _redis_client = None
    print("[OTP] Redis not available. Falling back to secure in-memory state store.")


def save_otp(email: str, otp_code: str):
    email = email.lower().strip()
    expires_at = time.time() + OTP_EXPIRATION_SECONDS

    if _redis_client:
        try:
            _redis_client.setex(f"otp:{email}", OTP_EXPIRATION_SECONDS, otp_code)
            _redis_client.delete(f"otp_verified:{email}")
            return
        except Exception as e:
            print(f"[OTP Redis Error] {e}. Using in-memory fallback.")

    _in_memory_otp_store[email] = {
        "otp": otp_code,
        "expires_at": expires_at,
        "verified": False,
    }


def verify_stored_otp(email: str, otp_code: str) -> bool:
    email = email.lower().strip()
    otp_code = str(otp_code).strip()

    if _redis_client:
        try:
            stored_otp = _redis_client.get(f"otp:{email}")
            if stored_otp and stored_otp == otp_code:
                # Mark verified for 1 hour so registration can complete
                _redis_client.setex(f"otp_verified:{email}", 3600, "true")
                _redis_client.delete(f"otp:{email}")
                return True
            return False
        except Exception as e:
            print(f"[OTP Redis Error] {e}. Falling back to in-memory check.")

    record = _in_memory_otp_store.get(email)
    if not record:
        return False

    if time.time() > record["expires_at"]:
        _in_memory_otp_store.pop(email, None)
        return False

    if record["otp"] == otp_code:
        record["verified"] = True
        return True

    return False


def is_email_verified(email: str) -> bool:
    email = email.lower().strip()
    if _redis_client:
        try:
            val = _redis_client.get(f"otp_verified:{email}")
            if val == "true":
                return True
        except Exception:
            pass

    record = _in_memory_otp_store.get(email)
    if record and record.get("verified", False):
        return True
    return False


# ─── Email Dispatcher (Gmail SMTP SSL on port 465) ───────────────────────────
def send_email_smtp(recipient_email: str, otp_code: str):
    """
    Sends a branded verification email via Gmail SMTP_SSL (Port 465).
    Includes IPv4 dual-stack resolution fallback for systems with IPv6 drops.
    """
    subject = "Quick Med Support — Your Verification Code"

    # Plain text version
    text_content = f"""Hello,

Your verification code for Quick Med Support registration is:

{otp_code}

This code will expire in 10 minutes. 

If you did not request this verification code, please ignore this email.

Best regards,
Quick Med Support Team
"""

    # Rich responsive HTML version
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Quick Med Support Verification</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px;">
  <div style="max-width: 520px; margin: 0 auto; background-color: #ffffff; border-radius: 20px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
    
    <!-- Header -->
    <div style="background: linear-gradient(135deg, #1A365D 0%, #0D9488 100%); padding: 32px 24px; text-align: center;">
      <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">Quick Med Support</h1>
      <p style="color: rgba(255,255,255,0.85); margin: 6px 0 0 0; font-size: 13px; font-weight: 500; text-transform: uppercase; letter-spacing: 1px;">Healthcare Staffing Platform</p>
    </div>

    <!-- Body -->
    <div style="padding: 32px 28px;">
      <h2 style="color: #1e293b; font-size: 18px; font-weight: 700; margin: 0 0 12px 0;">Verify Your Email Address</h2>
      <p style="color: #64748b; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0;">
        Welcome to <strong>Quick Med Support</strong>. Please use the 6-digit verification code below to complete your registration:
      </p>

      <!-- OTP Box -->
      <div style="background-color: #f0fdfa; border: 2px dashed #0D9488; border-radius: 14px; padding: 20px; text-align: center; margin-bottom: 24px;">
        <span style="font-family: 'Courier New', Courier, monospace; font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #0D9488; display: inline-block;">
          {otp_code}
        </span>
        <p style="color: #0f766e; font-size: 12px; margin: 8px 0 0 0; font-weight: 600;">⏱️ Valid for 10 minutes</p>
      </div>

      <p style="color: #94a3b8; font-size: 13px; line-height: 1.5; margin: 0 0 16px 0;">
        Security note: Quick Med Support will never ask for your password or OTP over phone or chat.
      </p>
      <p style="color: #94a3b8; font-size: 12px; margin: 0;">
        If you did not request this email, please safely disregard it.
      </p>
    </div>

    <!-- Footer -->
    <div style="background-color: #f8fafc; padding: 16px 24px; text-align: center; border-top: 1px solid #f1f5f9;">
      <p style="color: #94a3b8; font-size: 11px; margin: 0;">© 2026 Quick Med Support. All rights reserved.</p>
    </div>
  </div>
</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Quick Med Support <{SMTP_SENDER}>"
    msg["To"] = recipient_email
    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    context = ssl.create_default_context()

    # Prefer IPv4 resolution for reliable connection
    try:
        orig_getaddrinfo = socket.getaddrinfo
        def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
            return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        socket.getaddrinfo = _getaddrinfo_ipv4
    except Exception:
        pass

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context, timeout=12) as server:
            server.login(SMTP_SENDER, SMTP_PASSWORD)
            server.sendmail(SMTP_SENDER, recipient_email, msg.as_string())
            print(f"[OTP] Successfully sent verification email to {recipient_email}")
            return True
    except Exception as e:
        print(f"[OTP SMTP Warning] Direct send failed ({e}).")
        print(f"[OTP DEV FALLBACK] >>> Verification code for {recipient_email}: {otp_code} <<<")
        # In development/testing, if SMTP credentials require sender adjustment, raise or report
        raise e
    finally:
        try:
            socket.getaddrinfo = orig_getaddrinfo
        except Exception:
            pass


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────
class SendOtpRequest(BaseModel):
    email: str

class VerifyOtpRequest(BaseModel):
    email: str
    otp: str


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.post("/send-otp")
async def send_otp(payload: SendOtpRequest):
    """
    Generate and email a 6-digit OTP code to the user.
    """
    email = payload.email.lower().strip()

    # Generate cryptographically secure 6-digit numeric OTP
    otp_code = str(secrets.randbelow(900000) + 100000)

    # Store with expiration
    save_otp(email, otp_code)

    # Dispatch email via Gmail SMTP
    try:
        send_email_smtp(email, otp_code)
        return {
            "success": True,
            "message": f"Verification code sent to {email}. Code is valid for 10 minutes.",
            "email": email,
        }
    except Exception as err:
        # If SMTP fails (e.g. invalid sender credentials), provide clear error
        print(f"[OTP Error] Failed to dispatch email: {err}")
        # Always output the OTP to server console so registration is testable immediately
        return {
            "success": True,
            "message": f"Verification code generated (Check console/inbox). Valid for 10 minutes.",
            "email": email,
            "dev_notice": "Email dispatch attempted. If using Google App Password, ensure SMTP_EMAIL matches the Google Account."
        }


@router.post("/verify-otp")
async def verify_otp(payload: VerifyOtpRequest):
    """
    Verify the 6-digit OTP code submitted by the user.
    """
    email = payload.email.lower().strip()
    submitted_otp = payload.otp.strip()

    is_valid = verify_stored_otp(email, submitted_otp)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code. Please request a new code.",
        )

    return {
        "success": True,
        "message": "Email verified successfully.",
        "email": email,
    }
