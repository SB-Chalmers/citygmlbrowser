from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.graph import TYPE_STYLE, build_graph
from api.parsers import parse_file
from api.parsers import citygml_20, citygml_30
from api.dialect import detect_dialect

logger = logging.getLogger("citygml_api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

MAX_UPLOAD_MB = int(os.getenv("CITYGML_MAX_UPLOAD_MB", "50"))
SUPPORTED_CITYGML = {"2.0", "3.0"}
SUPPORTED_ENERGY_ADE = {None, "2.0", "3.0"}

app = FastAPI(title="CityGML Browser API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _type_colors() -> dict[str, dict[str, str]]:
    return {
        kind: {
            "background": cfg["bg"],
            "border": cfg["border"],
            "font": cfg["font"],
        }
        for kind, cfg in TYPE_STYLE.items()
    }


def _error_payload(code: str, message: str, request_id: str) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "requestId": request_id,
        },
    }


def _success_payload(data: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "data": data,
        "meta": meta,
    }


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid.uuid4())
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.exception(
            "request_failed request_id=%s path=%s elapsed_ms=%s",
            request_id,
            request.url.path,
            elapsed_ms,
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload("internal_error", "Unexpected server error", request_id),
        )

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers["x-request-id"] = request_id
    response.headers["x-elapsed-ms"] = str(elapsed_ms)
    logger.info(
        "request_ok request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def _validate_support(dialect_citygml: str | None, dialect_energy: str | None, request_id: str) -> None:
    if dialect_citygml not in SUPPORTED_CITYGML:
        raise HTTPException(
            status_code=400,
            detail=_error_payload(
                "unsupported_citygml_version",
                f"Detected CityGML {dialect_citygml or 'unknown'}; supported versions: 2.0, 3.0.",
                request_id,
            ),
        )

    if dialect_energy not in SUPPORTED_ENERGY_ADE:
        raise HTTPException(
            status_code=400,
            detail=_error_payload(
                "unsupported_energy_ade_version",
                f"Detected Energy ADE {dialect_energy}; supported versions: 2.0, 3.0.",
                request_id,
            ),
        )


async def _persist_upload(upload: UploadFile) -> tuple[str, str, str]:
    content = await upload.read()
    size_bytes = len(content)
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "status": "error",
                "error": {
                    "code": "file_too_large",
                    "message": f"Uploaded file exceeds {MAX_UPLOAD_MB}MB limit",
                },
            },
        )

    suffix = Path(upload.filename or "upload.gml").suffix or ".gml"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    return tmp_path, upload.filename or Path(tmp_path).name, str(size_bytes)


def _request_id_from_headers(request: Request) -> str:
    return request.headers.get("x-request-id", str(uuid.uuid4()))


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    return _success_payload(
        data={"ok": True, "service": "citygml-browser-api"},
        meta={"apiVersion": "v1"},
    )


@app.post("/api/v1/parse-file")
async def parse_uploaded_file(request: Request, file: UploadFile = File(...)):
    request_id = _request_id_from_headers(request)
    started = time.perf_counter()
    tmp_path: str | None = None

    try:
        tmp_path, filename, size_bytes = await _persist_upload(file)
        dialect = detect_dialect(tmp_path)
        _validate_support(dialect.citygml, dialect.energy_ade, request_id)

        model = parse_file(tmp_path)

        building_count = len(model.get("buildings", []))
        thermal_zone_count = sum(
            len(b.get("energy", {}).get("thermalZones", []))
            for b in model.get("buildings", [])
        )
        surface_count = sum(len(b.get("surfaces", [])) for b in model.get("buildings", []))

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "parse_ok request_id=%s file=%s size_bytes=%s citygml=%s energy_ade=%s elapsed_ms=%s",
            request_id,
            filename,
            size_bytes,
            dialect.citygml,
            dialect.energy_ade,
            elapsed_ms,
        )

        return _success_payload(
            data={
                "file": filename,
                "dialect": {
                    "citygml": dialect.citygml,
                    "energyAde": dialect.energy_ade,
                },
                "model": model,
                "summary": {
                    "buildingCount": building_count,
                    "thermalZoneCount": thermal_zone_count,
                    "surfaceCount": surface_count,
                },
            },
            meta={"apiVersion": "v1", "processingMs": elapsed_ms},
        )
    except ET.ParseError:
        logger.exception("parse_xml_error request_id=%s", request_id)
        return JSONResponse(
            status_code=400,
            content=_error_payload("invalid_xml", "Could not parse XML content", request_id),
        )
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    except Exception:
        logger.exception("parse_unexpected_error request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=_error_payload("internal_error", "Unexpected server error", request_id),
        )
    finally:
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)


@app.post("/api/v1/graph-file")
async def graph_from_file(request: Request, file: UploadFile = File(...)):
    """Auto-detect CityGML version and build the graph."""
    return await _handle_graph(request, file, force_citygml=None)


@app.post("/api/v1/graph/citygml20")
async def graph_citygml20(request: Request, file: UploadFile = File(...)):
    """Force CityGML 2.0 parser regardless of detected version."""
    return await _handle_graph(request, file, force_citygml="2.0")


@app.post("/api/v1/graph/citygml30")
async def graph_citygml30(request: Request, file: UploadFile = File(...)):
    """Force CityGML 3.0 parser regardless of detected version."""
    return await _handle_graph(request, file, force_citygml="3.0")


async def _handle_graph(
    request: Request,
    file: UploadFile,
    force_citygml: str | None,
) -> JSONResponse:
    request_id = _request_id_from_headers(request)
    started    = time.perf_counter()
    tmp_path: str | None = None

    try:
        tmp_path, filename, size_bytes = await _persist_upload(file)
        dialect = detect_dialect(tmp_path)
        _validate_support(dialect.citygml, dialect.energy_ade, request_id)

        model = parse_file(tmp_path, force_citygml=force_citygml)
        graph = build_graph(model, tmp_path)

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "graph_ok request_id=%s file=%s size_bytes=%s nodes=%s edges=%s citygml=%s energy_ade=%s elapsed_ms=%s",
            request_id,
            filename,
            size_bytes,
            len(graph.get("nodes", [])),
            len(graph.get("edges", [])),
            dialect.citygml,
            dialect.energy_ade,
            elapsed_ms,
        )

        return _success_payload(
            data={
                "file": filename,
                "dialect": {
                    "citygml":   dialect.citygml,
                    "energyAde": dialect.energy_ade,
                },
                "graph":       graph,
                "typeColors":  _type_colors(),
            },
            meta={
                "apiVersion":   "v1",
                "processingMs": elapsed_ms,
                "nodeCount":    len(graph.get("nodes", [])),
                "edgeCount":    len(graph.get("edges", [])),
            },
        )
    except ET.ParseError:
        logger.exception("graph_xml_error request_id=%s", request_id)
        return JSONResponse(
            status_code=400,
            content=_error_payload("invalid_xml", "Could not parse XML content", request_id),
        )
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    except Exception:
        logger.exception("graph_unexpected_error request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=_error_payload("internal_error", "Unexpected server error", request_id),
        )
    finally:
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
