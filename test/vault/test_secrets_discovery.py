from pathlib import Path

import pytest

from gofr_common.vault.secrets_discovery import (
    discover_vault_bootstrap_artifacts,
    read_vault_root_token,
    read_vault_unseal_key,
    require_vault_bootstrap_artifacts,
)


def _write_artifacts(secrets_dir: Path) -> None:
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "vault_root_token").write_text("root-token\n", encoding="utf-8")
    (secrets_dir / "vault_unseal_key").write_text("unseal-key\n", encoding="utf-8")


def test_discover_prefers_env_override(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()

    project_secrets = project_root / "secrets"
    override_secrets = tmp_path / "override"

    _write_artifacts(project_secrets)
    _write_artifacts(override_secrets)

    artifacts = discover_vault_bootstrap_artifacts(
        project_root=project_root,
        env={"GOFR_SHARED_SECRETS_DIR": str(override_secrets)},
    )

    assert artifacts is not None
    assert artifacts.secrets_dir == override_secrets
    assert read_vault_root_token(artifacts) == "root-token"
    assert read_vault_unseal_key(artifacts) == "unseal-key"


def test_require_raises_when_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()

    with pytest.raises(FileNotFoundError):
        require_vault_bootstrap_artifacts(project_root=project_root, env={})
