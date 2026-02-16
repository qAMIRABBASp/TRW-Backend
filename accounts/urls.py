from django.urls import path
from .views import (
    RegisterView,
    GoogleLoginView,
    LoginView,
    VerifyOTPView,
    ResendOTPView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    TwoFAToggleView,
    LogoutView,
    
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('google/', GoogleLoginView.as_view(), name='google-login'),
    path('login/', LoginView.as_view(), name='login'),
    path('verify/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend/', ResendOTPView.as_view(), name='resend-otp'),
    path('password/reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path("2fa/toggle/", TwoFAToggleView.as_view(), name="2fa-toggle"),
    path("logout/", LogoutView.as_view(), name="accounts_logout"),
    

]