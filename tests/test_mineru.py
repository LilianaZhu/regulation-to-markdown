from __future__ import annotations

import io
import zipfile

import httpx
import pytest
import respx

from regulation_to_markdown import mineru
from regulation_to_markdown.mcp_server import _match_results_to_batches
from regulation_to_markdown.mineru import MinerUClient, MinerUError
from regulation_to_markdown.models import MinerUResult, PageBatch


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("full.md", "# Parsed\n")
        archive.writestr(
            "demo_content_list.json",
            '[{"type":"text","text":"Parsed","page_idx":0}]',
        )
    return buffer.getvalue()


@respx.mock
def test_mineru_signed_upload_status_and_download(tmp_path):
    pdf = tmp_path / "batch.pdf"
    pdf.write_bytes(b"%PDF-test")
    base = "https://mineru.test/api/v4"
    respx.post(f"{base}/file-urls/batch").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "batch_id": "batch-123",
                    "file_urls": ["https://upload.test/one"],
                },
                "msg": "ok",
            },
        )
    )
    upload_route = respx.put("https://upload.test/one").mock(
        return_value=httpx.Response(200)
    )
    respx.get(f"{base}/extract-results/batch/batch-123").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "batch_id": "batch-123",
                    "extract_result": [
                        {
                            "file_name": "batch.pdf",
                            "state": "done",
                            "data_id": "doc-batch-1",
                            "full_zip_url": "https://download.test/result.zip",
                            "err_msg": "",
                        }
                    ],
                },
                "msg": "ok",
            },
        )
    )
    download_route = respx.get("https://download.test/result.zip").mock(
        return_value=httpx.Response(200, content=_zip_bytes())
    )

    batch = PageBatch(
        index=1,
        start_page=1,
        end_page=1,
        file_path=str(pdf),
        data_id="doc-batch-1",
    )
    with MinerUClient(token="secret", base_url=base) as client:
        batch_id = client.submit_files([batch])
        results = client.batch_status(batch_id)
        downloaded = client.download_results(results, tmp_path / "raw")

    assert batch_id == "batch-123"
    assert results[0].state == "done"
    assert (tmp_path / "raw" / "001-batch" / "full.md").is_file()
    assert len(downloaded) == 1
    assert downloaded[0]["data_id"] == "doc-batch-1"
    assert downloaded[0]["result_dir"].endswith("001-batch")
    assert "authorization" not in upload_route.calls.last.request.headers
    assert "content-type" not in upload_route.calls.last.request.headers
    assert "authorization" not in download_route.calls.last.request.headers


@respx.mock
def test_mineru_download_enforces_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(mineru, "MAX_DOWNLOAD_BYTES", 3)
    respx.get("https://download.test/large.zip").mock(
        return_value=httpx.Response(200, content=b"1234")
    )
    result = mineru.MinerUResult(
        file_name="large.pdf",
        state="done",
        full_zip_url="https://download.test/large.zip",
    )

    with (
        MinerUClient(token="secret") as client,
        pytest.raises(MinerUError, match="exceeds"),
    ):
        client.download_results([result], tmp_path / "raw")

    assert not (tmp_path / "raw" / "001-large.zip").exists()


def test_mineru_redacts_signed_url_query():
    message = mineru._redact_url_queries(
        "PUT https://upload.test/file?signature=top-secret&expires=1 failed"
    )

    assert "top-secret" not in message
    assert "https://upload.test/file?<redacted>" in message


def test_mineru_results_are_matched_by_data_id_not_response_order(tmp_path):
    batches = [
        PageBatch(
            index=1,
            start_page=1,
            end_page=1,
            file_path=str(tmp_path / "one.pdf"),
            data_id="one",
        ),
        PageBatch(
            index=2,
            start_page=2,
            end_page=2,
            file_path=str(tmp_path / "two.pdf"),
            data_id="two",
        ),
    ]
    results = [
        MinerUResult(file_name="two.pdf", state="done", data_id="two"),
        MinerUResult(file_name="one.pdf", state="done", data_id="one"),
    ]

    matched = _match_results_to_batches(results, batches)

    assert [result.data_id for result in matched] == ["one", "two"]
