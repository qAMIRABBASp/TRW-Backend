import random
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.conf import settings


def generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def hash_code(code: str) -> str:
    return make_password(code)


def verify_code(code: str, code_hash: str) -> bool:
    return check_password(code, code_hash)


def send_otp_email(to_email: str, code: str, purpose: str):
    subject = "Your verification code"
    if purpose == "REGISTER":
        subject = "Verify your registration"
    elif purpose == "RESET":
        subject = "Reset your password"

    body = f"Your code is: {code}\nThis code will expire soon."

    # اگر EMAIL_BACKEND درست تنظیم نشده باشه، اینجا ارور میده؛
    # برای dev می‌تونی از console backend استفاده کنی (پایین توضیح دادم).
    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        fail_silently=False,
    )
