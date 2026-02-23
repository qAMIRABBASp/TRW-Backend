from django.utils.translation import gettext as _
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class PingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # یه متن ساده که بعداً می‌تونی براش ترجمه بذاری
        return Response({"message": _("OK")})