from rest_framework import serializers
from .models import Event, Registration


class EventSerializer(serializers.ModelSerializer):
    remaining_capacity = serializers.IntegerField(read_only=True)

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
            "price",
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
