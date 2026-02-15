#!/usr/bin/env python3
"""Provision Vault AppRole for gofr-dig services.

Creates the AppRole, attaches policies, and generates service credentials
that are mounted into containers at /run/secrets/vault_creds.

Prerequisites:
  - Vault is running and unsealed (gofr-vault container on gofr-net)
  - Vault root token available at secrets/vault_root_token
  - gofr-dig-policy exists in Vault (run bootstrap_auth.py first)

Usage:
    # From gofr-dig project root
    source <(./lib/gofr-common/scripts/auth_env.sh --docker)
    uv run scripts/setup_approle.py

    # Or with explicit env
    GOFR_VAULT_URL=http://gofr-vault:$GOFR_VAULT_PORT GOFR_VAULT_TOKEN=<root-token> \
        uv run scripts/setup_approle.py

Environment Variables:
    GOFR_VAULT_URL      Vault URL (built from GOFR_VAULT_PORT if not set)
    GOFR_VAULT_PORT     Vault port (from gofr_ports.env; used to build default URL)
    GOFR_VAULT_TOKEN    Vault root token (or reads from secrets/vault_root_token)
    VAULT_ADDR           Fallback for Vault URL
    VAULT_TOKEN          Fallback for Vault token
"""

import json
import os
import sys
from pathlib import Path

# Project layout
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SECRETS_DIR = PROJECT_ROOT / "secrets"
FALLBACK_SECRETS_DIR = PROJECT_ROOT / "lib" / "gofr-common" / "secrets"
SERVICE_CREDS_DIR = SECRETS_DIR / "service_creds"

# Add gofr-common src to path
COMMON_SRC = PROJECT_ROOT / "lib" / "gofr-common" / "src"
sys.path.insert(0, str(COMMON_SRC))

from gofr_common.auth.admin import VaultAdmin  # noqa: E402
from gofr_common.auth.backends.vault_client import VaultClient  # noqa: E402
from gofr_common.auth.backends.vault_config import VaultConfig  # noqa: E402

# Services to provision (role_name → policy_names)
SERVICES = {
    "gofr-dig": ["gofr-dig-policy", "gofr-dig-logging-policy"],
    "gofr-admin-control": ["gofr-admin-control-policy"],
}


def log_info(msg: str) -> None:
    print(f"[INFO]  {msg}", file=sys.stderr)


def log_ok(msg: str) -> None:
    print(f"[OK]    {msg}", file=sys.stderr)


def log_error(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


def resolve_vault_config() -> VaultConfig:
    """Resolve Vault URL and token from env vars or secrets file."""
    vault_port = os.environ.get("GOFR_VAULT_PORT", "")
    default_url = f"http://gofr-vault:{vault_port}" if vault_port else ""
    vault_url = (
        os.environ.get("GOFR_VAULT_URL")
        or os.environ.get("VAULT_ADDR")
        or default_url
    )
    if not vault_url:
        log_error(
            "No Vault URL found. Set GOFR_VAULT_URL or GOFR_VAULT_PORT "
            "(from gofr_ports.env)."
        )
        sys.exit(1)

    vault_token = os.environ.get("GOFR_VAULT_TOKEN") or os.environ.get("VAULT_TOKEN")
    if not vault_token:
        # Try primary path, then fallback to gofr-common submodule
        token_file = SECRETS_DIR / "vault_root_token"
        fallback_token_file = FALLBACK_SECRETS_DIR / "vault_root_token"
        if token_file.exists():
            vault_token = token_file.read_text().strip()
        elif fallback_token_file.exists():
            vault_token = fallback_token_file.read_text().strip()
        else:
            log_error(
                "No Vault token found. Set GOFR_VAULT_TOKEN or bootstrap Vault:\n"
                f"  Checked: {token_file}\n"
                f"  Checked: {fallback_token_file}"
            )
            sys.exit(1)

    return VaultConfig(url=vault_url, token=vault_token)


def main() -> int:
    log_info("=== gofr-dig AppRole Provisioning ===")

    # Connect to Vault
    config = resolve_vault_config()
    log_info(f"Vault URL: {config.url}")

    client = VaultClient(config)
    admin = VaultAdmin(client)

    # Ensure AppRole auth method is enabled
    log_info("Enabling AppRole auth method (idempotent)...")
    admin.enable_approle_auth()
    log_ok("AppRole auth method enabled")

    # Install latest policies
    log_info("Installing Vault policies...")
    admin.update_policies()
    log_ok("Policies installed")

    # Provision each service
    SERVICE_CREDS_DIR.mkdir(parents=True, exist_ok=True)

    for service_name, policy_names in SERVICES.items():
        primary_policy = policy_names[0]
        extra_policies = policy_names[1:]
        policy_list = ", ".join(policy_names)
        log_info(f"Provisioning AppRole: {service_name} → [{policy_list}]")

        # Create or update the role
        admin.provision_service_role(
            service_name=service_name,
            policy_name=primary_policy,
            additional_policy_names=extra_policies,
            token_ttl="1h",
            token_max_ttl="24h",
        )
        log_ok(f"  Role '{service_name}' created/updated")

        # Generate credentials
        creds = admin.generate_service_credentials(service_name)
        log_ok(f"  Credentials generated (role_id: {creds['role_id'][:8]}...)")

        # Write to file
        creds_file = SERVICE_CREDS_DIR / f"{service_name}.json"
        creds_file.write_text(json.dumps(creds, indent=2) + "\n")
        creds_file.chmod(0o600)
        log_ok(f"  Saved to {creds_file}")

    log_info("")
    log_info("=== Provisioning Complete ===")
    log_info(f"Credentials dir: {SERVICE_CREDS_DIR}")
    log_info("")
    log_info("Next steps:")
    log_info("  1. Start gofr-dig: ./scripts/start-prod.sh")
    log_info("  2. Credentials are auto-mounted to /run/secrets/vault_creds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
