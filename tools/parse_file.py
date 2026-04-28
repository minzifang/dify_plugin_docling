from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import base64
import mimetypes
import shutil
import json
import os
import time
from http.client import RemoteDisconnected

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ParseFileTool(Tool):
    DEFAULT_CONVERT_PATH = "/v1/convert/file"
    DEFAULT_SOURCE_CONVERT_PATH = "/v1/convert/source"
    DEFAULT_ASYNC_CONVERT_PATH = "/v1/convert/file/async"

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file_obj = tool_parameters.get("file")
        output_format = str(tool_parameters.get("output_format") or "markdown").lower()
        execution_mode = str(tool_parameters.get("execution_mode") or "auto").lower()
        max_file_size_mb = float(tool_parameters.get("max_file_size_mb") or 100)
        request_timeout = self._positive_int(tool_parameters.get("request_timeout"), default=600)
        async_timeout = self._positive_int(tool_parameters.get("async_timeout"), default=7200)
        file_download_timeout = self._positive_int(tool_parameters.get("file_download_timeout"), default=120)
        requested_transport = str(tool_parameters.get("request_transport") or "auto").lower()
        poll_interval = self._positive_int(tool_parameters.get("poll_interval"), default=5)
        pdf_page_chunk_size = self._positive_int(tool_parameters.get("pdf_page_chunk_size"), default=20)
        max_output_chars = self._non_negative_int(tool_parameters.get("max_output_chars"), default=200000)
        include_raw_response = self._as_bool(tool_parameters.get("include_raw_response", False))
        api_url = str(self.runtime.credentials.get("docling_api_url") or "").strip().rstrip("/")
        api_key = str(self.runtime.credentials.get("docling_api_key") or "").strip()
        convert_path = str(self.runtime.credentials.get("docling_convert_path") or "").strip()

        if not file_obj:
            yield self.create_text_message("Error: missing required parameter `file`.")
            return
        if not api_url:
            yield self.create_text_message("Error: missing Docling API URL in plugin credentials.")
            return
        if not api_url.startswith(("http://", "https://")):
            yield self.create_text_message("Error: Docling API URL must start with http:// or https://.")
            return

        if output_format not in {"markdown", "text", "html", "json", "doctags"}:
            yield self.create_text_message(
                "Error: `output_format` must be one of markdown, text, html, json, doctags."
            )
            return
        if execution_mode not in {"auto", "async", "sync"}:
            yield self.create_text_message("Error: `execution_mode` must be auto, async, or sync.")
            return
        if requested_transport not in {"auto", "source_json", "multipart"}:
            yield self.create_text_message("Error: `request_transport` must be auto, source_json, or multipart.")
            return

        try:
            with TemporaryDirectory() as temp_dir:
                source_path, file_info = self._materialize_file(
                    file_obj=file_obj,
                    temp_dir=Path(temp_dir),
                    max_file_size_bytes=int(max_file_size_mb * 1024 * 1024),
                    file_download_timeout=file_download_timeout,
                )
                resolved_execution_mode = self._select_execution_mode(execution_mode, file_info)
                request_transport = self._select_request_transport(requested_transport, file_info)

                if self._should_segment_pdf(file_info, tool_parameters):
                    service_payload = self._call_docling_service_segmented(
                        api_url=api_url,
                        convert_path=convert_path,
                        request_transport=request_transport,
                        api_key=api_key,
                        source_path=source_path,
                        output_format=output_format,
                        max_file_size_mb=max_file_size_mb,
                        mime_type=file_info["mime_type"],
                        tool_parameters=tool_parameters,
                        request_timeout=request_timeout,
                        page_chunk_size=pdf_page_chunk_size,
                    )
                    resolved_execution_mode = "segmented"
                else:
                    service_payload = self._call_docling_service(
                        endpoints=self._resolve_docling_endpoints(
                            api_url,
                            resolved_execution_mode,
                            request_transport,
                            convert_path,
                        ),
                        api_key=api_key,
                        source_path=source_path,
                        output_format=output_format,
                        max_file_size_mb=max_file_size_mb,
                        mime_type=file_info["mime_type"],
                        tool_parameters=tool_parameters,
                        request_timeout=request_timeout,
                        async_timeout=async_timeout,
                        poll_interval=poll_interval,
                    )
                raw_text = str(service_payload.get("text") or "")
                text, content_truncated = self._truncate_text(raw_text, max_output_chars)

                payload = {
                    "output_format": output_format,
                    "execution_mode": resolved_execution_mode,
                    "requested_execution_mode": execution_mode,
                    "request_transport": request_transport,
                    "requested_request_transport": requested_transport,
                    "request_timeout": request_timeout,
                    "async_timeout": async_timeout,
                    "pdf_page_chunk_size": pdf_page_chunk_size,
                    "filename": file_info["filename"],
                    "mime_type": file_info["mime_type"],
                    "size": file_info["size"],
                    "status": service_payload.get("status"),
                    "processing_time": service_payload.get("processing_time"),
                    "content_length": len(raw_text),
                    "returned_content_length": len(text),
                    "content_truncated": content_truncated,
                    "content": text,
                    "content_preview": text[:1000],
                }
                if include_raw_response:
                    payload["service"] = service_payload

                yield self.create_json_message(payload)
                yield self.create_text_message(text)
        except Exception as exc:
            raise RuntimeError(self._format_error(exc)) from exc

    def _format_error(self, exc: Exception) -> str:
        if self._is_timeout_error(exc):
            return (
                "Docling parse failed: timed out while waiting for Docling Serve. "
                "For small Word/Office files, use execution_mode=sync or auto. "
                "For very large PDFs, use execution_mode=async and increase async_timeout, "
                "or increase Docling Serve MAX_SYNC_WAIT when using sync mode. "
                f"Original error: {exc}"
            )
        if self._is_disconnect_error(exc):
            return (
                "Docling parse failed: Docling Serve closed the connection before returning a response. "
                "This usually happens when the Docling Serve process restarts or aborts while receiving or "
                "processing a complex PDF. The plugin retried the submit request but still could not get a "
                "response. Check `docker inspect docling-serve` restart count and `docker logs docling-serve` "
                "at the same timestamp. "
                f"Original error: {exc}"
            )
        return f"Docling parse failed: {exc}"

    def _is_timeout_error(self, exc: Exception) -> bool:
        current: BaseException | None = exc
        while current is not None:
            if isinstance(current, (TimeoutError, requests.Timeout)):
                return True
            current = current.__cause__ or current.__context__
        return "timed out" in str(exc).lower()

    def _is_disconnect_error(self, exc: BaseException) -> bool:
        current: BaseException | None = exc
        while current is not None:
            if isinstance(current, (RemoteDisconnected, requests.ConnectionError)):
                text = str(current)
                if "RemoteDisconnected" in text or "Remote end closed connection without response" in text:
                    return True
            current = current.__cause__ or current.__context__
        text = str(exc)
        return "RemoteDisconnected" in text or "Remote end closed connection without response" in text

    def _call_docling_service(
        self,
        endpoints: dict[str, str],
        api_key: str,
        source_path: Path,
        output_format: str,
        max_file_size_mb: float,
        mime_type: str,
        tool_parameters: dict[str, Any],
        request_timeout: int,
        async_timeout: int,
        poll_interval: int,
    ) -> dict[str, Any]:
        headers = {}
        if api_key:
            headers["X-Api-Key"] = api_key

        docling_format = self._to_docling_format(output_format)
        options = self._build_docling_options(
            docling_format=docling_format,
            max_file_size_mb=max_file_size_mb,
            tool_parameters=tool_parameters,
        )
        convert_url = endpoints["convert_url"]
        submit_timeout = request_timeout if endpoints["mode"] == "sync" else min(120, request_timeout)
        if endpoints["transport"] == "source_json":
            response = self._post_source_json(
                convert_url=convert_url,
                headers=headers,
                source_path=source_path,
                options=options,
                timeout=submit_timeout,
            )
        else:
            response = self._post_multipart_file(
                convert_url=convert_url,
                headers=headers,
                source_path=source_path,
                mime_type=mime_type,
                options=options,
                timeout=submit_timeout,
            )

        self._raise_for_bad_response(response, convert_url)
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Docling API returned a non-object JSON response")

        if endpoints["mode"] == "async":
            payload = self._poll_docling_task(
                payload=payload,
                endpoints=endpoints,
                headers=headers,
                request_timeout=async_timeout,
                poll_interval=poll_interval,
            )

        text = self._extract_docling_text(payload, output_format)
        payload["text"] = text
        return payload

    def _call_docling_service_segmented(
        self,
        api_url: str,
        convert_path: str,
        request_transport: str,
        api_key: str,
        source_path: Path,
        output_format: str,
        max_file_size_mb: float,
        mime_type: str,
        tool_parameters: dict[str, Any],
        request_timeout: int,
        page_chunk_size: int,
    ) -> dict[str, Any]:
        page_count = self._estimate_pdf_page_count(source_path)
        if page_count <= 0:
            raise ValueError("Unable to estimate PDF page count for segmented parsing.")

        headers = {}
        if api_key:
            headers["X-Api-Key"] = api_key

        endpoints = self._resolve_docling_endpoints(api_url, "sync", request_transport, convert_path)
        chunks: list[dict[str, Any]] = []
        texts: list[str] = []
        for start in range(1, page_count + 1, page_chunk_size):
            end = min(start + page_chunk_size - 1, page_count)
            segment_parameters = {**tool_parameters, "page_range": f"{start},{end}"}
            try:
                segment_payload = self._call_docling_service(
                    endpoints=endpoints,
                    api_key=api_key,
                    source_path=source_path,
                    output_format=output_format,
                    max_file_size_mb=max_file_size_mb,
                    mime_type=mime_type,
                    tool_parameters=segment_parameters,
                    request_timeout=request_timeout,
                    async_timeout=request_timeout,
                    poll_interval=5,
                )
                segment_text = str(segment_payload.get("text") or "")
                if segment_text.strip():
                    texts.append(f"\n\n<!-- pages {start}-{end} -->\n\n{segment_text}")
                chunks.append(
                    {
                        "page_range": [start, end],
                        "status": "success",
                        "content_length": len(segment_text),
                    }
                )
            except Exception as exc:
                chunks.append(
                    {
                        "page_range": [start, end],
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                if not texts:
                    raise
                break

        text = "\n".join(texts).strip()
        return {
            "document": {"filename": source_path.name, "md_content": text},
            "status": "success" if all(item["status"] == "success" for item in chunks) else "partial_success",
            "processing_time": None,
            "segmented": True,
            "page_count": page_count,
            "page_chunk_size": page_chunk_size,
            "chunks": chunks,
            "text": text,
        }

    def _post_source_json(
        self,
        convert_url: str,
        headers: dict[str, str],
        source_path: Path,
        options: dict[str, Any],
        timeout: int,
    ) -> requests.Response:
        request_headers = {**headers, "Content-Type": "application/json", "accept": "application/json"}
        encoded = base64.b64encode(source_path.read_bytes()).decode("ascii")
        payload = {
            "options": options,
            "sources": [
                {
                    "kind": "file",
                    "base64_string": encoded,
                    "filename": source_path.name,
                }
            ],
            "target": {"kind": "inbody"},
        }
        try:
            return self._post_with_retries(
                convert_url=convert_url,
                request_kwargs={
                    "headers": request_headers,
                    "json": payload,
                    "timeout": (30, timeout),
                },
            )
        except Exception as exc:
            raise RuntimeError(
                f"{'async' if convert_url.endswith('/async') else 'sync'} Docling source_json request failed before response. "
                f"url={convert_url}, timeout={timeout}s, file={source_path.name}, "
                f"size={source_path.stat().st_size}, original={exc}"
            ) from exc

    def _post_multipart_file(
        self,
        convert_url: str,
        headers: dict[str, str],
        source_path: Path,
        mime_type: str,
        options: dict[str, Any],
        timeout: int,
    ) -> requests.Response:
        data = self._options_to_form_data(options)
        data.append(("target_type", "inbody"))
        try:
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    with source_path.open("rb") as file_handle:
                        return requests.post(
                            convert_url,
                            headers=headers,
                            files=[("files", (source_path.name, file_handle, mime_type or "application/octet-stream"))],
                            data=data,
                            timeout=(30, timeout),
                        )
                except Exception as exc:
                    last_exc = exc
                    if not self._should_retry_submit_error(exc, attempt):
                        raise
                    time.sleep(2 + attempt * 3)
                    self._wait_for_docling_http(convert_url, headers)
            if last_exc:
                raise last_exc
            raise RuntimeError("multipart submit failed without an exception")
        except Exception as exc:
            raise RuntimeError(
                f"{'async' if convert_url.endswith('/async') else 'sync'} Docling multipart request failed before response. "
                f"url={convert_url}, timeout={timeout}s, file={source_path.name}, "
                f"size={source_path.stat().st_size}, original={exc}"
            ) from exc

    def _post_with_retries(self, convert_url: str, request_kwargs: dict[str, Any]) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                return requests.post(convert_url, **request_kwargs)
            except Exception as exc:
                last_exc = exc
                if not self._should_retry_submit_error(exc, attempt):
                    raise
                time.sleep(2 + attempt * 3)
                headers = request_kwargs.get("headers")
                self._wait_for_docling_http(convert_url, headers if isinstance(headers, dict) else {})
        if last_exc:
            raise last_exc
        raise RuntimeError("submit failed without an exception")

    def _should_retry_submit_error(self, exc: Exception, attempt: int) -> bool:
        if attempt >= 2:
            return False
        return self._is_disconnect_error(exc) or isinstance(exc, requests.ConnectionError)

    def _wait_for_docling_http(self, convert_url: str, headers: dict[str, str]) -> None:
        root_url = self._resolve_api_root(convert_url)
        for _ in range(12):
            try:
                response = requests.get(self._join_api_url(root_url, "/docs"), headers=headers, timeout=(5, 10))
                if response.status_code < 500:
                    return
            except Exception:
                pass
            time.sleep(5)

    def _resolve_docling_endpoints(
        self,
        api_url: str,
        execution_mode: str,
        request_transport: str,
        convert_path: str = "",
    ) -> dict[str, str]:
        custom_convert_url = self._resolve_custom_convert_url(api_url, convert_path)
        if execution_mode == "sync":
            return {
                "mode": "sync",
                "transport": request_transport,
                "convert_url": custom_convert_url
                or (self._resolve_source_convert_url(api_url)
                if request_transport == "source_json"
                else self._resolve_convert_url(api_url)),
            }

        if custom_convert_url:
            raise ValueError(
                "Async mode cannot infer status/result endpoints from a custom conversion path. "
                "Set execution_mode=sync, or use a Docling Serve base URL with the official async API."
            )

        api_root = self._resolve_api_root(api_url)
        async_convert_url = (
            self._join_api_url(api_root, "/v1/convert/source/async")
            if request_transport == "source_json"
            else self._resolve_async_convert_url(api_url)
        )
        return {
            "mode": "async",
            "transport": request_transport,
            "convert_url": async_convert_url,
            "status_poll_url": self._join_api_url(api_root, "/v1/status/poll/{task_id}"),
            "result_url": self._join_api_url(api_root, "/v1/result/{task_id}"),
        }

    def _resolve_custom_convert_url(self, api_url: str, convert_path: str) -> str | None:
        if not convert_path:
            return None
        if convert_path.startswith(("http://", "https://")):
            return convert_path.rstrip("/")
        if convert_path == "/":
            return api_url.rstrip("/") + "/"
        return self._join_api_url(api_url, convert_path)

    def _resolve_convert_url(self, api_url: str) -> str:
        parsed = urlparse(api_url)
        if parsed.path and parsed.path != "/":
            return api_url
        return self._join_api_url(api_url, self.DEFAULT_CONVERT_PATH)

    def _resolve_source_convert_url(self, api_url: str) -> str:
        parsed = urlparse(api_url)
        normalized_path = parsed.path.rstrip("/")
        if not normalized_path:
            return self._join_api_url(api_url, self.DEFAULT_SOURCE_CONVERT_PATH)
        if normalized_path.endswith("/source"):
            return api_url
        if normalized_path.endswith("/file"):
            return parsed._replace(path=normalized_path[: -len("/file")] + "/source").geturl()
        if normalized_path.endswith("/file/async"):
            return parsed._replace(path=normalized_path[: -len("/file/async")] + "/source").geturl()
        return api_url

    def _resolve_async_convert_url(self, api_url: str) -> str:
        parsed = urlparse(api_url)
        normalized_path = parsed.path.rstrip("/")
        if not normalized_path:
            return self._join_api_url(api_url, self.DEFAULT_ASYNC_CONVERT_PATH)
        if normalized_path.endswith("/async"):
            return api_url
        if normalized_path.endswith(self.DEFAULT_CONVERT_PATH):
            return api_url.rstrip("/") + "/async"
        if "/v1/convert/" in normalized_path:
            return api_url.rstrip("/") + "/async"
        raise ValueError(
            "Async mode requires a Docling base URL or an official Docling convert URL. "
            "For custom gateways, set execution_mode=sync or expose /v1/convert/file/async."
        )

    def _resolve_api_root(self, api_url: str) -> str:
        parsed = urlparse(api_url)
        path = parsed.path.rstrip("/")
        if "/v1/" in path:
            root_path = path.split("/v1/", 1)[0]
        elif path.endswith("/v1"):
            root_path = path[:-3]
        else:
            root_path = ""
        return parsed._replace(path=root_path, params="", query="", fragment="").geturl().rstrip("/")

    def _select_execution_mode(self, requested_mode: str, file_info: dict[str, Any]) -> str:
        if requested_mode in {"sync", "async"}:
            return requested_mode
        filename = str(file_info.get("filename") or "").lower()
        mime_type = str(file_info.get("mime_type") or "").lower()
        size = int(file_info.get("size") or 0)
        is_pdf = Path(filename).suffix == ".pdf" or mime_type == "application/pdf"
        if is_pdf and size >= 2 * 1024 * 1024:
            return "async"
        return "sync"

    def _select_request_transport(self, requested_transport: str, file_info: dict[str, Any]) -> str:
        if requested_transport in {"source_json", "multipart"}:
            return requested_transport

        filename = str(file_info.get("filename") or "").lower()
        mime_type = str(file_info.get("mime_type") or "").lower()
        size = int(file_info.get("size") or 0)
        is_pdf = Path(filename).suffix == ".pdf" or mime_type == "application/pdf"
        if is_pdf:
            if size <= 20 * 1024 * 1024:
                return "source_json"
            return "multipart"
        return "multipart"

    def _should_segment_pdf(self, file_info: dict[str, Any], tool_parameters: dict[str, Any]) -> bool:
        if str(tool_parameters.get("page_range") or "").strip():
            return False
        mode = str(tool_parameters.get("execution_mode") or "auto").lower()
        if mode not in {"auto", "segmented"}:
            return False
        filename = str(file_info.get("filename") or "").lower()
        mime_type = str(file_info.get("mime_type") or "").lower()
        size = int(file_info.get("size") or 0)
        is_pdf = Path(filename).suffix == ".pdf" or mime_type == "application/pdf"
        return is_pdf and size >= 2 * 1024 * 1024

    def _estimate_pdf_page_count(self, source_path: Path) -> int:
        data = source_path.read_bytes()
        # Good enough for routing large PDFs without adding a heavy PDF dependency to the plugin.
        return len(list(__import__("re").finditer(rb"/Type\s*/Page(?!s)\b", data)))

    def _join_api_url(self, base_url: str, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        path = path or self.DEFAULT_CONVERT_PATH
        if not path.startswith("/"):
            path = "/" + path
        return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))

    def _raise_for_bad_response(self, response: requests.Response, convert_url: str) -> None:
        if response.status_code < 400:
            return

        body = response.text.strip()
        if len(body) > 500:
            body = body[:500] + "..."

        if response.status_code == 504:
            raise ValueError(
                "Docling API returned 504 Gateway Timeout. "
                "The plugin reached the configured service, but the gateway or reverse proxy "
                "timed out while waiting for Docling to finish parsing. "
                "Increase timeout settings on the Docling Serve gateway/proxy, allocate more "
                "CPU/GPU/memory to Docling, or reduce parsing cost by limiting `page_range`, "
                "disabling OCR when it is not needed, using `table_mode=fast`, or increasing "
                "`document_timeout` if the service supports it. "
                f"url={convert_url}"
            )

        if response.status_code in {502, 503}:
            raise ValueError(
                f"Docling API returned HTTP {response.status_code}. "
                "The configured URL is reachable, but the upstream Docling service may be "
                "unavailable, overloaded, restarting, or rejected by its gateway. "
                f"url={convert_url}"
                + (f", response={body}" if body else "")
            )

        raise ValueError(
            f"Docling API returned HTTP {response.status_code} for {convert_url}"
            + (f": {body}" if body else "")
        )

    def _poll_docling_task(
        self,
        payload: dict[str, Any],
        endpoints: dict[str, str],
        headers: dict[str, str],
        request_timeout: int,
        poll_interval: int,
    ) -> dict[str, Any]:
        task_id = self._extract_task_id(payload)
        if not task_id:
            raise ValueError(
                f"Docling async API did not return a task id. response={self._short_json(payload)}"
            )

        deadline = time.monotonic() + request_timeout
        last_status: dict[str, Any] = payload
        while time.monotonic() < deadline:
            status_url = endpoints["status_poll_url"].format(task_id=task_id)
            try:
                response = requests.get(
                    status_url,
                    headers=headers,
                    params={"wait": min(poll_interval, 10)},
                    timeout=(10, max(15, poll_interval + 10)),
                )
            except (requests.Timeout, TimeoutError) as exc:
                last_status = {
                    "task_id": task_id,
                    "task_status": "poll_timeout_retrying",
                    "detail": str(exc),
                }
                time.sleep(min(poll_interval, max(1, int(deadline - time.monotonic()))))
                continue
            if response.status_code == 404:
                last_status = {"task_id": task_id, "task_status": "not_found_retrying"}
                time.sleep(min(poll_interval, max(1, int(deadline - time.monotonic()))))
                continue
            self._raise_for_bad_response(response, status_url)
            last_status = response.json()
            if not isinstance(last_status, dict):
                raise ValueError("Docling async status API returned a non-object JSON response")

            status = str(
                last_status.get("task_status")
                or last_status.get("status")
                or last_status.get("state")
                or ""
            ).lower()
            if status in {"success", "succeeded", "completed", "complete", "done"}:
                result_url = endpoints["result_url"].format(task_id=task_id)
                while time.monotonic() < deadline:
                    remaining = max(1, int(deadline - time.monotonic()))
                    result_response = requests.get(
                        result_url,
                        headers=headers,
                        timeout=(10, max(60, remaining)),
                    )
                    if result_response.status_code == 404:
                        time.sleep(min(poll_interval, max(1, int(deadline - time.monotonic()))))
                        continue
                    self._raise_for_bad_response(result_response, result_url)
                    result_payload = result_response.json()
                    if not isinstance(result_payload, dict):
                        raise ValueError("Docling async result API returned a non-object JSON response")
                    return result_payload
                raise TimeoutError(
                    f"Docling async result was not available within request_timeout={request_timeout}s. "
                    f"task_id={task_id}"
                )
            if status in {"failure", "failed", "error", "revoked", "cancelled", "canceled"}:
                raise ValueError(f"Docling async task failed: {self._short_json(last_status)}")

            time.sleep(min(poll_interval, max(1, int(deadline - time.monotonic()))))

        raise TimeoutError(
            f"Docling async task did not finish within request_timeout={request_timeout}s. "
            f"task_id={task_id}, last_status={self._short_json(last_status)}"
        )

    def _extract_task_id(self, payload: dict[str, Any]) -> str | None:
        for name in ("task_id", "taskId", "id"):
            value = payload.get(name)
            if value:
                return str(value)
        task = payload.get("task")
        if isinstance(task, dict):
            for name in ("task_id", "taskId", "id"):
                value = task.get(name)
                if value:
                    return str(value)
        return None

    def _short_json(self, value: Any) -> str:
        text = json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= 500 else text[:500] + "..."

    def _build_docling_options(
        self,
        docling_format: str,
        max_file_size_mb: float,
        tool_parameters: dict[str, Any],
    ) -> dict[str, Any]:
        send_advanced_options = self._as_bool(tool_parameters.get("send_advanced_options", False))

        options: dict[str, Any] = {
            "from_formats": [self._guess_docling_input_format(tool_parameters)],
            "to_formats": [docling_format],
            "image_export_mode": "placeholder",
            "do_ocr": False,
            "do_table_structure": not self._is_pdf_file(tool_parameters),
            "include_images": False,
        }

        document_timeout = tool_parameters.get("document_timeout")
        if document_timeout not in (None, ""):
            options["document_timeout"] = self._positive_int(document_timeout, default=1)

        if send_advanced_options:
            options.update(
                {
                    "do_ocr": self._as_bool(tool_parameters.get("do_ocr", False)),
                    "force_ocr": self._as_bool(tool_parameters.get("force_ocr", False)),
                    "do_table_structure": self._as_bool(tool_parameters.get("do_table_structure", True)),
                    "include_images": self._as_bool(tool_parameters.get("include_images", False)),
                }
            )

            for name in ("image_export_mode", "pdf_backend", "table_mode", "pipeline"):
                value = tool_parameters.get(name)
                if value not in (None, "", "auto"):
                    options[name] = str(value)

            ocr_lang = str(tool_parameters.get("ocr_lang") or "").strip()
            if ocr_lang:
                options["ocr_lang"] = [item.strip() for item in ocr_lang.split(",") if item.strip()]

        page_range = str(tool_parameters.get("page_range") or "").strip()
        if page_range:
            parts = [item.strip() for item in page_range.replace("-", ",").split(",") if item.strip()]
            if len(parts) != 2 or not all(item.isdigit() for item in parts):
                raise ValueError("`page_range` must look like `1,3` or `1-3`.")
            options["page_range"] = [int(parts[0]), int(parts[1])]

        return options

    def _options_to_form_data(self, options: dict[str, Any]) -> list[tuple[str, str]]:
        data: list[tuple[str, str]] = []
        for key, value in options.items():
            if isinstance(value, list):
                for item in value:
                    data.append((key, self._form_value(item)))
            else:
                data.append((key, self._form_value(value)))
        return data

    def _form_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _to_docling_format(self, output_format: str) -> str:
        return {
            "markdown": "md",
            "text": "text",
            "html": "html",
            "json": "json",
            "doctags": "doctags",
        }[output_format]

    def _guess_docling_input_format(self, tool_parameters: dict[str, Any]) -> str:
        file_obj = tool_parameters.get("file")
        filename = (
            self._get_file_attr(file_obj, "filename")
            or self._get_file_attr(file_obj, "name")
            or ""
        )
        mime_type = (
            self._get_file_attr(file_obj, "mime_type")
            or self._get_file_attr(file_obj, "mimetype")
            or ""
        )
        ext = Path(str(filename).lower()).suffix
        if ext:
            return {
                ".docx": "docx",
                ".pptx": "pptx",
                ".pdf": "pdf",
                ".html": "html",
                ".htm": "html",
                ".md": "md",
                ".csv": "csv",
                ".xlsx": "xlsx",
                ".json": "json_docling",
                ".txt": "md",
            }.get(ext, "docx")
        if mime_type == "application/pdf":
            return "pdf"
        if "spreadsheet" in mime_type:
            return "xlsx"
        if "presentation" in mime_type:
            return "pptx"
        return "docx"

    def _is_pdf_file(self, tool_parameters: dict[str, Any]) -> bool:
        file_obj = tool_parameters.get("file")
        filename = (
            self._get_file_attr(file_obj, "filename")
            or self._get_file_attr(file_obj, "name")
            or ""
        )
        mime_type = (
            self._get_file_attr(file_obj, "mime_type")
            or self._get_file_attr(file_obj, "mimetype")
            or ""
        )
        return Path(str(filename).lower()).suffix == ".pdf" or str(mime_type).lower() == "application/pdf"

    def _extract_docling_text(self, payload: dict[str, Any], output_format: str) -> str:
        document = payload.get("document")
        if not isinstance(document, dict):
            raise ValueError("Docling Serve response must contain `document`")

        preferred_field = {
            "markdown": "md_content",
            "text": "text_content",
            "html": "html_content",
            "json": "json_content",
            "doctags": "doctags_content",
        }[output_format]

        content = self._first_non_empty_docling_content(
            document,
            [
                preferred_field,
                "md_content",
                "markdown_content",
                "text_content",
                "content",
                "markdown",
                "text",
                "html_content",
                "doctags_content",
                "json_content",
            ],
        )
        if content is None:
            errors = payload.get("errors") or []
            raise ValueError(
                f"Docling Serve response did not include usable converted content. "
                f"status={payload.get('status')}, errors={errors}"
            )
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False, default=str)

    def _first_non_empty_docling_content(self, document: dict[str, Any], names: list[str]) -> Any:
        seen = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            value = document.get(name)
            if self._is_usable_content(value):
                return value
        return None

    def _is_usable_content(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            stripped = value.strip()
            return stripped not in {"", "{}", "[]", "null"}
        if isinstance(value, (dict, list)):
            return bool(value)
        return True

    def _materialize_file(
        self,
        file_obj: Any,
        temp_dir: Path,
        max_file_size_bytes: int,
        file_download_timeout: int,
    ) -> tuple[Path, dict[str, Any]]:
        filename = self._get_file_attr(file_obj, "filename") or self._get_file_attr(file_obj, "name")
        mime_type = self._get_file_attr(file_obj, "mime_type") or self._get_file_attr(file_obj, "mimetype")
        path = self._get_file_attr(file_obj, "path")
        url = self._get_file_attr(file_obj, "url") or self._get_file_attr(file_obj, "remote_url")

        if path:
            source_path = Path(str(path))
            if not filename:
                filename = source_path.name
            if not mime_type:
                mime_type = mimetypes.guess_type(filename or source_path.name)[0]
            size = source_path.stat().st_size
            self._validate_size(size, max_file_size_bytes)
            copied_path = temp_dir / self._safe_filename(filename or source_path.name)
            shutil.copyfile(source_path, copied_path)
            return copied_path, self._file_info(filename, mime_type, size)

        if url:
            url = self._normalize_file_url(str(url))
            inferred_name = filename or self._filename_from_url(str(url)) or "document"
            safe_name = self._safe_filename(inferred_name)
            target_path = temp_dir / safe_name
            request = Request(str(url), headers={"User-Agent": "dify-docling-plugin/0.1.20"})
            try:
                with urlopen(request, timeout=file_download_timeout) as response:
                    data = response.read(max_file_size_bytes + 1)
                    response_mime = response.headers.get_content_type()
            except Exception as exc:
                raise RuntimeError(
                    f"failed to download Dify file before sending it to Docling. "
                    f"timeout={file_download_timeout}s, url={self._safe_url_for_error(str(url))}"
                ) from exc

            self._validate_size(len(data), max_file_size_bytes)
            target_path.write_bytes(data)
            return target_path, self._file_info(
                inferred_name,
                mime_type or response_mime,
                len(data),
            )

        blob = (
            self._get_file_attr(file_obj, "blob")
            or self._get_file_attr(file_obj, "content")
            or self._get_file_attr(file_obj, "data")
        )
        if blob is not None:
            data = blob if isinstance(blob, bytes) else bytes(str(blob), "utf-8")
            self._validate_size(len(data), max_file_size_bytes)
            safe_name = self._safe_filename(filename or "document")
            target_path = temp_dir / safe_name
            target_path.write_bytes(data)
            return target_path, self._file_info(filename or safe_name, mime_type, len(data))

        raise ValueError("unsupported Dify file object: expected `url`, `path`, or binary content")

    def _get_file_attr(self, file_obj: Any, name: str) -> Any:
        if isinstance(file_obj, dict):
            return file_obj.get(name)

        if hasattr(file_obj, "model_dump"):
            try:
                dumped = file_obj.model_dump(mode="python")
            except TypeError:
                dumped = file_obj.model_dump()
            except Exception:
                dumped = None
            if isinstance(dumped, dict) and name in dumped:
                return dumped.get(name)

        raw_attrs = getattr(file_obj, "__dict__", None)
        if isinstance(raw_attrs, dict) and name in raw_attrs:
            return raw_attrs.get(name)

        try:
            return getattr(file_obj, name, None)
        except Exception:
            return None

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "off"}
        return bool(value)

    def _bool_text(self, value: Any) -> str:
        return "true" if self._as_bool(value) else "false"

    def _positive_int(self, value: Any, default: int) -> int:
        if value in (None, ""):
            return default
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return default
        return max(1, number)

    def _non_negative_int(self, value: Any, default: int) -> int:
        if value in (None, ""):
            return default
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return default
        return max(0, number)

    def _truncate_text(self, text: str, max_chars: int) -> tuple[str, bool]:
        if max_chars == 0 or len(text) <= max_chars:
            return text, False
        suffix = (
            "\n\n[Content truncated by Dify Docling Plugin. "
            "Increase `max_output_chars` or set it to 0 to return the full content.]"
        )
        keep = max(0, max_chars - len(suffix))
        return text[:keep] + suffix, True

    def _normalize_file_url(self, url: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        if not url.startswith("/"):
            raise ValueError(
                "Dify file URL is not an absolute URL or root-relative path. "
                "Please pass a valid Dify file variable."
            )

        base_url = (
            os.getenv("FILES_URL")
            or os.getenv("DIFY_INNER_API_URL")
            or os.getenv("PLUGIN_DIFY_INNER_API_URL")
            or "http://api:5001"
        )
        return urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))

    def _validate_size(self, size: int, max_file_size_bytes: int) -> None:
        if size > max_file_size_bytes:
            raise ValueError(
                f"file is too large: {size} bytes exceeds {max_file_size_bytes} bytes"
            )

    def _file_info(self, filename: str | None, mime_type: str | None, size: int) -> dict[str, Any]:
        guessed_mime = mimetypes.guess_type(filename or "")[0]
        return {
            "filename": filename or "document",
            "mime_type": mime_type or guessed_mime or "application/octet-stream",
            "size": size,
        }

    def _filename_from_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        name = Path(unquote(parsed.path)).name
        return name or None

    def _safe_filename(self, filename: str) -> str:
        candidate = Path(filename).name.strip() or "document"
        return candidate.replace("/", "_").replace("\\", "_")

    def _safe_url_for_error(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path
        return f"{parsed.scheme}://{parsed.netloc}{path}"
