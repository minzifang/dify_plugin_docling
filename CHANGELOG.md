# Changelog

All notable changes to this project will be documented in this file.

This project follows a practical versioning scheme based on Dify plugin releases. Public release packages should be attached to GitHub Releases instead of committed to the repository.

## [0.1.20] - 2026-04-23

### Fixed

- Added segmented PDF parsing for larger PDFs in `execution_mode=auto`, splitting long PDFs into page chunks and merging the converted output.
- Verified the strategy directly against `信创国产化数据库测试-海光.pdf`: the same file succeeds when parsed in 20-page chunks, avoiding the single huge PDF conversion path.

## [0.1.19] - 2026-04-23

### Fixed

- Added submit retry handling for Docling Serve connection resets during PDF conversion request submission.
- Waits for Docling Serve `/docs` to become reachable before retrying after a disconnect, which helps when the service restarts cleanly during a request.
- Increased the default async polling budget to 7200 seconds for complex or large PDFs.
- Clarified the connection-reset diagnostic to distinguish plugin retry exhaustion from normal Docling parsing failures.

## [0.1.18] - 2026-04-23

### Fixed

- Added PDF-specific auto routing: PDFs larger than 2 MB now use Docling async mode automatically.
- Changed request transport auto mode to use Source JSON for PDFs up to 20 MB and multipart for larger PDFs, avoiding base64 expansion for very large files.
- Simplified `/v1/convert/source` requests to the official `sources` + `target={kind: inbody}` schema.
- Disabled table structure extraction by default for PDFs unless advanced options are explicitly enabled, reducing parsing cost for large or irregular PDFs.
- Improved diagnostics when Docling Serve closes the connection before returning a response.

## [0.1.17] - 2026-04-23

### Fixed

- Changed the default request transport back to multipart `/v1/convert/file`, matching Docling Serve UI-style file upload behavior and avoiding base64 JSON expansion for larger PDFs and Office files.
- Removed the plugin-side 180-second sync timeout cap. `request_timeout` now controls the full synchronous conversion wait budget.
- Sent `target_type=INBODY` with the official uppercase enum value for multipart conversion requests.
- Added a full `content` field to JSON output so downstream Dify nodes can select parsed content directly instead of only receiving metadata or preview fields.

## [0.1.16] - 2026-04-23

### Changed

- Added automatic async execution for PDFs larger than 8 MB while keeping normal files on the verified synchronous source JSON path.
- Kept conservative source JSON conversion options for both sync and async PDF workflows.

## [0.1.15] - 2026-04-23

### Fixed

- Restored the `sources` request shape for Docling Serve 1.16.1 `/v1/convert/source`, matching the live OpenAPI schema.
- Added conservative default conversion options for source JSON requests: explicit `from_formats`, `do_ocr=false`, `include_images=false`, and `image_export_mode=placeholder`.
- Kept `file_sources` as fallback only for older compatible gateways.

## [0.1.14] - 2026-04-23

### Fixed

- Changed source JSON request order to use the simpler `file_sources` payload first, matching common Docling Serve usage examples.
- Removed the default `target` object from source JSON requests so the request body stays close to the minimal documented curl example.

## [0.1.13] - 2026-04-23

### Fixed

- Changed the default Docling request transport from multipart `/v1/convert/file` to source JSON `/v1/convert/source`.
- Added `request_transport` so users can manually switch back to multipart if their Docling gateway only exposes `/v1/convert/file`.
- Added compatibility fallback between the newer `sources` request shape and older `file_sources` shape for source JSON requests.

## [0.1.12] - 2026-04-23

### Fixed

- Reverted `auto` execution to always use the synchronous Docling endpoint. Async is now manual only.
- Added a hard 180-second cap for synchronous Docling requests, so stale workflow nodes with older long timeout values cannot run for ten minutes without output.
- Restored the plugin runtime maximum request timeout to 600 seconds to match the intended fast-fail workflow behavior.

## [0.1.11] - 2026-04-23

### Fixed

- Split synchronous HTTP timeout from async polling timeout. Normal Word/Office files no longer inherit the long async wait budget.
- Added `async_timeout` and `file_download_timeout` so users can distinguish Docling parsing delays from Dify file download delays.
- Added stage-specific timeout messages for Dify file download, sync conversion, async submit, async polling, and result fetch.
- Sent the detected file MIME type to Docling instead of always using `application/octet-stream`.

## [0.1.10] - 2026-04-23

### Fixed

- Changed the default execution mode to `auto` so normal Word, Office, text, HTML, and Markdown files use the fast synchronous Docling endpoint.
- Kept async mode available for larger PDFs and large files without making every document pay the async polling overhead.
- Added `requested_execution_mode` to JSON metadata so users can see whether `auto` resolved to `sync` or `async`.

