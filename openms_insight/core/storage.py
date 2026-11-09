"""Read cached parquet files through the S3 API when the workspace lives on S3.

Apps built from the OpenMS streamlit-template can keep their workspaces on an
S3 bucket that is mounted as a file system (JuiceFS). The mount is what the
components write to, and it works for reading too, but an S3 gateway serves the
same files as objects, and polars reads those with ranged requests and pushes
column and row-group selection down to the store.

The app announces this through environment variables (the template's
``k8s/components/storage-s3`` sets them):

``WORKSPACES_DIR``
    The mounted root that the bucket's objects are relative to.
``WORKSPACES_S3_ENDPOINT``, ``WORKSPACES_S3_BUCKET``,
``WORKSPACES_S3_ACCESS_KEY``, ``WORKSPACES_S3_SECRET_KEY``
    The gateway and its credentials. All four must be set.

S3 reads are opt-in: set ``OPENMS_INSIGHT_S3=1`` as well. A view reads its
small cache files again on every rerun, and through the S3 API each read is a
few ranged requests to the gateway, where the mount serves them from its local
cache. On the live apps that made selecting a table row about three times
slower. Without ``OPENMS_INSIGHT_S3=1``, when the variables are not all set, or
when a file lies outside ``WORKSPACES_DIR``, files are read from the local
path. Writes always go to the mounted path.
"""

import os
from pathlib import Path
from typing import Any, Union

import polars as pl

PathLike = Union[str, "os.PathLike[str]"]

_ENV = (
    "WORKSPACES_S3_ENDPOINT",
    "WORKSPACES_S3_BUCKET",
    "WORKSPACES_S3_ACCESS_KEY",
    "WORKSPACES_S3_SECRET_KEY",
)
_DEFAULT_ROOT = "/workspaces-streamlit-template"
_ON = {"1", "true", "yes", "on"}


def s3_enabled() -> bool:
    """True when S3 reads are switched on and the workspace is on S3."""
    if os.environ.get("OPENMS_INSIGHT_S3", "").strip().lower() not in _ON:
        return False
    return all(os.environ.get(name, "").strip() for name in _ENV)


def _object_key(path: PathLike) -> str | None:
    root = Path(os.path.abspath(os.environ.get("WORKSPACES_DIR") or _DEFAULT_ROOT))
    target = Path(os.path.abspath(os.fspath(path)))
    try:
        rel = target.relative_to(root)
    except ValueError:
        return None
    key = rel.as_posix()
    return key if key not in ("", ".") else None


def s3_location(path: PathLike) -> tuple[str, dict[str, str]] | None:
    """The ``s3://`` URI and polars ``storage_options`` for ``path``.

    Returns None when S3 is not in use or ``path`` is not under the
    workspaces root, in which case the local path should be read.
    """
    if not s3_enabled():
        return None
    key = _object_key(path)
    if key is None:
        return None
    endpoint = os.environ["WORKSPACES_S3_ENDPOINT"].strip().rstrip("/")
    bucket = os.environ["WORKSPACES_S3_BUCKET"].strip()
    options = {
        "aws_endpoint_url": endpoint,
        "aws_access_key_id": os.environ["WORKSPACES_S3_ACCESS_KEY"].strip(),
        "aws_secret_access_key": os.environ["WORKSPACES_S3_SECRET_KEY"].strip(),
        "aws_region": os.environ.get("WORKSPACES_S3_REGION", "").strip() or "us-east-1",
        "aws_virtual_hosted_style_request": "false",
    }
    if endpoint.startswith("http://"):
        options["aws_allow_http"] = "true"
    return f"s3://{bucket}/{key}", options


def scan_parquet(path: PathLike, **kwargs: Any) -> pl.LazyFrame:
    """``pl.scan_parquet`` that reads through the S3 API when the workspace is on S3."""
    location = s3_location(path)
    if location is None:
        return pl.scan_parquet(path, **kwargs)
    uri, options = location
    return pl.scan_parquet(uri, storage_options=options, **kwargs)
