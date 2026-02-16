from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework import status, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from .models import OTP
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    LoginSerializer,
    LogoutSerializer,
    OTPVerifySerializer,
    OTPResendSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    TwoFAToggleSerializer,
    get_tokens_for_user,
    create_and_send_otp,
    validate_otp_instance,
)
from .services import verify_google_token

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # ✅ بهتره قبل از save بخونی (چون ممکنه تو create() pop بشه)
        require_otp = serializer.validated_data.get("require_otp", True)

        user = serializer.save()

        # اگر خواستی 2FA همیشه مجبور کنه:
        # require_otp = require_otp or user.is_2fa_enabled

        if require_otp:
            try:
                otp = create_and_send_otp(user, OTP.PURPOSE_REGISTER)
            except serializers.ValidationError as e:
                # e.detail ممکنه str یا dict باشه
                return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

            return Response(
                {
                    "needs_verification": True,
                    "otp_id": str(otp.id),
                    "user": UserSerializer(user).data,
                },
                status=status.HTTP_201_CREATED,
            )

        tokens = get_tokens_for_user(user)
        return Response(
            {
                "needs_verification": False,
                "user": UserSerializer(user).data,
                "tokens": tokens,
            },
            status=status.HTTP_200_OK,
        )


class GoogleLoginView(APIView):
    
    permission_classes = [AllowAny]

    @extend_schema(responses=UserSerializer)
    def post(self, request):
        token = request.data.get("token")
        google_user_data = verify_google_token(token)
        print("GOOGLE TOKEN EXISTS?", bool(token))
        print("GOOGLE TOKEN HEAD:", token[:30] if token else None)

        if not google_user_data:
            return Response({"error": "توکن گوگل نامعتبر است"}, status=status.HTTP_400_BAD_REQUEST)

        email = google_user_data.get("email")
        if not email:
            return Response({"error": "ایمیل از گوگل دریافت نشد"}, status=status.HTTP_400_BAD_REQUEST)

        user, created = User.objects.get_or_create(email=email)
        if created:
            user.auth_provider = "google"
            user.save(update_fields=["auth_provider"])

        tokens = get_tokens_for_user(user)
        return Response(
            {"user": UserSerializer(user).data, "tokens": tokens},
            status=status.HTTP_200_OK,
        )




class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={200: UserSerializer},
        description="ورود با استفاده از ایمیل یا شماره موبایل",
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier = serializer.validated_data["identifier"]
        password = serializer.validated_data["password"]
        

        user = User.objects.filter(Q(email=identifier) | Q(phone_number=identifier)).first()
        if not user:
            return Response({"error": "نام کاربری یا رمز عبور اشتباه است"}, status=status.HTTP_401_UNAUTHORIZED)

# 2) اگر اکانت لاک است
        if user.is_locked():
            return Response(
                {"error": "حساب شما به دلیل تلاش‌های ناموفق قفل شده است. لطفاً بعداً تلاش کنید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if getattr(user, "lock_until", None) and user.lock_until and user.lock_until > timezone.now():
            remaining = int((user.lock_until - timezone.now()).total_seconds())
            return Response(
                {"error": "اکانت موقتاً قفل شده", "retry_after_seconds": remaining},
                status=status.HTTP_403_FORBIDDEN,
            )

# 3) اگر پسورد غلط است
        if not user.check_password(password):
            user.register_failed_attempt()
            return Response({"error": "نام کاربری یا رمز عبور اشتباه است"}, status=status.HTTP_401_UNAUTHORIZED)

# 4) موفق: ریست شمارنده
        user.reset_login_attempts()

# 5) اگر 2FA روشن است → OTP بده
        if user.is_2fa_enabled:
            otp = create_and_send_otp(user, OTP.PURPOSE_LOGIN)
            return Response(
                {"needs_verification": True, "otp_id": str(otp.id), "user": UserSerializer(user).data},
                status=status.HTTP_200_OK,
            )

# 6) اگر 2FA خاموش است → توکن بده
        tokens = get_tokens_for_user(user)
        return Response(
            {
                "needs_verification": False,
                "message": "لاگین موفقیت‌آمیز بود",
                "user": UserSerializer(user).data,
                "tokens": tokens,
            },
            status=status.HTTP_200_OK,
        )

class VerifyOTPView(APIView):
    """Verify OTP and issue JWT tokens (used for login/register/reset)"""

    permission_classes = [AllowAny]

    @extend_schema(request=OTPVerifySerializer)
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp_id = serializer.validated_data["otp_id"]
        code = serializer.validated_data["code"]

        try:
            otp = OTP.objects.select_related("user").get(id=otp_id)
        except OTP.DoesNotExist:
            return Response({"error": "کد یافت نشد"}, status=status.HTTP_404_NOT_FOUND)

        try:
            validate_otp_instance(otp, code)
        except serializers.ValidationError as e:
            return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)

        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at"])

        tokens = get_tokens_for_user(otp.user)
        return Response(
            {
                "needs_verification": False,
                "user": UserSerializer(otp.user).data,
                "tokens": tokens,
            },
            status=status.HTTP_200_OK,
        )


class ResendOTPView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=OTPResendSerializer)
    def post(self, request):
        serializer = OTPResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp_id = serializer.validated_data["otp_id"]

        try:
            otp = OTP.objects.select_related("user").get(id=otp_id)
        except OTP.DoesNotExist:
            return Response({"error": "کد یافت نشد"}, status=status.HTTP_404_NOT_FOUND)

        # create_and_send_otp خودش cooldown / rate limit رو اعمال می‌کنه
        try:
            new_otp = create_and_send_otp(otp.user, otp.purpose)
        except serializers.ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        return Response({"otp_id": str(new_otp.id)}, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetRequestSerializer)
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]

        user = User.objects.filter(Q(email=identifier) | Q(phone_number=identifier)).first()
        if not user:
            # ✅ لو نده کاربر هست یا نه
            return Response({"ok": True}, status=status.HTTP_200_OK)

        try:
            otp = create_and_send_otp(user, OTP.PURPOSE_RESET)
        except serializers.ValidationError:
            # ✅ لو نده rate limit خوردی یا نه
            return Response({"ok": True}, status=status.HTTP_200_OK)

        return Response({"ok": True, "otp_id": str(otp.id)}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetConfirmSerializer)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp_id = serializer.validated_data["otp_id"]
        code = serializer.validated_data["code"]
        new_password = serializer.validated_data["new_password"]

        try:
            otp = OTP.objects.select_related("user").get(id=otp_id, purpose=OTP.PURPOSE_RESET)
        except OTP.DoesNotExist:
            return Response({"error": "کد یافت نشد"}, status=status.HTTP_404_NOT_FOUND)

        try:
            validate_otp_instance(otp, code)
        except serializers.ValidationError as e:
            return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)

        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at"])

        user = otp.user
        user.set_password(new_password)
        user.save(update_fields=["password"])

        return Response({"ok": True}, status=status.HTTP_200_OK)


class TwoFAToggleView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=TwoFAToggleSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = TwoFAToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        request.user.is_2fa_enabled = serializer.validated_data["enabled"]
        request.user.save(update_fields=["is_2fa_enabled"])

        return Response({"user": UserSerializer(request.user).data}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LogoutSerializer)
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh = serializer.validated_data["refresh"]

        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except TokenError:
            return Response({"error": "refresh token نامعتبر یا منقضی شده است"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"ok": True, "message": "Logout انجام شد"}, status=status.HTTP_200_OK)
