from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import mimetypes
import shutil
import json
import os

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ParseFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file_obj = tool_parameters.get("file")
        output_format = str(tool_parameters.get("output_format") or "markdown").lower()
        max_file_size_mb = float(tool_parameters.get("max_file_size_mb") or 100)
        base_url = str(self.runtime.credentials.get("docling_api_url") or "").strip().rstrip("/")
        api_key = str(self.runtime.credentials.get("docling_api_key") or "").strip()
        convert_path = str(self.runtime.credentials.get("docling_convert_path") or "/v1/convert/file").strip()

        if not file_obj:
            yield self.create_text_message("Error: missing required parameter `file`.")
            return
        if not base_url:
            yield self.create_text_message("Error: missing Docling API URL in plugin credentials.")
            return
        if not base_url.startswith(("http://", "https://")):
            yield self.create_text_message("Error: Docling API URL must start with http:// or https://.")
            return

        if output_format not in {"markdown", "text", "html", "json", "doctags"}:
            yield self.create_text_message(
                "Error: `output_format` must be one of markdown, text, html, json, doctags."
            )
            return

        try:
            with TemporaryDirectory() as temp_dir:
                source_path, file_info = self._materialize_file(
                    file_obj=file_obj,
                    temp_dir=Path(temp_dir),
                    max_file_size_bytes=int(max_file_size_mb * 1024 * 1024),
                )

                service_payload = self._call_docling_service(
                    base_url=base_url,
                    api_key=api_key,
                    source_path=source_path,
                    output_format=output_format,
                    max_file_size_mb=max_file_size_mb,
                    tool_parameters=tool_parameters,
                    convert_path=convert_path,
                )
                text = str(service_payload.get("text") or "")

                payload = {
                    "content": text,
                    "output_format": output_format,
                    "filename": file_info["filename"],
                    "mime_type": file_info["mime_type"],
                    "size": file_info["size"],
                    "status": service_payload.get("status"),
                    "processing_time": service_payload.get("processing_time"),
                    "service": service_payload,
                }

                yield self.create_json_message(payload)
                yield self.create_variable_message("content", text)
                yield self.create_text_message(text)
        except Exception as exc:
            yield self.create_text_message(f"Docling parse failed: {exc}")

    def _call_docling_service(
        self,
        base_url: str,
        api_key: str,
        source_path: Path,
        output_format: str,
        max_file_size_mb: float,
        tool_parameters: dict[str, Any],
        convert_path: str,
    ) -> dict[str, Any]:
        headers = {}
        if api_key:
            headers["X-Api-Key"] = api_key

        docling_format = self._to_docling_format(output_format)
        data = self._build_docling_form_data(
            docling_format=docling_format,
            max_file_size_mb=max_file_size_mb,
            tool_parameters=tool_parameters,
        )
        convert_url = self._join_api_url(base_url, convert_path)

        with source_path.open("rb") as file_handle:
            response = requests.post(
                convert_url,
                headers=headers,
                files=[("files", (source_path.name, file_handle, "application/octet-stream"))],
                data=data,
                timeout=600,
            )

        self._raise_for_bad_response(response, convert_url)
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Docling API returned a non-object JSON response")
        text = self._extract_docling_text(payload, output_format)
        payload["text"] = text
        return payload

    def _join_api_url(self, base_url: str, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if not path:
            path = "/v1/convert/file"
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

    def _build_docling_form_data(
        self,
        docling_format: str,
        max_file_size_mb: float,
        tool_parameters: dict[str, Any],
    ) -> list[tuple[str, str]]:
        document_timeout = tool_parameters.get("document_timeout")
        if document_timeout in (None, ""):
            document_timeout = int(max_file_size_mb * 6)

        data = [
            ("target_type", "inbody"),
            ("to_formats", docling_format),
            ("document_timeout", str(document_timeout)),
            ("do_ocr", self._bool_text(tool_parameters.get("do_ocr", True))),
            ("force_ocr", self._bool_text(tool_parameters.get("force_ocr", False))),
            ("do_table_structure", self._bool_text(tool_parameters.get("do_table_structure", True))),
            ("include_images", self._bool_text(tool_parameters.get("include_images", True))),
        ]

        for name in ("image_export_mode", "pdf_backend", "table_mode", "pipeline"):
            value = tool_parameters.get(name)
            if value not in (None, ""):
                data.append((name, str(value)))

        ocr_lang = str(tool_parameters.get("ocr_lang") or "").strip()
        if ocr_lang:
            for lang in [item.strip() for item in ocr_lang.split(",") if item.strip()]:
                data.append(("ocr_lang", lang))

        page_range = str(tool_parameters.get("page_range") or "").strip()
        if page_range:
            parts = [item.strip() for item in page_range.replace("-", ",").split(",") if item.strip()]
            if len(parts) != 2 or not all(item.isdigit() for item in parts):
                raise ValueError("`page_range` must look like `1,3` or `1-3`.")
            data.append(("page_range", parts[0]))
            data.append(("page_range", parts[1]))

        return data

    def _to_docling_format(self, output_format: str) -> str:
        return {
            "markdown": "md",
            "text": "text",
            "html": "html",
            "json": "json",
            "doctags": "doctags",
        }[output_format]

    def _extract_docling_text(self, payload: dict[str, Any], output_format: str) -> str:
        document = payload.get("document")
        if not isinstance(document, dict):
            raise ValueError("Docling Serve response must contain `document`")

        field_name = {
            "markdown": "md_content",
            "text": "text_content",
            "html": "html_content",
            "json": "json_content",
            "doctags": "doctags_content",
        }[output_format]

        content = document.get(field_name)
        if content is None and output_format == "markdown":
            content = document.get("markdown_content")
        if content is None:
            errors = payload.get("errors") or []
            raise ValueError(
                f"Docling Serve response did not include `{field_name}`. "
                f"status={payload.get('status')}, errors={errors}"
            )
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False, default=str)

    def _materialize_file(
        self,
        file_obj: Any,
        temp_dir: Path,
        max_file_size_bytes: int,
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
            request = Request(str(url), headers={"User-Agent": "dify-docling-plugin/0.1.2"})
            with urlopen(request, timeout=120) as response:
                data = response.read(max_file_size_bytes + 1)
                response_mime = response.headers.get_content_type()

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
