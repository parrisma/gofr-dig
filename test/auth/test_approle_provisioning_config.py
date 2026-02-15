from pathlib import Path

import pytest

from gofr_common.auth.approle_provisioning import AppRoleConfigError, load_approle_config


def test_load_approle_config_happy_path(tmp_path: Path) -> None:
    config_path = tmp_path / "gofr_approles.json"
    config_path.write_text(
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

    config = load_approle_config(config_path)

    assert config.schema_version == 1
    assert config.project == "gofr-dig"
    assert config.mount_point == "approle"
    assert config.token_ttl == "1h"
    assert config.token_max_ttl == "24h"
    assert config.credentials_output_dir == "secrets/service_creds"
    assert len(config.roles) == 1
    assert config.roles[0].role_name == "gofr-dig"
    assert config.roles[0].policies == ("gofr-dig-policy",)


@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        "{}",
        '{"schema_version": 2, "project": "x", "roles": [{"role_name": "a", "policies": ["p"]}]}',
        '{"schema_version": 1, "project": "", "roles": [{"role_name": "a", "policies": ["p"]}]}',
        '{"schema_version": 1, "project": "x", "roles": []}',
        '{"schema_version": 1, "project": "x", "roles": [{"role_name": "", "policies": ["p"]}]}',
        '{"schema_version": 1, "project": "x", "roles": [{"role_name": "a", "policies": []}]}',
    ],
)
def test_load_approle_config_rejects_invalid(tmp_path: Path, payload: str) -> None:
    config_path = tmp_path / "gofr_approles.json"
    config_path.write_text(payload + "\n", encoding="utf-8")

    with pytest.raises(AppRoleConfigError):
        load_approle_config(config_path)
