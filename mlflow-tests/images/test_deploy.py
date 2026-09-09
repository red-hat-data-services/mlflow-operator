import importlib.util
from pathlib import Path
from types import SimpleNamespace

import yaml


DEPLOY_PY = Path(__file__).parents[2] / ".github/actions/deploy/deploy.py"
SPEC = importlib.util.spec_from_file_location("deploy", DEPLOY_PY)
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


def test_create_postgres_secret_applies_an_existing_secret() -> None:
    args = SimpleNamespace(
        artifact_storage="externals3",
        namespace="mlflow-test",
        postgres_host="postgres.example.test",
        postgres_port="5432",
        postgres_user="mlflow",
        postgres_password="password",
        postgres_backend_db="backend",
        postgres_registry_db="registry",
        postgres_sslmode="verify-full",
        s3_endpoint="",
        seaweedfs_tls=False,
    )
    deployer = deploy.MLflowDeployer(args)
    commands = []

    def run_command(command, description=None, **kwargs):
        commands.append((command, description, kwargs))
        manifest = Path(command[-1])
        secret = yaml.safe_load(manifest.read_text())
        assert secret == {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "mlflow-db-credentials", "namespace": "mlflow-test"},
            "type": "Opaque",
            "stringData": {
                "backend-store-uri": "postgresql://mlflow:password@postgres.example.test:5432/backend?sslmode=verify-full",
                "registry-store-uri": "postgresql://mlflow:password@postgres.example.test:5432/registry?sslmode=verify-full",
            },
        }

    deployer.run_command = run_command
    deployer.create_postgres_secret()

    assert len(commands) == 1
    assert commands[0][0][:3] == ["kubectl", "apply", "-f"]
    assert commands[0][1] == "Applying PostgreSQL credentials secret"
