import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path))
    monkeypatch.setenv("UPLOAD_CHUNK_SIZE", "1024")
    import file_intake.backend.app as app_mod
    app_mod = importlib.reload(app_mod)
    return TestClient(app_mod.app), tmp_path


def upload(c, name, data, fmt):
    r = c.post("/api/uploads", json={"filename": name, "size": len(data), "source_format": fmt})
    if r.status_code != 201:
        return r
    info = r.json()
    for i in range(info["total_chunks"]):
        chunk = data[i * info["chunk_size"]:(i + 1) * info["chunk_size"]]
        assert c.put(f"/api/uploads/{info['upload_id']}/chunks/{i}", content=chunk).status_code == 200
    return c.post(f"/api/uploads/{info['upload_id']}/complete")


def test_formats_listed(client):
    c, _ = client
    data = c.get("/api/formats").json()
    values = {f["value"] for f in data["formats"]}
    assert {"csv-csv", "parquet-parquet", "excel-xlsx", "geotiff-tiff"} <= values


def test_csv_roundtrip_multi_chunk(client):
    c, root = client
    data = b"a,b\n" + b"1,2\n" * 2000
    r = upload(c, "sales.csv", data, "csv-csv")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["size"] == len(data)
    assert (root / body["stored_at"]).read_bytes() == data


def test_wrong_extension_rejected(client):
    c, _ = client
    r = upload(c, "data.txt", b"a,b\n", "csv-csv")
    assert r.status_code == 422


def test_over_limit_rejected(client):
    c, _ = client
    r = c.post("/api/uploads", json={"filename": "big.xlsx", "size": 101 * 1024 * 1024,
                                     "source_format": "excel-xlsx"})
    assert r.status_code == 413
    assert "100 MB" in r.json()["detail"]


def test_magic_bytes_checked(client):
    c, _ = client
    r = upload(c, "fake.parquet", b"not parquet at all", "parquet-parquet")
    assert r.status_code == 415


def test_parquet_ok(client):
    c, _ = client
    assert upload(c, "x.parquet", b"PAR1" + b"\0" * 3000 + b"PAR1", "parquet-parquet").status_code == 200


def test_text_format_rejects_binary(client):
    c, _ = client
    assert upload(c, "x.geojson", b"\x00\x01binary", "geojson-geojson").status_code == 415


def test_chunk_cannot_exceed_declared_size(client):
    c, _ = client
    info = c.post("/api/uploads", json={"filename": "a.csv", "size": 10, "source_format": "csv-csv"}).json()
    r = c.put(f"/api/uploads/{info['upload_id']}/chunks/0", content=b"x" * 500)
    assert r.status_code == 413


def test_complete_before_all_chunks(client):
    c, _ = client
    info = c.post("/api/uploads", json={"filename": "a.csv", "size": 3000, "source_format": "csv-csv"}).json()
    c.put(f"/api/uploads/{info['upload_id']}/chunks/0", content=b"x" * 1024)
    assert c.post(f"/api/uploads/{info['upload_id']}/complete").status_code == 400
