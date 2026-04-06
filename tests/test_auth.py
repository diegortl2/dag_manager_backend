"""Unit tests for Azure AD authentication backend and views."""

from unittest.mock import MagicMock, patch

import jwt
import pytest
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from authentication.backend import AzureADAuthentication, AzureADUser, JWKSKeyCache


class TestAzureADUser:
    def test_is_authenticated(self, azure_user):
        assert azure_user.is_authenticated is True

    def test_pk_is_oid(self, azure_user):
        assert azure_user.pk == "test-oid-123"

    def test_str_returns_email(self, azure_user):
        assert str(azure_user) == "test@example.com"

    def test_str_falls_back_to_oid(self):
        user = AzureADUser(oid="oid-only", email="", name="")
        assert str(user) == "oid-only"

    def test_roles_default(self):
        user = AzureADUser(oid="x", email="x@test.com", name="X")
        assert user.roles == []


class TestAzureADAuthentication:
    def test_returns_none_when_no_auth_header(self):
        factory = APIRequestFactory()
        request = factory.get("/api/dags/")
        auth = AzureADAuthentication()
        result = auth.authenticate(request)
        assert result is None

    def test_returns_none_for_non_bearer(self):
        factory = APIRequestFactory()
        request = factory.get("/api/dags/", HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz")
        auth = AzureADAuthentication()
        result = auth.authenticate(request)
        assert result is None

    def test_returns_none_for_malformed_header(self):
        factory = APIRequestFactory()
        request = factory.get("/api/dags/", HTTP_AUTHORIZATION="Bearer")
        auth = AzureADAuthentication()
        result = auth.authenticate(request)
        assert result is None

    @patch("authentication.backend._get_jwks_cache")
    @patch("authentication.backend.jwt.decode")
    @patch("authentication.backend.jwt.get_unverified_header")
    @patch("authentication.backend.jwt.algorithms.RSAAlgorithm.from_jwk")
    def test_valid_token(self, mock_from_jwk, mock_header, mock_decode, mock_cache):
        mock_header.return_value = {"kid": "test-kid", "alg": "RS256"}
        mock_cache.return_value = MagicMock()
        mock_cache.return_value.get_key.return_value = {"kid": "test-kid", "kty": "RSA"}
        mock_from_jwk.return_value = MagicMock()
        mock_decode.return_value = {
            "oid": "user-oid",
            "preferred_username": "user@test.com",
            "name": "Test User",
            "roles": ["admin"],
        }

        factory = APIRequestFactory()
        request = factory.get(
            "/api/dags/", HTTP_AUTHORIZATION="Bearer valid-token-here"
        )
        auth = AzureADAuthentication()
        user, token = auth.authenticate(request)

        assert isinstance(user, AzureADUser)
        assert user.oid == "user-oid"
        assert user.email == "user@test.com"
        assert user.name == "Test User"
        assert user.roles == ["admin"]
        assert token == "valid-token-here"

    @patch("authentication.backend._get_jwks_cache")
    @patch("authentication.backend.jwt.get_unverified_header")
    @patch("authentication.backend.jwt.algorithms.RSAAlgorithm.from_jwk")
    @patch("authentication.backend.jwt.decode")
    def test_expired_token_raises(self, mock_decode, mock_from_jwk, mock_header, mock_cache):
        mock_header.return_value = {"kid": "test-kid"}
        mock_cache.return_value = MagicMock()
        mock_cache.return_value.get_key.return_value = {"kid": "test-kid"}
        mock_from_jwk.return_value = MagicMock()
        mock_decode.side_effect = jwt.ExpiredSignatureError("Token expired")

        factory = APIRequestFactory()
        request = factory.get(
            "/api/dags/", HTTP_AUTHORIZATION="Bearer expired-token"
        )
        auth = AzureADAuthentication()
        with pytest.raises(AuthenticationFailed, match="expired"):
            auth.authenticate(request)

    def test_authenticate_header_returns_bearer(self):
        auth = AzureADAuthentication()
        assert auth.authenticate_header(None) == "Bearer"


class TestJWKSKeyCache:
    @patch("authentication.backend.requests.get")
    def test_fetches_and_caches_keys(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "keys": [
                {"kid": "key1", "kty": "RSA"},
                {"kid": "key2", "kty": "RSA"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        cache = JWKSKeyCache(tenant_id="test-tenant")
        key = cache.get_key("key1")
        assert key["kid"] == "key1"

    @patch("authentication.backend.requests.get")
    def test_raises_for_missing_kid(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"keys": [{"kid": "other", "kty": "RSA"}]}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        cache = JWKSKeyCache(tenant_id="test-tenant")
        with pytest.raises(AuthenticationFailed, match="not found"):
            cache.get_key("missing-kid")


@pytest.mark.django_db
class TestAuthViews:
    def test_me_view_authenticated(self, authenticated_client):
        response = authenticated_client.get("/api/auth/me/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "test@example.com"
        assert response.data["name"] == "Test User"
        assert response.data["oid"] == "test-oid-123"

    def test_me_view_unauthenticated(self, api_client):
        response = api_client.get("/api/auth/me/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_health_view(self, api_client):
        response = api_client.get("/api/auth/health/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ok"
