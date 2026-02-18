from django.urls import path
from .views import EventListView, EventDetailView, EventRegisterView, PaymentCallbackView

urlpatterns = [
    path("events/", EventListView.as_view(), name="event-list"),
    path("events/<int:pk>/", EventDetailView.as_view(), name="event-detail"),
    path("events/<int:pk>/register/", EventRegisterView.as_view(), name="event-register"),
    path("payment/callback/", PaymentCallbackView.as_view(), name="payment-callback"),
]
