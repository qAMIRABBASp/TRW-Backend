from django.utils import translation

SUPPORTED = {"fa", "en", "de"}

class APILanguageMiddleware:
    """
    زبان را از هدر درخواست می‌گیرد و برای همان request فعال می‌کند.
    اولویت:
      1) X-Language (اختیاری)
      2) Accept-Language (استاندارد)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = request.headers.get("X-Language")

        if not lang:
            accept = request.headers.get("Accept-Language", "")
            lang = (accept.split(",")[0].strip() if accept else "")[:2]  # de-DE -> de

        if lang not in SUPPORTED:
            lang = "en"

        translation.activate(lang)
        request.LANGUAGE_CODE = lang

        response = self.get_response(request)
        response["Content-Language"] = lang

        translation.deactivate()
        return response