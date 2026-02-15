import importlib.util
import sys
from pathlib import Path


def _load_setup_approle_module(project_root: Path):
    script_path = (
        project_root
        / "lib"
        / "gofr-common"
        / "scripts"
        / "setup_approle.py"
    )
    spec = importlib.util.spec_from_file_location("gofr_common_setup_approle", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_policies_only_does_not_write_credentials(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()

    # Minimal layout expected by the script
    (project_root / "config").mkdir()
    (project_root / "secrets").mkdir()
    (project_root / "lib" / "gofr-common" / "config").mkdir(parents=True)

    (project_root / "lib" / "gofr-common" / "config" / "gofr_ports.env").write_text(
        "GOFR_VAULT_PORT=8201\n",
        encoding="utf-8",
    )

    (project_root / "config" / "gofr_approles.json").write_text(
        """
        {
          "schema_version": 1,
          "project": "gofr-dig",
          "roles": [
            {"role_name": "gofr-dig", "policies": ["gofr-dig-policy"]}
          ]
        }
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    # Bootstrap artifacts for discovery
    (project_root / "secrets" / "vault_root_token").write_text("root\n", encoding="utf-8")
    (project_root / "secrets" / "vault_unseal_key").write_text("unseal\n", encoding="utf-8")

    module = _load_setup_approle_module(Path.cwd())

    class FakeBootstrap:
        def __init__(self, vault_addr: str):
            self.vault_addr = vault_addr

        def ensure_unsealed(self, _unseal_key: str) -> bool:
            return True

    class FakeAdmin:
        def __init__(self, _client):
            self.synced_roles = []

        def enable_approle_auth(self, mount_point: str = "approle") -> None:
            assert mount_point == "approle"

        def update_policies(self) -> None:
            return None

        def provision_service_role(
            self,
            service_name: str,
            policy_name: str,
            additional_policy_names=None,
            token_ttl: str = "1h",
            token_max_ttl: str = "24h",
        ) -> None:
            self.synced_roles.append(service_name)

        def generate_service_credentials(self, _service_name: str):
            raise AssertionError("generate_service_credentials must not be called in --policies-only")

    class FakeClient:
        def __init__(self, _config):
            pass

    setattr(module, "VaultBootstrap", FakeBootstrap)
    setattr(module, "VaultClient", FakeClient)
    setattr(module, "VaultAdmin", FakeAdmin)

    argv = [
        "setup_approle.py",
        "--project-root",
        str(project_root),
        "--config",
        "config/gofr_approles.json",
        "--policies-only",
    ]

    old_argv = sys.argv
    try:
        sys.argv = argv
        rc = module.main()
    finally:
        sys.argv = old_argv

    assert rc == 0

    # Should not have created credentials output dir
    assert not (project_root / "secrets" / "service_creds").exists()
