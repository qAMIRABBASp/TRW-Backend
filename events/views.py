from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny


from .models import Event, Registration
from .serializers import EventSerializer, RegistrationCreateSerializer, RegistrationSerializer
from .gateways import DummyGateway


class EventListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = EventSerializer

    def get_queryset(self):
        now = timezone.now()
        return Event.objects.filter(is_active=True, start_datetime__gte=now).order_by("start_datetime")


class EventDetailView(generics.RetrieveAPIView):   
    permission_classes = [AllowAny]
    queryset = Event.objects.all()
    serializer_class = EventSerializer


class EventRegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request, pk):
        try:
            event = Event.objects.get(pk=pk, is_active=True)
        except Event.DoesNotExist:
            return Response({"detail": "Event not found or inactive."}, status=status.HTTP_404_NOT_FOUND)

        if event.remaining_capacity <= 0:
            return Response({"detail": "Event is full."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RegistrationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://127.0.0.1:5173")
        gateway = DummyGateway(base_url=frontend_base)

        callback_base = getattr(settings, "PAYMENT_GATEWAY", {}).get(
            "CALLBACK_BASE_URL", "http://127.0.0.1:8000"
        )
        callback_url = f"{callback_base}/api/payment/callback/"

        init_result = gateway.init_payment(amount=event.price, callback_url=callback_url)

        registration = Registration.objects.create(
            event=event,
            amount=event.price,
            gateway_name="dummy",
            payment_authority=init_result.authority,
            **serializer.validated_data,
        )

        return Response(
            {
                "payment_url": init_result.payment_url,
                "registration_id": registration.id,
                "authority": registration.payment_authority,
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentCallbackView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        authority = request.query_params.get("authority") or request.query_params.get("Authority")
        if not authority:
            return Response({"detail": "Missing authority."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            registration = Registration.objects.select_related("event").get(payment_authority=authority)
        except Registration.DoesNotExist:
            return Response({"detail": "Registration not found."}, status=status.HTTP_404_NOT_FOUND)

        if registration.status == Registration.STATUS_PAID:
            data = RegistrationSerializer(registration).data
            return Response({"detail": "Payment already verified.", "status": "ok", "registration": data})

        gateway = DummyGateway()
        verify_result = gateway.verify_payment(authority=authority)

        if not verify_result.success:
            registration.status = Registration.STATUS_FAILED
            registration.save(update_fields=["status", "updated_at"])
            return Response({"detail": "Payment verification failed.", "status": "failed"}, status=400)

        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=registration.event.pk)
            if event.remaining_capacity <= 0:
                registration.status = Registration.STATUS_FAILED
                registration.save(update_fields=["status", "updated_at"])
                return Response({"detail": "Event is full.", "status": "failed"}, status=400)

            event.reserved_count += 1
            event.save(update_fields=["reserved_count", "updated_at"])

            registration.status = Registration.STATUS_PAID
            registration.payment_ref_id = verify_result.ref_id or ""
            registration.save(update_fields=["status", "payment_ref_id", "updated_at"])

        data = RegistrationSerializer(registration).data
        return Response({"detail": "Payment successful.", "status": "ok", "registration": data})
