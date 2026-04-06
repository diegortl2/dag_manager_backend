"""
Azure Key Vault client for resolving connection secrets.

Uses Azure Managed Identity (via ``azure-identity``) to authenticate.
Secrets are cached in memory for a configurable TTL to avoid excessive
Key Vault API calls.
"""

import logging
import threading
import time
from typing import Optional

from azure.identity import ManagedIdentityCredential
from django.conf import settings

logger = logging.getLogger(__name__)


class KeyVaultError(Exception):
    """Raised when a Key Vault operation fails."""


class KeyVaultClient:
    """
    Client for reading secrets from Azure Key Vault.

    Authenticates using the user-assigned managed identity configured
    via ``AZURE_MANAGED_IDENTITY_CLIENT_ID``. Optionally caches secrets
    in memory to reduce API calls.
    """

    CACHE_TTL = 300  # 5 minutes

    _cache: dict[str, tuple[str, float]] = {}
    _lock = threading.Lock()

    def __init__(
        self,
        vault_url: Optional[str] = None,
        managed_identity_client_id: Optional[str] = None,
    ):
        self._vault_url = (
            vault_url
            or getattr(settings, "AZURE_KEY_VAULT_URL", "")
        ).rstrip("/")
        self._mi_client_id = (
            managed_identity_client_id
            or getattr(settings, "AZURE_MANAGED_IDENTITY_CLIENT_ID", "")
        )

    def _get_client(self):
        """Lazily create the Azure SecretClient."""
        try:
            from azure.keyvault.secrets import SecretClient
        except ImportError:
            raise KeyVaultError(
                "azure-keyvault-secrets is not installed. "
                "Run: pip install azure-keyvault-secrets"
            )

        if not self._vault_url:
            raise KeyVaultError(
                "Key Vault URL is not configured. Set AZURE_KEY_VAULT_URL."
            )

        credential = ManagedIdentityCredential(
            client_id=self._mi_client_id if self._mi_client_id else None,
        )
        return SecretClient(vault_url=self._vault_url, credential=credential)

    def get_secret(self, secret_name: str, bypass_cache: bool = False) -> str:
        """
        Retrieve a secret value from Azure Key Vault.

        Results are cached in memory for ``CACHE_TTL`` seconds unless
        ``bypass_cache`` is True.
        """
        if not secret_name:
            raise KeyVaultError("Secret name cannot be empty.")

        cache_key = f"{self._vault_url}::{secret_name}"

        if not bypass_cache:
            with self._lock:
                if cache_key in self._cache:
                    value, cached_at = self._cache[cache_key]
                    if time.time() - cached_at < self.CACHE_TTL:
                        logger.debug("Key Vault cache hit for '%s'", secret_name)
                        return value

        try:
            client = self._get_client()
            secret = client.get_secret(secret_name)
            value = secret.value or ""
        except KeyVaultError:
            raise
        except Exception as exc:
            raise KeyVaultError(
                f"Failed to retrieve secret '{secret_name}' from Key Vault: {exc}"
            ) from exc

        with self._lock:
            self._cache[cache_key] = (value, time.time())

        logger.info("Resolved Key Vault secret '%s'", secret_name)
        return value

    def set_secret(self, secret_name: str, value: str) -> None:
        """
        Create or update a secret in Azure Key Vault.

        Used to write full Airflow connection URIs so that Airflow's
        Key Vault secrets backend can resolve them at runtime.
        """
        if not secret_name:
            raise KeyVaultError("Secret name cannot be empty.")

        try:
            client = self._get_client()
            client.set_secret(secret_name, value)
        except KeyVaultError:
            raise
        except Exception as exc:
            raise KeyVaultError(
                f"Failed to set secret '{secret_name}' in Key Vault: {exc}"
            ) from exc

        # Invalidate cache for this secret
        with self._lock:
            cache_key = f"{self._vault_url}::{secret_name}"
            self._cache.pop(cache_key, None)

        logger.info("Wrote Key Vault secret '%s'", secret_name)

    def clear_cache(self, secret_name: Optional[str] = None) -> None:
        """Clear cached secrets. If ``secret_name`` given, clear only that one."""
        with self._lock:
            if secret_name:
                cache_key = f"{self._vault_url}::{secret_name}"
                self._cache.pop(cache_key, None)
            else:
                self._cache.clear()
