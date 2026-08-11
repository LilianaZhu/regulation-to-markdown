from __future__ import annotations

import os
import re
import time
import zipfile
from pathlib import Path
from typing import Any, Self

import httpx

from .models import MinerUResult, PageBatch

MINERU_API_BASE = "https://mineru.net/api/v4"
TERMINAL_STATES = {"done", "failed"}
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ZIP_MEMBERS = 20_000
MAX_COMPRESSION_RATIO = 1_000


class MinerUError(RuntimeError):
    pass


def _redact_url_queries(message: object) -> str:
    return re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?<redacted>", str(message))


class MinerUClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = MINERU_API_BASE,
        timeout_seconds: float = 60,
        max_retries: int = 3,
    ):
        self._token = token or os.environ.get("MINERU_API_TOKEN", "")
        if not self._token:
            raise MinerUError(
                "MINERU_API_TOKEN is required. Configure it in Cursor plugin variables."
            )
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            headers={"Authorization": f"Bearer {self._token}"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(method, url, **kwargs)
                if (
                    response.status_code == 429 or response.status_code >= 500
                ) and attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    time.sleep(min(delay, 30))
                    continue
                response.raise_for_status()
                return response
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 30))
        raise MinerUError(
            f"MinerU request failed after retries: {_redact_url_queries(last_error)}"
        )

    @staticmethod
    def _data(response: httpx.Response) -> dict[str, Any]:
        payload = response.json()
        if payload.get("code") != 0:
            raise MinerUError(
                f"MinerU API error {payload.get('code')}: {payload.get('msg', 'unknown')}"
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MinerUError("MinerU response does not contain a data object")
        return data

    def submit_files(
        self,
        batches: list[PageBatch],
        *,
        model_version: str = "vlm",
        language: str = "latin",
        is_ocr: bool = False,
        enable_table: bool = True,
        enable_formula: bool = True,
    ) -> str:
        if not batches:
            raise MinerUError("No batches to submit")
        if len(batches) > 50:
            raise MinerUError(
                "MinerU accepts at most 50 signed upload URLs per request"
            )

        files: list[dict[str, Any]] = []
        paths: list[Path] = []
        for batch in batches:
            if not batch.file_path:
                raise MinerUError(f"Batch {batch.index} has no split file path")
            path = Path(batch.file_path).resolve()
            if not path.is_file():
                raise MinerUError(f"Batch file does not exist: {path}")
            paths.append(path)
            files.append(
                {
                    "name": path.name,
                    "data_id": batch.data_id or f"batch-{batch.index:03d}",
                    "is_ocr": is_ocr,
                }
            )

        response = self._request(
            "POST",
            f"{self.base_url}/file-urls/batch",
            json={
                "files": files,
                "model_version": model_version,
                "language": language,
                "enable_table": enable_table,
                "enable_formula": enable_formula,
            },
        )
        data = self._data(response)
        batch_id = str(data.get("batch_id", ""))
        upload_urls = data.get("file_urls")
        if not batch_id or not isinstance(upload_urls, list):
            raise MinerUError("MinerU did not return batch_id and file_urls")
        if len(upload_urls) != len(paths):
            raise MinerUError(
                f"MinerU returned {len(upload_urls)} URLs for {len(paths)} files"
            )

        upload_client = httpx.Client(timeout=httpx.Timeout(300), follow_redirects=True)
        try:
            for path, upload_url in zip(paths, upload_urls, strict=True):
                with path.open("rb") as handle:
                    upload = upload_client.put(
                        str(upload_url),
                        content=handle,
                        headers={"Content-Length": str(path.stat().st_size)},
                    )
                    upload.raise_for_status()
        except httpx.HTTPError as exc:
            raise MinerUError(
                f"MinerU signed upload failed: {_redact_url_queries(exc)}"
            ) from exc
        finally:
            upload_client.close()
        return batch_id

    def batch_status(self, batch_id: str) -> list[MinerUResult]:
        response = self._request(
            "GET",
            f"{self.base_url}/extract-results/batch/{batch_id}",
        )
        data = self._data(response)
        results = data.get("extract_result", [])
        if not isinstance(results, list):
            raise MinerUError("MinerU batch response has invalid extract_result")
        return [MinerUResult.model_validate(item) for item in results]

    def wait_for_batch(
        self,
        batch_id: str,
        *,
        poll_interval_seconds: float = 5,
        timeout_seconds: float = 60 * 60,
    ) -> list[MinerUResult]:
        started = time.monotonic()
        while True:
            results = self.batch_status(batch_id)
            if results and all(result.state in TERMINAL_STATES for result in results):
                failed = [result for result in results if result.state == "failed"]
                if failed:
                    details = "; ".join(
                        f"{item.file_name}: {item.err_msg or 'unknown error'}"
                        for item in failed
                    )
                    raise MinerUError(f"MinerU batch contains failed files: {details}")
                return results
            if time.monotonic() - started > timeout_seconds:
                raise MinerUError(
                    f"Timed out waiting for MinerU batch {batch_id}; "
                    "the job can be resumed later with mineru_batch_status"
                )
            time.sleep(poll_interval_seconds)

    @staticmethod
    def _safe_extract(archive: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        destination_root = destination.resolve()
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > MAX_ZIP_MEMBERS:
                raise MinerUError(f"MinerU ZIP has too many files: {len(members)}")
            extracted_bytes = sum(member.file_size for member in members)
            if extracted_bytes > MAX_EXTRACTED_BYTES:
                raise MinerUError(
                    f"MinerU ZIP expands beyond {MAX_EXTRACTED_BYTES} bytes"
                )
            for member in members:
                target = (destination / member.filename).resolve()
                if (
                    destination_root not in target.parents
                    and target != destination_root
                ):
                    raise MinerUError(f"Unsafe path in MinerU ZIP: {member.filename}")
                if (
                    member.file_size
                    and member.compress_size
                    and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO
                ):
                    raise MinerUError(
                        f"Suspicious compression ratio in MinerU ZIP: {member.filename}"
                    )
            bundle.extractall(destination)

    def download_results(
        self,
        results: list[MinerUResult],
        output_dir: str | Path,
    ) -> list[dict[str, str | None]]:
        destination = Path(output_dir).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        extracted: list[dict[str, str | None]] = []
        download_client = httpx.Client(
            timeout=httpx.Timeout(300),
            follow_redirects=True,
        )
        try:
            for index, result in enumerate(results, start=1):
                if result.state != "done" or not result.full_zip_url:
                    raise MinerUError(f"Result is not downloadable: {result.file_name}")
                archive = destination / f"{index:03d}-{Path(result.file_name).stem}.zip"
                downloaded = 0
                try:
                    with download_client.stream("GET", result.full_zip_url) as response:
                        response.raise_for_status()
                        content_length = response.headers.get("Content-Length")
                        if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                            raise MinerUError(
                                f"MinerU download exceeds {MAX_DOWNLOAD_BYTES} bytes"
                            )
                        with archive.open("wb") as handle:
                            for chunk in response.iter_bytes():
                                downloaded += len(chunk)
                                if downloaded > MAX_DOWNLOAD_BYTES:
                                    raise MinerUError(
                                        "MinerU download exceeded "
                                        f"{MAX_DOWNLOAD_BYTES} bytes"
                                    )
                                handle.write(chunk)
                except Exception:
                    archive.unlink(missing_ok=True)
                    raise
                result_dir = destination / (
                    f"{index:03d}-{Path(result.file_name).stem}"
                )
                self._safe_extract(archive, result_dir)
                extracted.append(
                    {
                        "data_id": result.data_id,
                        "file_name": result.file_name,
                        "result_dir": str(result_dir),
                        "archive_path": str(archive),
                    }
                )
        except httpx.HTTPError as exc:
            raise MinerUError(
                f"MinerU result download failed: {_redact_url_queries(exc)}"
            ) from exc
        finally:
            download_client.close()
        return extracted
