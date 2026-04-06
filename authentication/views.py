"""
Authentication views.

Provides a ``/api/auth/me/`` endpoint that returns the current authenticated
user's information extracted from the Azure AD token.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from dags.permissions import IsAzureADAuthenticated


class MeView(APIView):
    """Return the current user's Azure AD profile information."""

    permission_classes = [IsAzureADAuthenticated]

    def get(self, request):
        user = request.user
        if not user or not getattr(user, "is_authenticated", False):
            return Response(
                {"detail": "Not authenticated."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "oid": getattr(user, "oid", ""),
                "email": getattr(user, "email", ""),
                "name": getattr(user, "name", ""),
                "roles": getattr(user, "roles", []),
            },
            status=status.HTTP_200_OK,
        )


class HealthView(APIView):
    """Unauthenticated health-check endpoint."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)
