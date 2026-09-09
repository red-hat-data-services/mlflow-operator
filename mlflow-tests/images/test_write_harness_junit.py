import os
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent
from xml.etree.ElementTree import parse

import pytest

from write_harness_junit import harness_junit_path, write_harness_error_junit


def bash_with_mapfile() -> str:
    bash = shutil.which("bash")
    if bash is None or subprocess.run(
        [bash, "-c", "type mapfile >/dev/null 2>&1"], check=False
    ).returncode:
        pytest.skip("test-run.sh requires Bash with mapfile support")
    return bash


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def _mlflow_delete_commands(kubectl_log: str) -> list[str]:
    return [
        line
        for line in kubectl_log.splitlines()
        if line.split()[:2] == ["delete", "mlflow"]
    ]


def test_harness_junit_path_includes_storage_type(tmp_path: Path) -> None:
    assert harness_junit_path(str(tmp_path), "file") == str(tmp_path / "xunit_report_file.xml")
    assert harness_junit_path(str(tmp_path), None) == str(tmp_path / "xunit_report.xml")


def test_write_harness_error_junit_matches_pytest_shape(tmp_path: Path) -> None:
    output = tmp_path / "xunit_report_file.xml"
    wrote = write_harness_error_junit(
        str(output),
        suite_name="mlflow-e2e",
        test_name="test_wait_for_mlflow_server_info",
        message="MLflow server-info endpoint did not become reachable within timeout",
        body="storage=file backend=postgres\nURL: https://example/mlflow/api/3.0/mlflow/server-info",
        hostname="mlflow-tests",
    )

    assert wrote is True
    root = parse(output).getroot()
    assert root.tag == "testsuites"
    assert root.get("name") == "pytest tests"
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.get("name") == "mlflow-e2e"
    assert suite.get("errors") == "1"
    assert suite.get("tests") == "1"
    case = suite.find("testcase")
    assert case is not None
    assert case.get("classname") == "tests.harness.TestHarnessSetup"
    assert case.get("name") == "test_wait_for_mlflow_server_info"
    error = case.find("error")
    assert error is not None
    assert "server-info" in (error.get("message") or "")
    assert "backend=postgres" in (error.text or "")


