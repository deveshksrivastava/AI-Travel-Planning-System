"""Single source of truth for accepted upload formats.

Each key matches the ``<option value="...">`` used by the HTML form
(``<family>-<extension>``). The frontend fetches this registry from
``GET /api/formats`` so limits are never duplicated in two places.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

MB = 1024 * 1024
GB = 1024 * MB

# Absolute ceiling for any single file. Matches the per-file limit of the
# Databricks Files API / Unity Catalog Volume uploads (5 GB). Anything bigger
# should be split, or pushed straight to cloud storage (azcopy / presigned URL).
HARD_CAP_BYTES = 5 * GB

ZIP = (b"PK\x03\x04",)
TIFF = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")  # classic + BigTIFF
NETCDF = (b"CDF\x01", b"CDF\x02", b"CDF\x05", b"\x89HDF\r\n\x1a\n")  # v3 + v4/HDF5


@dataclass(frozen=True)
class FileFormat:
    value: str            # option value posted by the form
    label: str            # text shown in the dropdown
    extension: str        # required file extension (lower case, no dot)
    max_bytes: int        # per-format size limit
    kind: str             # "text" (UTF-8 sniffed) or "binary" (magic bytes)
    magic: tuple[bytes, ...] = field(default=())   # accepted leading bytes
    text_starts: tuple[str, ...] = field(default=())  # first non-space char(s)
    note: str = ""

    def public(self) -> dict:
        d = asdict(self)
        d.pop("magic")
        d.pop("text_starts")
        d["max_mb"] = round(self.max_bytes / MB)
        return d


FORMATS: dict[str, FileFormat] = {
    f.value: f
    for f in [
        FileFormat("csv-csv", "CSV", "csv", 2 * GB, "text",
                   note="Streamed row by row on ingest; size mainly bounded by storage."),
        FileFormat("json-json", "JSON", "json", 500 * MB, "text", text_starts=("{", "["),
                   note="Plain JSON is usually parsed fully in memory; use NDJSON/Parquet for more."),
        FileFormat("excel-xlsx", "EXCEL (.xlsx)", "xlsx", 100 * MB, "binary", ZIP,
                   note="Excel caps at 1,048,576 rows; SheetJS/openpyxl load the whole workbook into memory."),
        FileFormat("ods-ods", "ODS", "ods", 50 * MB, "binary", ZIP,
                   note="ODS parsers are slower and more memory-hungry than xlsx."),
        FileFormat("shp-zip", "SHP (.zip)", "zip", 2 * GB, "binary", ZIP,
                   note="Zip must contain .shp/.shx/.dbf (+.prj). Each .shp/.dbf is itself capped at 2 GB."),
        FileFormat("geojson-geojson", "GEOJSON (.geojson)", "geojson", 1 * GB, "text", text_starts=("{",)),
        FileFormat("geojson-json", "GEOJSON (.json)", "json", 1 * GB, "text", text_starts=("{",)),
        FileFormat("geopkg-gpkg", "GEOPACKAGE (.gpkg)", "gpkg", 5 * GB, "binary", (b"SQLite format 3\x00",)),
        FileFormat("geoml-gml", "GML", "gml", 1 * GB, "text", text_starts=("<",)),
        FileFormat("pdf-pdf", "PDF", "pdf", 200 * MB, "binary", (b"%PDF-",)),
        FileFormat("geotiff-tif", "GEOTIFF (.tif)", "tif", 5 * GB, "binary", TIFF,
                   note="Classic TIFF tops out at 4 GB; larger rasters must be BigTIFF / COG."),
        FileFormat("geotiff-tiff", "GEOTIFF (.tiff)", "tiff", 5 * GB, "binary", TIFF,
                   note="Classic TIFF tops out at 4 GB; larger rasters must be BigTIFF / COG."),
        FileFormat("lidar-las", "LiDAR (.las)", "las", 5 * GB, "binary", (b"LASF",),
                   note="Prefer .laz (5-10x smaller) for large point clouds."),
        FileFormat("lidar-laz", "LiDAR (.laz)", "laz", 5 * GB, "binary", (b"LASF",)),
        FileFormat("netcdf-nc", "NetCDF (.nc)", "nc", 5 * GB, "binary", NETCDF),
        FileFormat("gpx-gpx", "GPX (.gpx)", "gpx", 100 * MB, "text", text_starts=("<",)),
        FileFormat("parquet-parquet", "PARQUET (.parquet)", "parquet", 5 * GB, "binary", (b"PAR1",),
                   note="Footer is also checked for the trailing PAR1 marker."),
    ]
}

assert all(f.max_bytes <= HARD_CAP_BYTES for f in FORMATS.values())
