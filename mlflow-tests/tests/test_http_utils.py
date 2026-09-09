import os

import pytest

from tests.constants.config import Config
from tests.http_utils import configure_ca_bundle_environment


@pytest.fixture(scope="module", autouse=True)
def create_experiments_and_runs() -> dict:
    return {}


def test_configure_ca_bundle_environment(monkeypatch):
    ca_bundle = "/tmp/test-ca-bundle.crt"
    monkeypatch.setattr(Config, "CA_BUNDLE", ca_bundle)
    bundle_variables = (
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "AWS_CA_BUNDLE",
    )
    for name in bundle_variables:
        monkeypatch.setenv(name, os.environ.get(name, ""))

    configure_ca_bundle_environment()

    for name in bundle_variables:
        assert os.environ[name] == ca_bundle


def test_configure_ca_bundle_environment_unsets_empty_bundles(monkeypatch):
    monkeypatch.setattr(Config, "CA_BUNDLE", "")
    bundle_variables = (
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "AWS_CA_BUNDLE",
    )
    for name in bundle_variables:
        monkeypatch.setenv(name, "")

    configure_ca_bundle_environment()

    for name in bundle_variables:
        assert name not in os.environ


def test_configure_ca_bundle_environment_preserves_existing_bundles(monkeypatch):
    monkeypatch.setattr(Config, "CA_BUNDLE", "")
    bundle_variables = (
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "AWS_CA_BUNDLE",
    )
    for name in bundle_variables:
        monkeypatch.setenv(name, f"/tmp/{name.lower()}.crt")

    configure_ca_bundle_environment()

    for name in bundle_variables:
        assert os.environ[name] == f"/tmp/{name.lower()}.crt"
