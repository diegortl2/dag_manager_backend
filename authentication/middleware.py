"""
Middleware that validates Azure AD tokens on every request and populates
``request.azure_user`` with an ``AzureADUser`` instance (or ``None``).

This runs *before* DRF authentication so that non-DRF views (e.g. Django
admin health-check endpoints) also have user context available.
"""

import logging

from django.conf import settings
from django.http import JsonResponse

from .backend import AzureADAuthentication, AzureADUser

logger = logging.getLogger(__name__)

# Paths that should be accessible without authentication.
PUBLIC_PATH_PREFIXES = (
    "/admin/",
    "/api/auth/health/",
)


class AzureADTokenMiddleware:
    """
    Extracts and validates the Azure AD bearer token from every request.
    Sets ``request.azure_user`` to an ``AzureADUser`` or ``None``.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.auth_backend = AzureADAuthentication()

    def __call__(self, request):
        request.azure_user = None

        # Skip authentication for public paths
        if self._is_public_path(request.path):
            return self.get_response(request)

        # Skip if Azure AD is not configured (development convenience)
        if not settings.AZURE_AD_TENANT_ID:
            return self.get_response(request)

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header:
            try:
                result = self.auth_backend.authenticate(request)
                if result is not None:
                    user, _ = result
                    request.azure_user = user
            except Exception as exc:
                logger.debug("Token validation failed in middleware: %s", exc)
                # Don't block the request here — let DRF's permission
                # classes decide whether to deny access.

        return self.get_response(request)

    @staticmethod
    def _is_public_path(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)
