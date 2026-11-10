# File Intake: HTML upload → backend

A standalone module (it does not touch the travel planner). It takes the
"File format" dropdown from the intake form and adds a working upload path
with a size limit for each format.

## 1. Requirements

| # | Requirement |
|---|---|
| R1 | User must pick a **format** and a **file**, and both are validated before anything is sent. |
| R2 | The file **extension must match** the chosen format (`csv-csv` → `.csv`, `geotiff-tiff` → `.tiff` …). |
| R3 | **Each format has its own maximum size**, enforced in the browser (fast feedback) **and** on the server (the real guard). |
| R4 | The upload must survive proxy request-size caps, so large files are sent in **8 MB chunks**. |
| R5 | The server checks the **content**, not just the name: magic bytes for binary formats and UTF-8 or no-NUL for text formats. |
| R6 | Progress bar, cancel, and automatic retry of failed chunks. |
| R7 | A SHA-256 is computed and the file is stored under `<UPLOAD_ROOT>/<format>/<id>_<name>`. |
| R8 | One source of truth: limits live in `backend/formats.py`, and the page reads them from `GET /api/formats`. |

## 2. How big can an upload be?

HTML itself has **no size limit**. `<input type=file>` can select files of any
size. The real limit is the **smallest cap between the browser and the
storage**:

| Layer | Typical default cap per request |
|---|---|
| nginx `client_max_body_size` | 1 MB |
| IIS / Azure App Service `maxAllowedContentLength` | ~28.6 MB |
| ASP.NET Core Kestrel `MaxRequestBodySize` | 30 MB |
| AWS API Gateway | 10 MB |
| Azure Front Door / App Gateway (WAF body inspection) | 128 KB – 4 MB inspected |
| Databricks Files API / UC Volume upload | 5 GB per file |
| FastAPI / Starlette | none (you must enforce it) |

Chunking (R4) keeps every request under 8 MB, so the proxy defaults no longer
matter. The limits users actually hit are the per-format ones below, which are
capped at **5 GB** to match the Volume per-file limit.

### Per-format limits (`backend/formats.py`)

| Option value | Label | Ext | Max | Why |
|---|---|---|---|---|
| `csv-csv` | CSV | .csv | **2 GB** | Streams row by row; no memory pressure. |
| `json-json` | JSON | .json | **500 MB** | Normal JSON is parsed fully into RAM. Use NDJSON or Parquet for anything larger. |
| `excel-xlsx` | EXCEL | .xlsx | **100 MB** | 1,048,576-row sheet cap; SheetJS/openpyxl load the whole workbook. |
| `ods-ods` | ODS | .ods | **50 MB** | ODS parsers are slower and use more memory than xlsx. |
| `shp-zip` | SHP | .zip | **2 GB** | The shapefile spec caps each .shp/.dbf at 2 GB. |
| `geojson-geojson` | GEOJSON | .geojson | **1 GB** | Text, parsed whole by most GIS libs. |
| `geojson-json` | GEOJSON | .json | **1 GB** | Same as above. |
| `geopkg-gpkg` | GEOPACKAGE | .gpkg | **5 GB** | SQLite; read with random access, not loaded whole. |
| `geoml-gml` | GML | .gml | **1 GB** | Verbose XML. |
| `pdf-pdf` | PDF | .pdf | **200 MB** | Documents; anything larger is usually scanned images. |
| `geotiff-tif` / `geotiff-tiff` | GEOTIFF | .tif / .tiff | **5 GB** | Classic TIFF stops at 4 GB, so larger files must be BigTIFF or COG. |
| `lidar-las` | LiDAR | .las | **5 GB** | Prefer LAZ, which is 5–10× smaller. |
| `lidar-laz` | LiDAR | .laz | **5 GB** | |
| `netcdf-nc` | NetCDF | .nc | **5 GB** | Supports both v3 and v4 (HDF5). |
| `gpx-gpx` | GPX | .gpx | **100 MB** | GPS tracks are small. |
| `parquet-parquet` | PARQUET | .parquet | **5 GB** | Columnar; the footer is also verified. |

These are sensible starting **policies**, not hard technical limits. Change the
`max_bytes` value in `formats.py` and both the UI and the API pick it up.
For more than 5 GB, skip the web server: split the file, or have the browser
upload straight to storage (Databricks Files API, ADLS SAS URL, or an S3
presigned multipart upload).

## 3. Design

```
Browser (index.html)                    FastAPI (backend/app.py)
───────────────────                     ────────────────────────
GET /api/formats  ───────────────────▶  registry + limits
validate ext + size locally
POST /api/uploads {name,size,fmt} ───▶  re-validate ext + size → upload_id
PUT  /chunks/0..N  (8 MB each)   ────▶  stream to _staging/<id>.part,
   (retry x3, backoff)                  reject >chunk / >declared size
POST /complete    ───────────────────▶  byte count, magic/text sniff,
                                        SHA-256, move to <fmt>/<id>_<name>
DELETE /uploads/<id> (on cancel/fail) ▶ cleanup
```

## 4. Running it

```bash
pip install fastapi uvicorn
uvicorn file_intake.backend.app:app --reload      # from repo root
# open http://127.0.0.1:8000/
python -m pytest file_intake/tests                # 9 tests
```

Environment variables: `UPLOAD_ROOT` (default `./file_intake_data`),
`UPLOAD_CHUNK_SIZE` (default 8 MiB), `UPLOAD_SESSION_TTL` (default 24 h).

## 5. Production to-dos

- Upload sessions are kept in memory, which only works with one worker. Move them to Redis or Postgres before scaling out.
- Add authentication and per-user quotas. Add AV scanning (ClamAV / Defender) before files are promoted out of staging.
- Swap the local `shutil.move` for a write to the Databricks Volume or ADLS.
- Deep validation after upload: open with GDAL/pyarrow/openpyxl and check that a .zip shapefile has .shp/.shx/.dbf.

## 6. About the `parse5 … control-character-in-input-stream` error in the screenshot

That error comes from pasting the minified **SheetJS `xlsx.js` inline** inside
`<script>…</script>` in `portal-intake.html`. Its lookup tables contain raw
control characters (`\0 \b \x0B \f …`) that are invalid in an HTML document,
so the Vite HTML parser stops. Fix: do not inline it. Either `npm i xlsx` and
`import * as XLSX from "xlsx"` from your JS module, or reference it as
`<script src="/vendor/xlsx.full.min.js"></script>`.