## [0.1.9] - 2026-04-23

### Fixed

- Made async status polling tolerant of per-request socket timeouts. A single `/v1/status/poll/{task_id}` timeout now retries until the configured total wait budget is exhausted.
- Increased the default plugin wait budget to 3600 seconds and the plugin runtime maximum request timeout to 7200 seconds for large documents.
- Limited the async submit request timeout separately from the total polling budget, so the initial task submission cannot consume the entire parse timeout.

## [0.1.8] - 2026-04-23

### Changed

- Added async execution mode for large documents. The plugin can submit Docling tasks through `/v1/convert/file/async`, poll status, and fetch results from `/v1/result/{task_id}`.
- Changed parse failures to raise plugin errors instead of returning error text as parsed document content.
- Removed confusing optional `content` JSON output controls from the tool UI. Converted document text is returned through Dify's standard `text` output.
- Improved timeout diagnostics for socket-level timeout errors.

## [0.1.7] - 2026-04-23

### Fixed

- Removed the explicit `content` output schema and variable message to avoid showing both `text` and `content` in downstream Dify nodes. The converted document is now emitted through Dify's standard `text` output.
- Added fallback extraction for Docling responses where the selected output field is empty, for example `json_content={}` while `md_content` or `text_content` is available.

## [0.1.6] - 2026-04-23

### Changed

- Simplified Docling API URL handling. Users can now enter either a Docling Serve base URL or a full conversion URL in `Docling API URL`.
- Removed the separate conversion endpoint path field from new provider configuration UI. Existing saved `docling_convert_path` values remain supported for backward compatibility.
- Added `send_advanced_options`; advanced OCR/table/image/PDF backend/pipeline fields are only sent when this is enabled, making the default request closer to Docling Serve UI/service defaults.

## [0.1.5] - 2026-04-23

### Fixed

- Reduced duplicate large outputs that could keep Dify tool nodes running after Docling finished parsing large documents.
- JSON output now contains metadata and a short preview by default instead of duplicating the full converted document and raw Docling response.

### Added

- Added `max_output_chars` to cap the returned `content` variable size. Use `0` to disable truncation.
- Added `emit_text_output`, `include_content_in_json`, and `include_raw_response` switches for workflows that explicitly need those larger outputs.

## [0.1.4] - 2026-04-22

### Fixed

- Changed the default PDF backend to `auto` so the plugin does not send an unsupported `pdf_backend=docling_parse` value to Docling Serve versions that only accept `pypdfium2`, `dlparse_v1`, `dlparse_v2`, or `dlparse_v4`.

## [0.1.3] - 2026-04-22

### Changed

- Added plugin-side `request_timeout` to prevent long-running Docling API calls from waiting indefinitely.
- Changed default parsing options to be safer for large documents and LLM workflows: OCR off by default, image inclusion off by default, and image export mode set to `placeholder`.
- Added clearer timeout guidance for large Word/PDF files containing many images.

## [0.1.2] - 2026-04-22

### Fixed

- Added an explicit `content` variable message and a generic text message on successful parsing so downstream Dify nodes can reliably consume the parsed document content.

## [0.1.1] - 2026-04-22

### Changed

- Added configurable conversion endpoint path for Docling-compatible gateways that do not expose `/v1/convert/file`.
- Improved HTTP error messages returned by the Docling API, especially `504 Gateway Timeout`, `502 Bad Gateway`, and `503 Service Unavailable`.
- Documented how to troubleshoot `/v1/convert/file` gateway timeouts in English and Simplified Chinese.

## [0.1.0] - 2026-04-21

### Added

- Initial open-source-ready release.
- Standalone Docling Serve provider configuration.
- `Parse File` tool for Dify file variables.
- Markdown, plain text, HTML, JSON, and DocTags output formats.
- Stable `content` output field for downstream Dify nodes.
- Advanced Docling Serve options for OCR, table extraction, PDF backend, image export, page range, pipeline, and timeout.
- Flexible provider validation using `/health`, `/docs`, `/openapi.json`, or `/`.
- English and Simplified Chinese documentation.
- MIT license and release documentation.

### Changed

- Clarified that Docling Serve must be deployed separately by following the official Docling documentation.
- Documented Docker, LAN IP, internal DNS, host bridge, and HTTPS URL examples for the Docling API URL.
- Renamed the main workflow output from `text` to `content` to avoid collisions with Dify's generic tool text output.
- Moved generated plugin packages to the ignored `dist/` workflow.

### Removed

- Removed project-specific Docling service scaffolding from the public documentation path to avoid confusing this plugin with a Docling installer.

## Historical Notes

Before `0.1.0`, this repository went through local development builds from `0.0.1` to `0.0.6`. Those builds were used to validate signing, Dify Docker networking, relative Dify file URLs, and Docling Serve compatibility.
