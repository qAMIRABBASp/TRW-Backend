from django.db import models
from django.utils import timezone
from datetime import datetime


class Event(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_datetime = models.DateTimeField()
    capacity = models.PositiveIntegerField()
    reserved_count = models.PositiveIntegerField(default=0)
    price = models.PositiveIntegerField(help_text="Price in smallest currency unit")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # (این فیلدها رو گذاشتی—می‌مونن، ولی فعلاً برای منطق ما لازم نیستند)
    original_price = models.PositiveIntegerField(default=89)
    discount_price = models.PositiveIntegerField(null=True, blank=True)
    discount_start = models.DateTimeField(null=True, blank=True)
    discount_end = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["start_datetime"]

    def __str__(self):
        return self.title

    @property
    def remaining_capacity(self):
        return max(self.capacity - self.reserved_count, 0)

    # =========================
    #  Discount (fixed dates)
    #  89€ -> 50€
    #  Feb 22, 2026 -> Feb 28, 2026
    # =========================

    @property
    def original_price_eur(self):
        return 89

    @property
    def discount_price_eur(self):
        return 50

    @property
    def discount_start_dt(self):
        return timezone.make_aware(datetime(2026, 2, 22, 0, 0, 0))

    @property
    def discount_end_dt(self):
        return timezone.make_aware(datetime(2026, 2, 28, 23, 59, 59))

    @property
    def is_discount_active(self):
        now = timezone.now()
        return self.discount_start_dt <= now <= self.discount_end_dt

    @property
    def current_price_eur(self):
        return self.discount_price_eur if self.is_discount_active else self.original_price_eur


class Registration(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELED, "Canceled"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    amount = models.PositiveIntegerField()
    gateway_name = models.CharField(max_length=50, blank=True)
    payment_authority = models.CharField(max_length=255, blank=True)
    payment_ref_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.event.title}"