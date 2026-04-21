# Changelog

All notable changes to this project will be documented in this file.

This project follows a practical versioning scheme based on Dify plugin releases. Public release packages should be attached to GitHub Releases instead of committed to the repository.

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
