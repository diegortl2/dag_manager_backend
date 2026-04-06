"""
Custom DRF permission classes for DAG management.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.backend import AzureADUser


class IsAzureADAuthenticated(BasePermission):
    """
    Grants access only if the request was authenticated via Azure AD and
    ``request.user`` is a valid ``AzureADUser`` instance.
    """

    message = "Authentication via Azure AD is required."

    def has_permission(self, request, view):
        user = request.user
        if isinstance(user, AzureADUser) and user.is_authenticated:
            return True
        return False


class IsOwnerOrReadOnly(BasePermission):
    """
    Allows read-only access to any authenticated user.
    Write operations (create, update, delete) are restricted to the DAG owner
    or to users whose email matches the ``created_by`` field.

    Falls back to allow if no owner is set on the object.
    """

    message = "Only the DAG owner may modify this resource."

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any authenticated request.
        if request.method in SAFE_METHODS:
            return True

        user = request.user
        if not isinstance(user, AzureADUser):
            return False

        user_email = user.email

        # If the object has no owner, allow modification.
        obj_owner = getattr(obj, "owner", None)
        obj_created_by = getattr(obj, "created_by", None)

        if not obj_owner and not obj_created_by:
            return True

        # Allow if the user is the owner or the original creator.
        if obj_owner and obj_owner == user_email:
            return True
        if obj_created_by and obj_created_by == user_email:
            return True

        return False
