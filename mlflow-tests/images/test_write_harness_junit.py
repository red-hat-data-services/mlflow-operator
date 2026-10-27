from pathlib import Path
from xml.etree.ElementTree import parse

import pytest
from write_harness_junit import harness_junit_path, write_harness_error_junit


def test_harness_junit_path_includes_storage_type(tmp_path: Path) -> None:
    assert harness_junit_path(str(tmp_path), "file") == str(
        tmp_path / "xunit_report_file.xml"
    )
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
    output.write_text(
        "<testsuites><testsuite name='mlflow-e2e'/></testsuites>", encoding="utf-8"
    )
    original = output.read_text(encoding="utf-8")

    wrote = write_harness_error_junit(
        str(output),
        test_name="test_deploy",
        message="deploy.py failed",
    )

    assert wrote is False
    assert output.read_text(encoding="utf-8") == original


def test_write_harness_error_junit_replace_overwrites_existing(tmp_path: Path) -> None:
    output = tmp_path / "xunit_report_file.xml"
    output.write_text(
        "<testsuites><testsuite name='old'/></testsuites>", encoding="utf-8"
    )

    wrote = write_harness_error_junit(
        str(output),
        test_name="test_deploy",
        message="deploy.py failed",
        body="snapshot included",
        replace=True,
    )

    assert wrote is True
    root = parse(output).getroot()
    case = root.find("testsuite").find("testcase")
    assert case.get("name") == "test_deploy"
    assert "snapshot included" in (case.find("error").text or "")


@pytest.mark.parametrize("replace", [False, True])
@pytest.mark.parametrize(
    "invalid",
    [
        "\x00",
        "\x01",
        "\x0b",
        "\x1b",
        "\x1f",
        pytest.param("\ud800", id="high-surrogate"),
        pytest.param("\udce2", id="truncated-utf8-surrogate"),
        "\ufffe",
        "\uffff",
    ],
)
def test_diagnostics_are_xml_safe(tmp_path: Path, invalid: str, replace: bool) -> None:
    output = tmp_path / "xunit_report_file.xml"
    if replace:
        write_harness_error_junit(
            str(output), test_name="test_deploy", message="initial"
        )
    valid = '\t\né中😀<&>"\ud7ff\ue000\ufffd\U0010ffff'
    diagnostics = f"before{invalid}after{valid}"
    expected = f"before\ufffdafter{valid}"

    assert write_harness_error_junit(
        str(output),
        suite_name=diagnostics,
        classname=diagnostics,
        test_name=diagnostics,
        message=diagnostics,
        body=diagnostics,
        hostname=diagnostics,
        replace=replace,
    )

    suite = parse(output).getroot().find("testsuite")
    case = suite.find("testcase")
    error = case.find("error")
    assert suite.get("name") == expected
    assert suite.get("hostname") == expected
    assert case.get("classname") == expected
    assert case.get("name") == expected
    assert error.get("message") == expected
    assert error.text == expected
