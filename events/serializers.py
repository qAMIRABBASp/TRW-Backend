from rest_framework import serializers
from .models import Event, Registration


class EventSerializer(serializers.ModelSerializer):
    remaining_capacity = serializers.IntegerField(read_only=True)

    # ✅ فیلدهای قیمت/تخفیف (از property های مدل)
    original_price_eur = serializers.IntegerField(read_only=True)
    discount_price_eur = serializers.IntegerField(read_only=True)
    current_price_eur = serializers.IntegerField(read_only=True)
    is_discount_active = serializers.BooleanField(read_only=True)

    # ✅ برای تایمر (ISO string)
    discount_end = serializers.SerializerMethodField()

    def get_discount_end(self, obj):
        # discount_end_dt property از مدل میاد
        return obj.discount_end_dt.isoformat()

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "start_datetime",
            "capacity",
            "reserved_count",
            "remaining_capacity",

            # فیلد قبلی (اگر فرانت قدیمی بهش وابسته است نگه می‌داریم)
            "price",

            # ✅ فیلدهای جدید برای UI پرداخت/تخفیف
            "original_price_eur",
            "discount_price_eur",
            "current_price_eur",
            "is_discount_active",
            "discount_end",

            "is_active",
        ]


class RegistrationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Registration
        fields = ["first_name", "last_name", "phone", "email"]


class RegistrationSerializer(serializers.ModelSerializer):
    event = EventSerializer(read_only=True)

    class Meta:
        model = Registration
        fields = [
            "id",
            "event",
            "first_name",
            "last_name",
            "phone",
            "email",
            "status",
            "amount",
            "gateway_name",
            "payment_authority",
            "payment_ref_id",
            "created_at",
        ]