"""Shared HTTP helpers for integration-style test requests."""

import os

from tests.constants.config import Config


def get_mlflow_base_uri() -> str:
    """Return the configured MLflow base URI without a trailing slash."""
    return Config.MLFLOW_URI.rstrip("/")


def get_requests_verify_value() -> bool | str:
    """Return the requests-compatible TLS verify value for the current test config."""
    if str(Config.DISABLE_TLS).lower() in {"1", "true", "yes", "y"}:
        return False
    if Config.CA_BUNDLE:
        return Config.CA_BUNDLE
    return True


def get_s3_verify_value(endpoint_url: str | None = None) -> bool | str:
    """Return the verification setting for direct S3 and presigned URL requests."""
    if endpoint_url and endpoint_url.startswith("https://localhost:"):
        # SeaweedFS is port-forwarded through localhost in the self-hosted TLS suite,
        # but its certificate SANs only include the in-cluster service DNS names.
        return False
    if Config.CA_BUNDLE:
        return Config.CA_BUNDLE
    return str(Config.DISABLE_TLS).lower() not in {"1", "true", "yes", "y"}


def configure_ca_bundle_environment() -> None:
    bundle_variables = (
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "AWS_CA_BUNDLE",
    )
    if Config.CA_BUNDLE:
        for name in bundle_variables:
            os.environ[name] = Config.CA_BUNDLE
    else:
        for name in bundle_variables:
            if os.environ.get(name) == "":
                os.environ.pop(name)
