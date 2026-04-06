"""
Azure AD JWT token validation authentication backend for Django REST Framework.

Validates JWT bearer tokens from the Authorization header against Azure AD's
JWKS endpoint. Extracts user info (oid, email, name, roles) from token claims.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import jwt
import requests
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


@dataclass
class AzureADUser:
    """
    Lightweight user object holding Azure AD claims.
    Not tied to Django's auth User model.
    """

    oid: str
    email: str
    name: str
    roles: list[str] = field(default_factory=list)
    raw_claims: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def pk(self) -> str:
        return self.oid

    def __str__(self) -> str:
        return self.email or self.oid


class JWKSKeyCache:
    """
    Thread-safe cache for Azure AD JWKS signing keys.
    Keys are refreshed when they expire or when a key-id miss occurs.
    """

    DEFAULT_TTL_SECONDS = 3600  # 1 hour

    def __init__(self, tenant_id: str, ttl: int = DEFAULT_TTL_SECONDS):
        self._tenant_id = tenant_id
        self._ttl = ttl
        self._keys: dict[str, dict] = {}
        self._last_refresh: float = 0.0
        self._lock = threading.Lock()

    @property
    def _jwks_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self._tenant_id}"
            f"/discovery/v2.0/keys"
        )

    def _needs_refresh(self) -> bool:
        return time.time() - self._last_refresh > self._ttl

    def _fetch_keys(self) -> None:
        """Fetch JWKS keys from Azure AD and populate the cache."""
        try:
            response = requests.get(self._jwks_url, timeout=10)
            response.raise_for_status()
            jwks_data = response.json()
        except requests.RequestException as exc:
            logger.error("Failed to fetch JWKS keys from Azure AD: %s", exc)
            raise AuthenticationFailed(
                "Unable to validate token: could not fetch signing keys."
            ) from exc

        new_keys: dict[str, dict] = {}
        for key_data in jwks_data.get("keys", []):
            kid = key_data.get("kid")
            if kid:
                new_keys[kid] = key_data
        self._keys = new_keys
        self._last_refresh = time.time()
        logger.info("Refreshed JWKS key cache with %d keys.", len(new_keys))

    def get_key(self, kid: str) -> dict:
        """
        Retrieve the signing key for a given key-id.
        Refreshes the cache if expired or if the key-id is not found.
        """
        with self._lock:
            if self._needs_refresh() or kid not in self._keys:
                self._fetch_keys()
            key_data = self._keys.get(kid)
            if not key_data:
                raise AuthenticationFailed(
                    f"Signing key '{kid}' not found in Azure AD JWKS."
                )
            return key_data


# Module-level singleton — lazily initialised on first use.
_jwks_cache: Optional[JWKSKeyCache] = None
_cache_init_lock = threading.Lock()


def _get_jwks_cache() -> JWKSKeyCache:
    global _jwks_cache
    if _jwks_cache is None:
        with _cache_init_lock:
            if _jwks_cache is None:
                _jwks_cache = JWKSKeyCache(tenant_id=settings.AZURE_AD_TENANT_ID)
    return _jwks_cache


class AzureADAuthentication(BaseAuthentication):
    """
    DRF authentication class that validates Azure AD JWT bearer tokens.
    Returns an (AzureADUser, token) tuple on success.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header:
            return None  # No credentials — let other auth backends try

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != self.keyword.lower():
            return None

        raw_token = parts[1]
        user = self._validate_token(raw_token)
        return (user, raw_token)

    def authenticate_header(self, request):
        return self.keyword

    # ------------------------------------------------------------------
    # Token validation
    # ------------------------------------------------------------------

    def _validate_token(self, raw_token: str) -> AzureADUser:
        """Decode and validate the JWT, returning an AzureADUser."""

        # 1. Read unverified header to determine which signing key to use.
        try:
            unverified_header = jwt.get_unverified_header(raw_token)
        except jwt.DecodeError as exc:
            raise AuthenticationFailed("Invalid token header.") from exc

        kid = unverified_header.get("kid")
        if not kid:
            raise AuthenticationFailed("Token header missing 'kid'.")

        # 2. Fetch the matching public key from Azure AD JWKS.
        cache = _get_jwks_cache()
        key_data = cache.get_key(kid)

        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        except Exception as exc:
            raise AuthenticationFailed("Failed to construct public key.") from exc

        # 3. Decode and verify the token.
        tenant_id = settings.AZURE_AD_TENANT_ID
        client_id = settings.AZURE_AD_CLIENT_ID
        audience = settings.AZURE_AD_AUDIENCE or client_id
        issuer = f"https://sts.windows.net/{tenant_id}/"
        issuer_v2 = f"https://login.microsoftonline.com/{tenant_id}/v2.0"

        try:
            claims = jwt.decode(
                raw_token,
                key=public_key,
                algorithms=["RS256"],
                audience=audience,
                issuer=[issuer, issuer_v2],
                options={
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationFailed("Token has expired.") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationFailed("Invalid token audience.") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationFailed("Invalid token issuer.") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationFailed(f"Invalid token: {exc}") from exc

        # 4. Build user object from claims.
        return AzureADUser(
            oid=claims.get("oid", ""),
            email=claims.get("preferred_username", claims.get("email", claims.get("upn", ""))),
            name=claims.get("name", ""),
            roles=claims.get("roles", []),
            raw_claims=claims,
        )
