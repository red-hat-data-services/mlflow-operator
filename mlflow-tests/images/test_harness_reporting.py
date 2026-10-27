"""Exercise the shell entrypoint without cluster access or real deployment."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

import pytest


@pytest.fixture
def harness(tmp_path: Path):
    images = tmp_path / "mlflow-tests" / "images"
    images.mkdir(parents=True)
    for name in ("test-run.sh", "write_harness_junit.py"):
        shutil.copy(Path(__file__).with_name(name), images / name)
    (images / "patch-csv.sh").write_text(
        'find_csv_and_update() { [ "$FAIL_STAGE" != csv ]; }\n'
    )
    # Full diagnostics must run only after a report has been written.
    debug = images / "collect-debug-logs.sh"
    debug.write_text(
        "#!/bin/bash\nset -eu\n"
        'test -s "$TEST_RESULTS_DIR/xunit_report_${STORAGE_TYPE}.xml"\n'
        'touch "$TEST_RESULTS_DIR/debug-collected"\n'
    )
    debug.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mock = bin_dir / "mock"
    mock.write_text(
        f"#!{sys.executable}\n"
        + """
import os
from pathlib import Path
import sys

cmd = Path(sys.argv[0]).name
args = sys.argv[1:]
stage = os.environ["FAIL_STAGE"]
results = Path(os.environ["TEST_RESULTS_DIR"])
if cmd == "kubectl":
    if args[0].startswith("--request-timeout="):
        # The first snapshot call must already have a readable JUnit report.
        assert list(results.glob("*unit*.xml"))
        print("mock cluster snapshot")
        sys.exit(0)
    if args[:2] in (["get", "namespace"], ["create", "namespace"]):
        sys.exit(1 if stage == "namespace" else 0)
    if args[:2] == ["create", "token"]:
        print("test-token")
        sys.exit(1 if stage == "token" else 0)
    if args[:2] == ["apply", "-f"]:
        sys.stdin.read()
        sys.exit(1 if stage == "rbac" else 0)
    if args[0] == "wait":
        if stage == "available" or (stage == "version" and any("status.version" in a for a in args)):
            sys.exit(1)
    if args[:2] == ["get", "mlflow"] and any("status.url" in a for a in args):
        if stage != "url":
            print("https://mlflow.example/mlflow")
elif cmd == "curl":
    assert "Authorization: Bearer test-token" in args
    Path(args[args.index("-o") + 1]).write_text("mock server response")
    print("503" if stage == "server-info" else "200", end="")
    if stage == "curl-timeout":
        print("transfer timed out after headers", file=sys.stderr)
        sys.exit(28)
    if stage == "curl-retry" and not (results / "curl-retried").exists():
        (results / "curl-retried").touch()
        sys.exit(28)
elif cmd == "uv":
    if "pytest" in args:
        output = next(a.split("=", 1)[1] for a in args if a.startswith("--junit-xml="))
        Path(output).write_text("<testsuites><testsuite name='pytest-original'/></testsuites>")
        sys.exit(1 if stage == "pytest" else 0)
    sys.exit(7 if stage == "deploy" else 0)
elif cmd == "sleep":
    pass
else:
    raise AssertionError(cmd)
