# Changelog

All notable changes to this project will be documented in this file.

This project follows a practical versioning scheme based on Dify plugin releases. Public release packages should be attached to GitHub Releases instead of committed to the repository.

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
