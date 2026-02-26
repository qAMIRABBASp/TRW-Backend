from django.conf import settings
from django.utils.translation import gettext_lazy as _
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
        # 1) event باید وجود داشته باشه و active باشه
        try:
            event = Event.objects.get(pk=pk, is_active=True)
        except Event.DoesNotExist:
            return Response(
                {"detail": _("Event not found or inactive.")},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 2) ظرفیت باید داشته باشه
        if event.remaining_capacity <= 0:
            return Response(
                {"detail": _("Event is full.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3) validate اطلاعات کاربر
        serializer = RegistrationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 4) روش پرداخت: online | bank_transfer
        payment_method = (request.data.get("payment_method") or "online").lower().strip()
        if payment_method not in ("online", "bank_transfer"):
            payment_method = "online"

        # 5) قیمت نهایی (با/بدون تخفیف) — همین که الان در API داری
        final_amount = event.current_price_eur

        # 6) اول Registration ساخته میشه (برای هر دو روش)
        registration = Registration.objects.create(
            event=event,
            amount=final_amount,
            status=Registration.STATUS_PENDING,  # اگر مدل‌تون default داره، باز هم مشکلی نیست
            gateway_name=("bank_transfer" if payment_method == "bank_transfer" else "dummy"),
            **serializer.validated_data,
        )

        # 7) اگر بانک‌تریسفر بود، دیگه payment_url نداریم
        if payment_method == "bank_transfer":
            return Response(
                {
                    "registration_id": registration.id,
                    "payment_method": "bank_transfer",
                    "status": registration.status,
                    "pricing": {
                        "original_price_eur": event.original_price_eur,
                        "discount_price_eur": event.discount_price_eur,
                        "current_price_eur": event.current_price_eur,
                        "is_discount_active": event.is_discount_active,
                        "discount_end": event.discount_end_dt.isoformat(),
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        # 8) اگر آنلاین بود: درگاه dummy رو init کن و authority رو ذخیره کن
        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://127.0.0.1:5173")
        gateway = DummyGateway(base_url=frontend_base)

        callback_base = getattr(settings, "PAYMENT_GATEWAY", {}).get(
            "CALLBACK_BASE_URL", "http://127.0.0.1:8000"
        )
        callback_url = f"{callback_base}/api/payment/callback/"

        init_result = gateway.init_payment(amount=final_amount, callback_url=callback_url)

        registration.payment_authority = init_result.authority
        registration.gateway_name = "dummy"
        registration.save(update_fields=["payment_authority", "gateway_name", "updated_at"])

        return Response(
            {
                "payment_url": init_result.payment_url,
                "registration_id": registration.id,
                "authority": registration.payment_authority,
                "payment_method": "online",
                "pricing": {
                    "original_price_eur": event.original_price_eur,
                    "discount_price_eur": event.discount_price_eur,
                    "current_price_eur": event.current_price_eur,
                    "is_discount_active": event.is_discount_active,
                    "discount_end": event.discount_end_dt.isoformat(),
                },
            },
            status=status.HTTP_201_CREATED,
        )



class ConfirmBankTransferView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        try:
            registration = Registration.objects.select_related("event").get(pk=pk)
        except Registration.DoesNotExist:
            return Response(
                {"detail": _("Registration not found.")},
                status=status.HTTP_404_NOT_FOUND,
            )

        # اگر قبلاً پرداخت شده
        if registration.status == Registration.STATUS_PAID:
            return Response(
                {"detail": _("Registration already paid.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ثبت انتخاب بانک‌تریسفر
        registration.gateway_name = "bank_transfer"
        registration.save(update_fields=["gateway_name", "updated_at"])

        return Response(
            {
                "ok": True,
                "registration_id": registration.id,
                "status": registration.status,
                "gateway_name": registration.gateway_name,
            },
            status=status.HTTP_200_OK,
        )



class PaymentCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        authority = request.query_params.get("authority") or request.query_params.get("Authority")
        if not authority:
            return Response({"detail": _("Missing authority.")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            registration = Registration.objects.select_related("event").get(payment_authority=authority)
        except Registration.DoesNotExist:
            return Response({"detail": _("Registration not found.")}, status=status.HTTP_404_NOT_FOUND)

        if registration.status == Registration.STATUS_PAID:
            data = RegistrationSerializer(registration).data
            return Response({"detail": _("Payment already verified."), "status": "ok", "registration": data})

        gateway = DummyGateway()
        verify_result = gateway.verify_payment(authority=authority)

        if not verify_result.success:
            registration.status = Registration.STATUS_FAILED
            registration.save(update_fields=["status", "updated_at"])
            return Response({"detail": _("Payment verification failed."), "status": "failed"}, status=400)

        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=registration.event.pk)
            if event.remaining_capacity <= 0:
                registration.status = Registration.STATUS_FAILED
                registration.save(update_fields=["status", "updated_at"])
                return Response({"detail": _("Event is full."), "status": "failed"}, status=400)

            event.reserved_count += 1
            event.save(update_fields=["reserved_count", "updated_at"])

            registration.status = Registration.STATUS_PAID
            registration.payment_ref_id = verify_result.ref_id or ""
            registration.save(update_fields=["status", "payment_ref_id", "updated_at"])

        data = RegistrationSerializer(registration).data
        return Response({"detail": _("Payment successful."), "status": "ok", "registration": data})