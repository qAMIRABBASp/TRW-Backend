from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone


from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from .models import OTP
from .services import generate_otp_code, hash_otp, verify_otp, otp_expiry, send_otp

User = get_user_model()

# تنظیمات امنیتی
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone_number",
            "first_name",
            "last_name",
            "date_of_birth",
            "is_2fa_enabled",
        ]


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    require_otp = serializers.BooleanField(write_only=True, required=False, default=True)

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "date_of_birth",
            "password",
            "require_otp",
        )

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip().lower()
        phone = (attrs.get("phone_number") or "").strip()

        if not email:
            raise serializers.ValidationError({"email": "ایمیل اجباری است"})
        if not phone:
            raise serializers.ValidationError({"phone_number": "شماره موبایل اجباری است"})

        errors = {}
        if User.objects.filter(email__iexact=email).exists():
            errors["email"] = "این ایمیل قبلاً ثبت شده است"
        if User.objects.filter(phone_number=phone).exists():
            errors["phone_number"] = "این شماره موبایل قبلاً ثبت شده است"
        if errors:
            raise serializers.ValidationError(errors)

        attrs["email"] = email
        attrs["phone_number"] = phone
        return attrs

    def create(self, validated_data):
        validated_data.pop("require_otp", None)
        password = validated_data.pop("password")

        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save(update_fields=["password"])
        return user



class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(label="E-Mail-Adresse oder Mobilnummer", required=True)
    password = serializers.CharField(write_only=True, required=True)


class OTPVerifySerializer(serializers.Serializer):
    otp_id = serializers.UUIDField()
    code = serializers.CharField(min_length=6, max_length=6)


class OTPResendSerializer(serializers.Serializer):
    otp_id = serializers.UUIDField()


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    otp_id = serializers.UUIDField()
    code = serializers.CharField(min_length=6, max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password2 = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password2": "رمز عبور و تکرار آن یکسان نیست"})
        return attrs


# -------------------------
# Helpers for views
# -------------------------

def _enforce_otp_cooldown(user, purpose: str):
    """
    جلوگیری از اسپم کردن ارسال کد.
    اگر آخرین OTP برای این purpose کمتر از X ثانیه پیش ساخته شده باشد، اجازه نده.
    """
    last = OTP.objects.filter(user=user, purpose=purpose).order_by("-created_at").first()
    if not last:
        return

    delta = timezone.now() - last.created_at
    if delta < timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS):
        remaining = OTP_RESEND_COOLDOWN_SECONDS - int(delta.total_seconds())
        raise serializers.ValidationError(f"لطفاً {remaining} ثانیه دیگر دوباره تلاش کنید")


def create_and_send_otp(user, purpose: str) -> OTP:
    now = timezone.now()

    COOLDOWN_SECONDS = 60          # فاصله بین دو ارسال برای همان purpose
    OTP_LIFETIME_MINUTES = 3       # همونی که داری
    MAX_ACTIVE_OTPS = 3            # حداکثر OTP فعال همزمان برای هر purpose

    # 1) Cooldown: اگر کمتر از 60 ثانیه پیش OTP برای همین purpose ساخته شده، نذار دوباره بسازه
    last_otp = (
        OTP.objects.filter(user=user, purpose=purpose)
        .order_by("-created_at")
        .first()
    )
    if last_otp and (now - last_otp.created_at).total_seconds() < COOLDOWN_SECONDS:
        remaining = COOLDOWN_SECONDS - int((now - last_otp.created_at).total_seconds())
        raise serializers.ValidationError({"otp": f"لطفاً {remaining} ثانیه دیگر دوباره تلاش کنید"})

    # 2) Max active OTP: اگر OTP فعال زیاد داری، نذار بیشتر بسازه
    active_count = OTP.objects.filter(
        user=user,
        purpose=purpose,
        used_at__isnull=True,
        expires_at__gt=now,
    ).count()
    if active_count >= MAX_ACTIVE_OTPS:
        raise serializers.ValidationError({"otp": "تعداد درخواست‌های کد بیش از حد مجاز است. چند دقیقه بعد دوباره تلاش کنید"})

    # ساخت OTP
    code = generate_otp_code()
    otp = OTP.objects.create(
        user=user,
        purpose=purpose,
        code_hash=hash_otp(code),
        expires_at=otp_expiry(OTP_LIFETIME_MINUTES),
    )
    send_otp(user, code, purpose)
    return otp


def validate_otp_instance(otp: OTP, code: str) -> None:
    # اگر قبلاً استفاده شده
    if otp.is_used:
        raise serializers.ValidationError("کد قبلاً استفاده شده است")

    # اگر منقضی شده
    if otp.is_expired:
        raise serializers.ValidationError("کد منقضی شده است")

    # اگر تعداد تلاش زیاد شده (قفل)
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        raise serializers.ValidationError("تعداد تلاش بیش از حد مجاز است")

    # چک کردن کد
    if not verify_otp(code, otp.code_hash):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        raise serializers.ValidationError("کد وارد شده صحیح نیست")

class TwoFAToggleSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate_refresh(self, value):
        # فقط اینکه خالی نباشه کافیـه، اعتبارسنجی اصلی تو view انجام میشه
        if not value or not isinstance(value, str):
            raise serializers.ValidationError("refresh token نامعتبر است")
        return value
