import time

class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()

        print(f"[REQ] {request.method} {request.get_full_path()} from {request.META.get('REMOTE_ADDR')}")

        response = self.get_response(request)

        duration = int((time.time() - start) * 1000)

        print(f"[RES] {request.method} {request.get_full_path()} -> {response.status_code} ({duration}ms)")

        return response
