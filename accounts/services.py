from google.oauth2 import id_token
from google.auth.transport import requests

import random
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password

# Client ID رو اینجا کپی کن
GOOGLE_CLIENT_ID = "75191774194-5accmehcs793m5cfnn7kofp1ptskpht1.apps.googleusercontent.com"

def verify_google_token(token_id):
    try:
        id_info = id_token.verify_oauth2_token(
            token_id, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        return id_info
    except Exception as e:
        print(f"Error verifying token: {e}")
        return None


# -------------------- OTP helpers (2FA / reset password) --------------------

def generate_otp_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def hash_otp(code: str) -> str:
    return make_password(code)


def verify_otp(code: str, code_hash: str) -> bool:
    return check_password(code, code_hash)


def otp_expiry(minutes: int = 3):
    return timezone.now() + timedelta(minutes=minutes)


def send_otp(user, code: str, purpose: str):
    """
    Placeholder sender.
    Later you can connect this to sms.ir or email.
    """
    print(f"[OTP] purpose={purpose} user_id={user.id} email={user.email} phone={user.phone_number} code={code}")