"""
    )
    mock.chmod(0o755)
    for name in ("kubectl", "curl", "uv", "sleep"):
        (bin_dir / name).symlink_to(mock)
    results = tmp_path / "results"
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "TEST_RESULTS_DIR": str(results),
        "MLFLOW_TEST_SUPPORTED_VERSION": "3.15.0",
        "SUPPORTED_MLFLOW_VERSION_RAW": "3.15.0",
        "INFRASTRUCTURE_PLATFORM": "openshift",
        "SKIP_CLEANUP": "true",
        "SKIP_INFRASTRUCTURE": "true",
        "DEPLOY_MLFLOW_OPERATOR": "false",
        "workspaces": "test-workspace",
        "LC_ALL": "C",
    }

    def run(stage, storage="file", pytest_args=(), **overrides):
        run_env = dict(env, FAIL_STAGE=stage, STORAGE_TYPE=storage, **overrides)
        return subprocess.run(
            [
                "bash",
                str(images / "test-run.sh"),
                "-o",
                "junit_suite_name=backport-e2e",
                *pytest_args,
            ],
            env=run_env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    return run, results


@pytest.mark.parametrize("storage", ["file", "s3"])
@pytest.mark.parametrize(
    "stage,case",
    [
        ("config", "test_config"),
        ("csv", "test_patch_csv"),
        ("namespace", "test_create_workspace_namespace"),
        ("deploy", "test_deploy"),
        ("rbac", "test_setup_rbac"),
        ("url", "test_wait_for_mlflow_status_url"),
        ("token", "test_create_kube_token"),
        ("available", "test_wait_for_mlflow_cr_available"),
        ("server-info", "test_wait_for_mlflow_server_info"),
        ("curl-timeout", "test_wait_for_mlflow_server_info"),
        ("version", "test_wait_for_mlflow_status_version"),
    ],
)
def test_bootstrap_failure_is_reported(harness, storage, stage, case):
    run, results = harness
    overrides = {}
    if stage == "config":
        overrides["DB_TYPE"] = "invalid"
    if stage == "csv":
        overrides["DEPLOY_MLFLOW_OPERATOR"] = "true"
    if stage == "version":
        overrides["pytest_args"] = ("-m", "post_upgrade")
    result = run(stage, storage, **overrides)
    assert result.returncode == 1, result.stdout + result.stderr
    suite = parse(results / f"xunit_report_{storage}.xml").getroot().find("testsuite")
    assert suite.get("name") == "backport-e2e"
    assert suite.get("errors") == "1"
    assert suite.find("testcase").get("name") == case
    assert "mock cluster snapshot" in suite.find("testcase/error").text
    if stage in (
        "deploy",
        "url",
        "available",
        "server-info",
        "curl-timeout",
        "version",
    ):
        assert (results / "debug-collected").exists()
    if stage == "server-info":
        assert "HTTP=503" in result.stdout
        assert "mock server response" in suite.find("testcase/error").text
    if stage == "curl-timeout":
        assert "HTTP=200 curl_exit=28" in result.stdout
        assert "last_curl_exit=28" in suite.find("testcase/error").get("message")


@pytest.mark.parametrize(
    "stage,returncode", [("success", 0), ("pytest", 1), ("curl-retry", 0)]
)
def test_authenticated_readiness_preserves_pytest_report(harness, stage, returncode):
    run, results = harness
    result = run(stage)
    assert result.returncode == returncode, result.stdout + result.stderr
    suite = parse(results / "xunit_report_file.xml").getroot().find("testsuite")
    assert suite.get("name") == "pytest-original"
    if stage == "curl-retry":
        assert "HTTP=200 curl_exit=28" in result.stdout
        assert (results / "curl-retried").exists()


def test_existing_pytest_report_survives_harness_error(harness):
    run, results = harness
    results.mkdir()
    report = results / "xunit_report_file.xml"
    original = "<testsuites><testsuite name='previous-pytest'/></testsuites>"
    report.write_text(original)
    result = run("config", DB_TYPE="invalid")
    assert result.returncode == 1, result.stdout + result.stderr
    assert report.read_text() == original


@pytest.mark.parametrize(
    "args",
    [
        ("-o", "junit_suite_name=MLflow E2E"),
        ("--override-ini", "junit_suite_name=MLflow E2E"),
        ("--override-ini=junit_suite_name=MLflow E2E",),
        ("-ojunit_suite_name=MLflow E2E",),
        ("-o=junit_suite_name=MLflow E2E",),
    ],
)
def test_bootstrap_report_preserves_suite_name_spaces(harness, args):
    run, results = harness
    result = run("config", pytest_args=args, DB_TYPE="invalid")
    assert result.returncode == 1, result.stdout + result.stderr
    suite = parse(results / "xunit_report_file.xml").getroot().find("testsuite")
    assert suite.get("name") == "MLflow E2E"


def test_unrelated_pytest_argument_does_not_override_suite_name(harness):
    run, results = harness
    result = run(
        "config", pytest_args=("-k", "junit_suite_name=other suite"), DB_TYPE="invalid"
    )
    assert result.returncode == 1, result.stdout + result.stderr
    suite = parse(results / "xunit_report_file.xml").getroot().find("testsuite")
    assert suite.get("name") == "backport-e2e"
