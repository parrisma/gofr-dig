from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.logger import Logger, session_logger
from gofr_common.auth import (
    AuthService,
    DuplicateGroupError,
    GroupRegistry,
    InvalidGroupError,
    create_stores_from_env,
)


@dataclass(frozen=True)
class TokenSet:
    token_apac: str
    token_emea: str
    token_us: str
    token_multi: str
    token_invalid: str
    token_expired: str


class TokenFactory:
    """Mint and manage JWT tokens for simulator personas.

    Uses the same Vault-backed stores as the service under test.

    Notes:
    - The JWT signing secret is loaded by AuthService via GOFR_JWT_SECRET.
    - Group names are expected to exist; this factory can create them if missing.
    """

    def __init__(
        self,
        *,
        env_prefix: str = "GOFR_DIG",
        logger: Logger | None = None,
        audience: str | None = "gofr-api",
        ensure_groups: bool = True,
    ) -> None:
        self._env_prefix = env_prefix
        self._logger = logger or session_logger

        # Align default Vault path prefix with gofr-dig service defaults.
        # If this is not set, gofr-common defaults to "gofr/dig/auth" for GOFR_DIG,
        # while the service uses "gofr/auth" unless overridden.
        import os

        os.environ.setdefault(f"{env_prefix}_VAULT_PATH_PREFIX", "gofr/auth")

        token_store, group_store = create_stores_from_env(env_prefix, logger=self._logger)
        group_registry = GroupRegistry(store=group_store)
        self._auth = AuthService(
            token_store=token_store,
            group_registry=group_registry,
            env_prefix=env_prefix,
            audience=audience,
            logger=self._logger,
        )

        if ensure_groups:
            self._ensure_group("apac", "Simulator group: APAC")
            self._ensure_group("emea", "Simulator group: EMEA")
            self._ensure_group("us", "Simulator group: US")

    @property
    def auth(self) -> AuthService:
        return self._auth

    def mint(self, *, groups: list[str], expires_in_seconds: int, name: str | None = None) -> str:
        return self._auth.create_token(groups=groups, expires_in_seconds=expires_in_seconds, name=name)

    def mint_required_tokens(self, *, expires_in_seconds: int = 3600) -> TokenSet:
        token_apac = self.mint(groups=["apac"], expires_in_seconds=expires_in_seconds, name="sim-apac")
        token_emea = self.mint(groups=["emea"], expires_in_seconds=expires_in_seconds, name="sim-emea")
        token_us = self.mint(groups=["us"], expires_in_seconds=expires_in_seconds, name="sim-us")

        # Multi-group token: order matters today for write-scoping (primary group = first).
        token_multi = self.mint(
            groups=["apac", "emea", "us"],
            expires_in_seconds=expires_in_seconds,
            name="sim-multi",
        )

        # Invalid token: syntactically JWT-ish but will never validate.
        token_invalid = "invalid.invalid.invalid"

        # Expired token: exp in the past.
        token_expired = self.mint(groups=["apac"], expires_in_seconds=-60, name="sim-expired")

        self._logger.info(
            "sim.tokens_minted",
            event="sim.tokens_minted",
            groups=["apac", "emea", "us"],
            multi_groups=["apac", "emea", "us"],
            expires_in_seconds=expires_in_seconds,
        )

        return TokenSet(
            token_apac=token_apac,
            token_emea=token_emea,
            token_us=token_us,
            token_multi=token_multi,
            token_invalid=token_invalid,
            token_expired=token_expired,
        )

    def _ensure_group(self, name: str, description: str) -> None:
        try:
            self._auth.groups.create_group(name, description)
            self._logger.info(
                "sim.group_created",
                event="sim.group_created",
                group=name,
            )
        except DuplicateGroupError:
            return
        except InvalidGroupError as exc:
            self._logger.error(
                "sim.group_invalid",
                event="sim.group_invalid",
                group=name,
                error=str(exc),
                recovery="Choose a group name that matches the registry naming rules",
            )
            raise


def tokens_from_env(prefix: str = "GOFR_DIG") -> Mapping[str, str]:
    """Read pre-minted tokens from environment.

    This is useful when the simulator should not mint tokens (e.g., no Vault access).

    Expected variables:
      - {PREFIX}_SIM_TOKEN_APAC
      - {PREFIX}_SIM_TOKEN_EMEA
      - {PREFIX}_SIM_TOKEN_US
      - {PREFIX}_SIM_TOKEN_MULTI

    Returns only variables that are present and non-empty.
    """
    import os

    out: dict[str, str] = {}
    for key in ("APAC", "EMEA", "US", "MULTI"):
        env_name = f"{prefix}_SIM_TOKEN_{key}"
        value = os.environ.get(env_name)
        if value and value.strip():
            out[key.lower()] = value.strip()
    return out
