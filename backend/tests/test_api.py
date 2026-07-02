import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_index_catalog() -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    response = client.get("/api/indices")
    assert response.status_code == 200
    assert response.json()["total"] == 35


def test_ogc_process_catalog_contains_core_and_legacy_processes() -> None:
    response = client.get("/processes")
    assert response.status_code == 200
    assert len(response.json()["processes"]) == 35


def test_agent_plan_endpoint_is_safe_by_default() -> None:
    response = client.post(
        "/api/agent/plan",
        json={
            "message": "我想分析农田长势",
            "availableBands": ["blue", "green", "red", "nir"],
            "enableWebSearch": False,
        },
    )
    assert response.status_code == 200
    plan = response.json()
    assert plan["requiresConfirmation"] is True
    assert plan["status"] == "awaiting_confirmation"
    assert plan["trace"]
    assert plan["knowledgeHits"]
    assert "jobId" not in plan


def test_agent_plan_stream_returns_sse_events() -> None:
    with client.stream(
        "POST",
        "/api/agent/plan/stream",
        json={
            "message": "我想分析农田长势",
            "availableBands": ["blue", "green", "red", "nir"],
            "enableWebSearch": False,
        },
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status_code == 200
    assert "event: status" in body
    assert "event: plan" in body
    assert "event: done" in body


def test_agent_knowledge_import_enters_rag() -> None:
    imported = client.post(
        "/api/agent/knowledge",
        json={
            "title": "设施农业黄化判读",
            "content": "黄化排查优先联合GNDVI、NDRE和叶绿素相关指数，同时查看氮素管理记录。",
            "source": "pytest-upload",
        },
    )
    assert imported.status_code == 201
    response = client.post(
        "/api/agent/plan",
        json={
            "message": "设施农业黄化和氮素问题怎么判读",
            "availableBands": ["green", "red", "red_edge", "nir"],
            "enableWebSearch": False,
        },
    )
    assert response.status_code == 200
    assert any(
        hit["source"].startswith("knowledge-base")
        for hit in response.json()["knowledgeHits"]
    )


def test_agent_confirm_rejects_unapproved_execution_sheet(sample_raster: Path) -> None:
    plan_response = client.post(
        "/api/agent/plan",
        json={
            "message": "我想分析农田长势",
            "availableBands": ["blue", "green", "red", "nir"],
            "enableWebSearch": False,
        },
    )
    plan_id = plan_response.json()["id"]
    response = client.post(
        f"/api/agent/plans/{plan_id}/confirm",
        json={
            "source": {"localPath": str(sample_raster)},
            "bands": {"blue": 1, "green": 2, "red": 3, "nir": 4},
            "indices": ["ndre"],
            "engine": "numpy",
            "blockSize": 256,
            "priority": 3,
        },
    )
    assert response.status_code == 422


def test_agent_confirm_stream_submits_and_reports_job(sample_raster: Path) -> None:
    plan_response = client.post(
        "/api/agent/plan",
        json={
            "message": "我想分析农田长势",
            "availableBands": ["blue", "green", "red", "nir"],
            "enableWebSearch": False,
        },
    )
    plan_id = plan_response.json()["id"]
    with client.stream(
        "POST",
        f"/api/agent/plans/{plan_id}/confirm/stream",
        json={
            "source": {"localPath": str(sample_raster)},
            "bands": {
                "blue": 1,
                "green": 2,
                "red": 3,
                "red_edge": 0,
                "nir": 4,
                "swir1": 0,
                "swir2": 0,
            },
            "indices": ["ndvi"],
            "engine": "numpy",
            "blockSize": 128,
            "priority": 3,
        },
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status_code == 200
    assert "event: plan" in body
    assert "event: job" in body
    assert "successful" in body


def test_agent_interprets_statistics_for_showcase() -> None:
    response = client.post(
        "/api/agent/interpret-results",
        json={
            "userGoal": "我想看长势不好区域",
            "products": [
                {
                    "index": "ndvi",
                    "statistics": {
                        "mean": 0.21,
                        "standardDeviation": 0.2,
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["insights"][0]["severity"] == "danger"
    assert payload["trace"]


def execution_payload(source_path: Path, indices: list[str] | None = None) -> dict:
    return {
        "source": {"localPath": str(source_path)},
        "indices": indices or ["ndvi"],
        "bands": {"blue": 1, "green": 2, "red": 3, "nir": 4},
        "engine": "numpy",
        "blockSize": 128,
        "priority": 3,
        "statistics": True,
        "preview": True,
    }


def test_upload_asset_saves_geotiff_and_returns_metadata(sample_raster: Path) -> None:
    with sample_raster.open("rb") as file_obj:
        response = client.post(
            "/api/assets/upload",
            files={"file": ("sample.tif", file_obj, "image/tiff")},
        )
    assert response.status_code == 201
    payload = response.json()
    assert payload["filename"] == "sample.tif"
    assert payload["objectKey"].startswith("inputs/")
    assert Path(payload["localPath"]).is_file()
    assert payload["metadata"]["width"] > 0
    assert payload["metadata"]["count"] == 4
    assert payload["metadata"]["geographicBounds"] == payload["metadata"]["bounds"]
    assert len(payload["metadata"]["bandMetadata"]) == 4
    assert payload["metadata"]["bandMetadata"][0]["band"] == 1
    assert "wavelengthNm" in payload["metadata"]["bandMetadata"][0]
    assert Path(payload["previewPath"]).is_file()


def test_sync_process_executes_real_windowed_raster(sample_raster: Path) -> None:
    response = client.post(
        "/processes/ndvi/execution",
        json=execution_payload(sample_raster),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "successful"
    assert payload["outputs"]["actualEngine"] == "numpy"
    assert payload["outputs"]["products"][0]["index"] == "ndvi"
    assert Path(payload["outputs"]["products"][0]["path"]).is_file()


def test_execution_allows_unused_zero_band_mappings(sample_raster: Path) -> None:
    payload = execution_payload(sample_raster)
    payload["bands"] = {
        "blue": 1,
        "green": 2,
        "red": 3,
        "red_edge": 0,
        "nir": 4,
        "swir1": 0,
        "swir2": 0,
    }
    response = client.post("/processes/ndvi/execution", json=payload)
    assert response.status_code == 200
    assert response.json()["outputs"]["products"][0]["index"] == "ndvi"


def test_batch_process_shares_one_request_for_multiple_indices(sample_raster: Path) -> None:
    response = client.post(
        "/processes/batch/execution",
        json=execution_payload(sample_raster, ["ndvi", "evi", "gndvi"]),
    )
    assert response.status_code == 200
    products = response.json()["outputs"]["products"]
    assert [product["index"] for product in products] == ["ndvi", "evi", "gndvi"]


def test_async_process_returns_job_and_results(sample_raster: Path) -> None:
    response = client.post(
        "/processes/ndvi/execution",
        headers={"Prefer": "respond-async"},
        json=execution_payload(sample_raster),
    )
    assert response.status_code == 200
    job_id = response.json()["jobID"]

    record = {}
    for _ in range(50):
        record = client.get(f"/jobs/{job_id}").json()
        if record["status"] in {"successful", "failed"}:
            break
        time.sleep(0.02)

    assert record["status"] == "successful"
    results = client.get(f"/jobs/{job_id}/results")
    assert results.status_code == 200
    assert results.json()["products"][0]["index"] == "ndvi"


def test_execution_rejects_missing_file_and_invalid_band(sample_raster: Path) -> None:
    missing = client.post(
        "/processes/ndvi/execution",
        json=execution_payload(sample_raster.parent / "missing.tif"),
    )
    assert missing.status_code == 422

    invalid_payload = execution_payload(sample_raster)
    invalid_payload["bands"]["nir"] = 99
    invalid = client.post("/processes/ndvi/execution", json=invalid_payload)
    assert invalid.status_code == 422
    assert "波段号超出影像范围" in invalid.json()["detail"]


def test_capabilities_match_task_book_requirements() -> None:
    response = client.get("/api/system/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["indexCount"] == 35
    assert payload["totalIndexCount"] >= 35
    assert payload["customIndexStorage"] in {"memory", "postgresql"}
    assert payload["engines"] == ["numpy", "joblib", "torch"]
    assert payload["asyncJobs"] is True
    assert payload["objectStorage"] == "minio"


def test_taskbook_coverage_has_no_missing_items() -> None:
    response = client.get("/api/system/taskbook-coverage")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["missing"] == 0
    assert payload["summary"]["covered"] >= 25
