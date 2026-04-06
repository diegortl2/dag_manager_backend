"""
Audit request middleware.

Captures request metadata (IP address, user agent) and makes it available
via thread-local storage so that model-level code and utility functions can
create audit log entries without needing a reference to the HTTP request.
"""

import threading

_thread_locals = threading.local()


def get_current_request_meta() -> dict:
    """
    Return the request metadata stashed by the middleware, or an empty dict
    if called outside of a request context.
    """
    return getattr(_thread_locals, "request_meta", {})


class AuditRequestMiddleware:
    """
    Stores request metadata in thread-local storage so that it can be
    accessed by audit-logging helpers anywhere in the call stack.

    Metadata stored:
        - ip_address
        - user_agent
        - user (Azure AD identifier, if available)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            ip_address = x_forwarded.split(",")[0].strip()
        else:
            ip_address = request.META.get("REMOTE_ADDR", "")

        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

        user = ""
        azure_user = getattr(request, "azure_user", None)
        if azure_user:
            user = getattr(azure_user, "email", "") or getattr(azure_user, "oid", "")

        _thread_locals.request_meta = {
            "ip_address": ip_address,
            "user_agent": user_agent,
            "user": user,
        }

        try:
            response = self.get_response(request)
        finally:
            # Clean up after the request to avoid leaking data between
            # requests when using thread pools.
            _thread_locals.request_meta = {}

        return response
