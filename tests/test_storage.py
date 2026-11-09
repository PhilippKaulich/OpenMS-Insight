"""S3-aware parquet reads: local unless the workspace is on S3."""

import polars as pl
import pytest

from openms_insight.core import storage

S3_ENV = {
    "WORKSPACES_S3_ENDPOINT": "http://gateway:9000/",
    "WORKSPACES_S3_BUCKET": "flashapp",
    "WORKSPACES_S3_ACCESS_KEY": "user",
    "WORKSPACES_S3_SECRET_KEY": "secret",
}


@pytest.fixture
def on_s3(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACES_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMS_INSIGHT_S3", "1")
    for name, value in S3_ENV.items():
        monkeypatch.setenv(name, value)
    return tmp_path


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACES_DIR", str(tmp_path))
    for name in S3_ENV:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_local_without_variables(local):
    assert not storage.s3_enabled()
    assert storage.s3_location(local / "ws" / "a.parquet") is None


def test_partial_variables_stay_local(on_s3, monkeypatch):
    monkeypatch.setenv("WORKSPACES_S3_SECRET_KEY", "")
    assert not storage.s3_enabled()


def test_switch_off(on_s3, monkeypatch):
    monkeypatch.setenv("OPENMS_INSIGHT_S3", "0")
    assert storage.s3_location(on_s3 / "ws" / "a.parquet") is None


def test_off_unless_switched_on(on_s3, monkeypatch):
    """The workspace variables alone keep reads on the mount: a rerun reads
    every view's cache again, and through the gateway each read costs requests."""
    monkeypatch.delenv("OPENMS_INSIGHT_S3", raising=False)
    assert not storage.s3_enabled()
    assert storage.s3_location(on_s3 / "ws" / "a.parquet") is None


def test_maps_path_under_root(on_s3):
    uri, options = storage.s3_location(on_s3 / "ws 1" / "cache" / "a.parquet")
    assert uri == "s3://flashapp/ws 1/cache/a.parquet"
    assert options["aws_endpoint_url"] == "http://gateway:9000"
    assert options["aws_allow_http"] == "true"
    assert options["aws_virtual_hosted_style_request"] == "false"
    assert options["aws_access_key_id"] == "user"


def test_outside_root_and_root_itself_stay_local(on_s3, tmp_path_factory):
    other = tmp_path_factory.mktemp("elsewhere")
    assert storage.s3_location(other / "a.parquet") is None
    assert storage.s3_location(on_s3) is None
    assert storage.s3_location(on_s3 / ".." / "x.parquet") is None


def test_scan_parquet_reads_locally(local):
    path = local / "a.parquet"
    pl.DataFrame({"x": [1, 2, 3]}).write_parquet(path)
    assert storage.scan_parquet(path).select(pl.sum("x")).collect().item() == 6


def test_scan_parquet_passes_s3_location(on_s3, monkeypatch):
    seen = {}

    def fake_scan(source, **kwargs):
        seen["source"] = source
        seen.update(kwargs)
        return pl.LazyFrame()

    monkeypatch.setattr(storage.pl, "scan_parquet", fake_scan)
    storage.scan_parquet(on_s3 / "ws" / "a.parquet", hive_partitioning=False)
    assert seen["source"] == "s3://flashapp/ws/a.parquet"
    assert seen["storage_options"]["aws_endpoint_url"] == "http://gateway:9000"
    assert seen["hive_partitioning"] is False
