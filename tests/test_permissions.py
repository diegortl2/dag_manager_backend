"""Unit tests for DRF permission classes."""

from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import AnonymousUser

from authentication.backend import AzureADUser
from dags.permissions import IsAzureADAuthenticated, IsOwnerOrReadOnly


class TestIsAzureADAuthenticated:
    def test_allows_azure_ad_user(self, azure_user):
        request = MagicMock()
        request.user = azure_user
        perm = IsAzureADAuthenticated()
        assert perm.has_permission(request, None) is True

    def test_denies_anonymous_user(self):
        request = MagicMock()
        request.user = AnonymousUser()
        perm = IsAzureADAuthenticated()
        assert perm.has_permission(request, None) is False

    def test_denies_none_user(self):
        request = MagicMock()
        request.user = None
        perm = IsAzureADAuthenticated()
        assert perm.has_permission(request, None) is False

    def test_denies_non_azure_user(self):
        request = MagicMock()
        request.user = MagicMock(spec=[])  # No AzureADUser attributes
        perm = IsAzureADAuthenticated()
        assert perm.has_permission(request, None) is False


class TestIsOwnerOrReadOnly:
    def test_allows_get_for_any_authenticated_user(self, azure_user, other_azure_user):
        request = MagicMock()
        request.method = "GET"
        request.user = other_azure_user
        obj = MagicMock()
        obj.owner = azure_user.email
        obj.created_by = azure_user.email

        perm = IsOwnerOrReadOnly()
        assert perm.has_object_permission(request, None, obj) is True

    def test_allows_head_for_any_authenticated_user(self, other_azure_user):
        request = MagicMock()
        request.method = "HEAD"
        request.user = other_azure_user
        obj = MagicMock()
        obj.owner = "someone@test.com"

        perm = IsOwnerOrReadOnly()
        assert perm.has_object_permission(request, None, obj) is True

    def test_allows_put_for_owner(self, azure_user):
        request = MagicMock()
        request.method = "PUT"
        request.user = azure_user
        obj = MagicMock()
        obj.owner = azure_user.email
        obj.created_by = azure_user.email

        perm = IsOwnerOrReadOnly()
        assert perm.has_object_permission(request, None, obj) is True

    def test_denies_put_for_non_owner(self, other_azure_user, azure_user):
        request = MagicMock()
        request.method = "PUT"
        request.user = other_azure_user
        obj = MagicMock()
        obj.owner = azure_user.email
        obj.created_by = azure_user.email

        perm = IsOwnerOrReadOnly()
        assert perm.has_object_permission(request, None, obj) is False

    def test_allows_delete_for_creator(self, azure_user):
        request = MagicMock()
        request.method = "DELETE"
        request.user = azure_user
        obj = MagicMock()
        obj.owner = ""
        obj.created_by = azure_user.email

        perm = IsOwnerOrReadOnly()
        assert perm.has_object_permission(request, None, obj) is True

    def test_denies_delete_for_non_owner(self, other_azure_user, azure_user):
        request = MagicMock()
        request.method = "DELETE"
        request.user = other_azure_user
        obj = MagicMock()
        obj.owner = azure_user.email
        obj.created_by = azure_user.email

        perm = IsOwnerOrReadOnly()
        assert perm.has_object_permission(request, None, obj) is False

    def test_allows_modification_when_no_owner(self, azure_user):
        request = MagicMock()
        request.method = "PUT"
        request.user = azure_user
        obj = MagicMock()
        obj.owner = ""
        obj.created_by = ""

        perm = IsOwnerOrReadOnly()
        assert perm.has_object_permission(request, None, obj) is True

    def test_denies_non_azure_user_for_write(self):
        request = MagicMock()
        request.method = "PUT"
        request.user = MagicMock(spec=[])  # Not an AzureADUser
        obj = MagicMock()
        obj.owner = "test@example.com"

        perm = IsOwnerOrReadOnly()
        assert perm.has_object_permission(request, None, obj) is False
