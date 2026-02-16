from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import uuid


class UserManager(BaseUserManager):
    def create_user(self, email=None, phone_number=None, password=None, **extra_fields):
        if not email or not phone_number:
            raise ValueError("ایمیل و شماره تلفن اجباری هستند")

        email = self.normalize_email(email)

        user = self.model(email=email, phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if not extra_fields.get("phone_number"):
            raise ValueError("برای ساخت سوپریوزر باید phone_number هم وارد شود")

        return self.create_user(email=email, password=password, **extra_fields)


class User(AbstractUser):
    username = None

    email = models.EmailField(unique=True)  # پیشنهاد: null/blank حذف
    phone_number = models.CharField(max_length=15, unique=True)  # پیشنهاد: null/blank حذف
    auth_provider = models.CharField(max_length=50, default="email")

    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    date_of_birth = models.DateField(null=True, blank=True)
    is_2fa_enabled = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone_number"]

    objects = UserManager()

    failed_login_attempts = models.PositiveIntegerField(default=0)
    lock_until = models.DateTimeField(null=True, blank=True)

    def is_locked(self):
        if self.lock_until and self.lock_until > timezone.now():
            return True
        return False

    def register_failed_attempt(self):
        self.failed_login_attempts += 1

        if self.failed_login_attempts >= 5:
            self.lock_until = timezone.now() + timedelta(minutes=15)
            self.failed_login_attempts = 0  # ریست بعد از لاک

        self.save(update_fields=["failed_login_attempts", "lock_until"])

    def reset_login_attempts(self):
        self.failed_login_attempts = 0
        self.lock_until = None
        self.save(update_fields=["failed_login_attempts", "lock_until"])

    def __str__(self):
        return self.email


class OTP(models.Model):
    PURPOSE_REGISTER = "REGISTER"
    PURPOSE_LOGIN = "LOGIN"
    PURPOSE_RESET = "RESET"

    PURPOSE_CHOICES = [
        (PURPOSE_REGISTER, "Register"),
        (PURPOSE_LOGIN, "Login"),
        (PURPOSE_RESET, "Reset"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps")
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)

    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)

    sent_via_email = models.BooleanField(default=False)
    sent_via_sms = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_used(self):
        return self.used_at is not None

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @staticmethod
    def default_expiry(minutes: int = 3):
        return timezone.now() + timedelta(minutes=minutes)

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