def test_write_harness_error_junit_does_not_overwrite_existing(tmp_path: Path) -> None:
    output = tmp_path / "xunit_report_file.xml"
    output.write_text("<testsuites><testsuite name='mlflow-e2e'/></testsuites>", encoding="utf-8")
    original = output.read_text(encoding="utf-8")

    wrote = write_harness_error_junit(
        str(output),
        test_name="test_deploy",
        message="deploy.py failed",
    )

    assert wrote is False
    assert output.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("overrides", "expected_returncode", "expect_delete"),
    [
        ({"UV_PYTEST_EXIT": "0"}, 0, True),
        ({"UV_PYTEST_EXIT": "1"}, 1, True),
        ({"UV_DEPLOY_EXIT": "1"}, 1, True),
        ({"HARNESS_SIGNAL": "INT"}, 130, True),
        ({"HARNESS_SIGNAL": "TERM"}, 143, True),
        ({"SKIP_CLEANUP": "true"}, 1, False),
        (
            {
                "SKIP_DEPLOYMENT": "true",
                "SKIP_CLEANUP": "false",
                "CLEANUP_REUSED_RESOURCES": "false",
            },
            1,
            False,
        ),
        (
            {
                "SKIP_DEPLOYMENT": "true",
                "SKIP_CLEANUP": "false",
                "CLEANUP_REUSED_RESOURCES": "true",
            },
            1,
            True,
        ),
        (
            {
                "SKIP_DEPLOYMENT": "true",
                "SKIP_CLEANUP": "false",
                "CLEANUP_REUSED_RESOURCES": "on_success",
                "UV_PYTEST_EXIT": "0",
            },
            0,
            True,
        ),
        (
            {
                "SKIP_DEPLOYMENT": "true",
                "SKIP_CLEANUP": "false",
                "CLEANUP_REUSED_RESOURCES": "on_success",
            },
            1,
            False,
        ),
    ],
    ids=[
        "last-suite-success",
        "last-suite-failed-pytest",
        "partial-deploy-failure",
        "interrupt",
        "terminate",
        "skip-cleanup",
        "reuse-preserve",
        "reuse-cleanup",
        "reuse-cleanup-on-success",
        "reuse-preserve-on-failure",
    ],
)
def test_last_suite_deletes_cluster_scoped_mlflow_cr(
    tmp_path: Path,
    overrides: dict[str, str],
    expected_returncode: int,
    expect_delete: bool,
) -> None:
    bash = bash_with_mapfile()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    kubectl_log = tmp_path / "kubectl.log"
    uv_log = tmp_path / "uv.log"

    _write_executable(
        fake_bin / "kubectl",
        dedent(
            f"""\
            #!/bin/sh
            echo "$*" >> "{kubectl_log}"
            case "$*" in
                *"create token"*) printf 'fake-token\\n' ;;
                *"jsonpath={{.status.url}}"*) printf 'https://mlflow.example/mlflow' ;;
            esac
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "curl",
        dedent(
            """\
            #!/bin/sh
            output_file=""
            while [ "$#" -gt 0 ]; do
                if [ "$1" = "-o" ]; then
                    output_file="$2"
                    shift 2
                else
                    shift
                fi
            done
            [ -z "$output_file" ] || printf '{}' > "$output_file"
            printf '200'
            """
        ),
    )
    _write_executable(fake_bin / "sleep", "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "uv",
        dedent(
            """\
            #!/bin/sh
            case "$*" in
                *deploy.py*) exit "${UV_DEPLOY_EXIT:-0}" ;;
                *pytest*)
                    if [ -n "${HARNESS_SIGNAL:-}" ]; then
                        trap 'echo child-stopped >> "$UV_LOG"; exit 0' TERM
                        echo child-started >> "$UV_LOG"
                        kill -s "${HARNESS_SIGNAL}" "$PPID"
                        while true; do sleep 1; done
                    fi
                    exit "${UV_PYTEST_EXIT:-1}"
                    ;;
            esac
            exit 0
            """
        ),
    )

    results_dir = tmp_path / "results"
    env = os.environ.copy()
    env.pop("DB_TYPE", None)
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "LC_ALL": "C",
            "TEST_RESULTS_DIR": str(results_dir),
            "MLFLOW_TEST_SUPPORTED_VERSION": "3.14",
            "SUPPORTED_MLFLOW_VERSION_RAW": "3.14.0",
            "INFRASTRUCTURE_PLATFORM": "openshift",
            "FORCE_PORT_FORWARD": "false",
            "DEPLOY_MLFLOW_OPERATOR": "false",
            "SKIP_DEPLOYMENT": "false",
            "SKIP_OPERATOR": "true",
            "SKIP_INFRASTRUCTURE": "true",
            "SKIP_CLEANUP": "false",
            "CLEANUP_REUSED_RESOURCES": "false",
            "BACKEND_STORE": "sqlite",
            "REGISTRY_STORE": "sqlite",
            "ARTIFACT_BACKENDS": "s3",
            "workspaces": "test-workspace",
            "UV_LOG": str(uv_log),
        }
    )
    env.update(overrides)

    result = subprocess.run(
        [bash, str(Path(__file__).with_name("test-run.sh"))],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == expected_returncode
    log_text = kubectl_log.read_text(encoding="utf-8") if kubectl_log.exists() else ""
    deletes = _mlflow_delete_commands(log_text)
    if expect_delete:
        assert len(deletes) == 1, (
            "expected exactly one MLflow CR deletion, kubectl log:\n"
            f"{log_text}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "--wait" in deletes[0]
        assert all("-n" not in line.split() for line in deletes)
        assert "Deleting cluster-scoped MLflow CR mlflow" in result.stdout
        if expected_returncode != 0:
            log_lines = log_text.splitlines()
            assert log_lines.index(deletes[0]) > next(
                i for i, line in enumerate(log_lines) if line == "get namespaces"
            ), "failure diagnostics must be collected before deleting the MLflow CR"
        if "HARNESS_SIGNAL" in overrides:
            assert uv_log.read_text(encoding="utf-8").splitlines() == [
                "child-started",
                "child-stopped",
            ]
    else:
        assert deletes == [], f"unexpected MLflow CR deletion: {deletes}\nstderr:\n{result.stderr}"


def test_mlflow_delete_failure_stops_before_next_backend(tmp_path: Path) -> None:
    bash = bash_with_mapfile()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    kubectl_log = tmp_path / "kubectl.log"
    uv_log = tmp_path / "uv.log"

    _write_executable(
        fake_bin / "kubectl",
        dedent(
            f"""\
            #!/bin/sh
            echo "$*" >> "{kubectl_log}"
            case "$*" in
                "delete mlflow "*) exit 1 ;;
                *"create token"*) printf 'fake-token\\n' ;;
                *"jsonpath={{.status.url}}"*) printf 'https://mlflow.example/mlflow' ;;
            esac
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "curl",
        "#!/bin/sh\nwhile [ \"$#\" -gt 0 ]; do [ \"$1\" = -o ] && { printf '{}' > \"$2\"; shift; }; shift; done\nprintf '200'\n",
    )
    _write_executable(fake_bin / "sleep", "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "uv",
        "#!/bin/sh\necho \"$*\" >> \"$UV_LOG\"\nexit 0\n",
    )

    env = os.environ.copy()
    env.pop("DB_TYPE", None)
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "LC_ALL": "C",
            "TEST_RESULTS_DIR": str(tmp_path / "results"),
            "MLFLOW_TEST_SUPPORTED_VERSION": "3.14",
            "SUPPORTED_MLFLOW_VERSION_RAW": "3.14.0",
            "INFRASTRUCTURE_PLATFORM": "openshift",
            "FORCE_PORT_FORWARD": "false",
            "DEPLOY_MLFLOW_OPERATOR": "false",
            "SKIP_DEPLOYMENT": "false",
            "SKIP_OPERATOR": "true",
            "SKIP_INFRASTRUCTURE": "true",
            "SKIP_CLEANUP": "false",
            "FAIL_FAST": "false",
            "BACKEND_STORE": "sqlite",
            "REGISTRY_STORE": "sqlite",
            "ARTIFACT_BACKENDS": "file,s3",
            "workspaces": "test-workspace",
            "UV_LOG": str(uv_log),
        }
    )

    result = subprocess.run(
        [bash, str(Path(__file__).with_name("test-run.sh"))],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 1
    assert "failed to delete MLflow CR mlflow" in result.stderr
    deploys = [
        line
        for line in uv_log.read_text(encoding="utf-8").splitlines()
        if "deploy.py" in line
    ]
    assert len(deploys) == 1, "the next backend must not start after MLflow CR deletion fails"
