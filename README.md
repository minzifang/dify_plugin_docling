# Dify Docling Plugin

[简体中文](README.zh-CN.md) | English

Parse documents in Dify by calling your own [Docling Serve](https://github.com/docling-project/docling-serve) API.

This project is a Dify plugin only. It does not install, bundle, or operate Docling for you. Deploy Docling Serve by following the official Docling documentation, then point this plugin to the Docling Serve URL that is reachable from your Dify plugin runtime.

## Highlights

- Works with Dify file variables in Workflow, Chatflow, and Agent apps.
- Calls a standalone Docling Serve-compatible HTTP API.
- Supports Markdown, plain text, HTML, JSON, and DocTags outputs.
- Returns converted content through Dify's standard `text` output.
- Supports auto, sync, and manual async execution modes; the default uses the stable synchronous path to avoid long-running workflows.
- Forwards common Docling Serve options such as OCR, table extraction, PDF backend, image export mode, page range, and document timeout.
- Keeps document parsing infrastructure outside Dify, so Docling can be deployed, scaled, secured, and tuned independently.

## How It Works

```text
Dify file variable
  -> Dify Docling Plugin
  -> Docling Serve API
  -> Parsed content returned to Dify
```

The plugin downloads the Dify file variable inside the plugin runtime, sends it to your configured Docling conversion URL, and returns structured JSON to Dify.

## Requirements

- Dify with plugin support enabled.
- Dify CLI, if you want to build or sign the package yourself.
- A Docling Serve instance reachable from Dify `plugin_daemon`.

For Docling Serve installation and runtime configuration, use the official project documentation:

- [Docling](https://github.com/docling-project/docling)
- [Docling Serve](https://github.com/docling-project/docling-serve)

## Configure The Docling API URL

The value must be reachable from the Dify plugin runtime, not just from your browser.

Common examples:

| Scenario | Example URL |
| --- | --- |
| Docling Serve on the same Docker network as Dify | `http://docling-serve:5001` |
| Docling Serve base URL | `http://docling-serve:5001` |
| Full Source JSON conversion URL | `http://docling-serve:5001/v1/convert/source` |
| Full multipart conversion URL | `http://docling-serve:5001/v1/convert/file` |
| Docling Serve on the Docker host from a container | `http://host.docker.internal:5001` |
| Docling Serve on another LAN machine | `http://192.168.1.20:5001` |
| Docling Serve behind internal DNS | `http://docling.internal:5001` |
| Public or private HTTPS endpoint | `https://docling.example.com` |

Avoid `http://localhost:5001` unless Docling Serve runs in the same container as Dify `plugin_daemon`. In Docker, `localhost` usually means the current container.

The plugin validates the base URL by trying:

```text
GET /health
GET /docs
GET /openapi.json
GET /
```

Only one of these endpoints needs to respond successfully.

For conversion, `Docling API URL` can be either a base URL or a full conversion URL. If you enter a base URL, the plugin uses the official Docling Serve conversion path automatically:

```text
http://docling-serve:5001
-> http://docling-serve:5001/v1/convert/file
```

If your gateway exposes conversion at another path, either enter the full official-compatible conversion URL or use the advanced `Conversion Path` credential. For example, when the service URL itself is the conversion endpoint, set:

```text
Docling API URL: http://192.168.4.211:5009
Conversion Path: /
```

## Provider Credentials

| Field | Required | Description |
| --- | --- | --- |
| `Docling API URL` | Yes | Docling Serve base URL or full file conversion URL. |
| `API Key` | No | Optional value sent as `X-Api-Key`. Leave empty if your service does not require it. |
| `Conversion Path` | No | Advanced override for custom gateways. Leave empty for official Docling Serve. Use `/` when the configured API URL itself is the conversion endpoint. |

## Tool: Parse File

### Inputs

| Option | Default | Description |
| --- | --- | --- |
| `file` | required | Dify file variable to parse. |
| `output_format` | `markdown` | Main content format returned in the Dify `text` output. Markdown is recommended for LLM prompts. |
| `execution_mode` | `auto` | Execution mode. `auto` uses sync for normal files and async for PDFs larger than 2 MB. `sync` calls the synchronous endpoint directly. `async` submits a task and polls for the result. |
| `max_file_size_mb` | `100` | Plugin-side file size limit before uploading to Docling Serve. |
| `do_ocr` | `false` | Ask Docling Serve to run OCR for scanned PDFs and images. Enable only when needed because OCR can be slow on large files. |
| `send_advanced_options` | `false` | Send OCR/table/image/PDF backend/pipeline options. Leave off to mimic Docling Serve UI/service defaults. |
| `request_transport` | `auto` | Request transport. Auto uses Source JSON for PDFs up to 20 MB and multipart for larger PDFs to avoid base64 expansion. Most non-PDF files use multipart. |
| `force_ocr` | `false` | Force OCR even when a text layer already exists. Useful for poor embedded text, but slower. |
| `ocr_lang` | empty | Comma-separated OCR language hints such as `en,zh`. Supported values depend on your OCR backend. |
| `do_table_structure` | `true` | Ask Docling to extract table cells, rows, and columns. |
| `table_mode` | `accurate` | `accurate` favors quality; `fast` favors speed. |
| `pdf_backend` | `auto` | Requested PDF backend. `auto` omits the field and lets Docling Serve choose its default. |
| `image_export_mode` | `placeholder` | How images are represented in Markdown, HTML, and JSON outputs. |
| `include_images` | `false` | Ask Docling to include images when the selected output format supports them. Leave off for LLM workflows and large files. |
| `pipeline` | `standard` | Use `standard` for normal deployments. `vlm` requires service-side VLM support. |
| `page_range` | empty | Optional inclusive page range, for example `1,3` or `1-3`. |
| `document_timeout` | auto | Per-document timeout in seconds. Increase for large or OCR-heavy files. |
| `request_timeout` | `600` | HTTP timeout in seconds for sync conversion or async task submission. Large files may need several minutes; align this with your Dify/plugin-daemon and Docling gateway timeouts. |
| `async_timeout` | `7200` | Total async polling budget in seconds. Complex PDFs can take many minutes. Only used when the actual execution mode is `async`. |
| `file_download_timeout` | `120` | Timeout in seconds for downloading the Dify file into the plugin runtime. |
| `poll_interval` | `5` | Seconds between async status checks. |
| `max_output_chars` | `200000` | Maximum characters returned in the Dify `text` output. Use `0` for no truncation. |
| `include_raw_response` | `false` | Include raw Docling API response in JSON for debugging. This can be very large. |

### Output

The tool returns JSON:

| Field | Type | Description |
| --- | --- | --- |
| `output_format` | string | Selected output format. |
| `execution_mode` | string | Actual execution mode used, `async` or `sync`. |
| `requested_execution_mode` | string | Requested execution mode, `auto`, `async`, or `sync`. |
| `filename` | string | Original or inferred file name. |
| `mime_type` | string | Original or inferred MIME type. |
| `size` | integer | Input file size in bytes. |
| `status` | string | Status returned by Docling Serve. |
| `processing_time` | number | Processing time returned by Docling Serve. |
| `content_length` | integer | Original converted content length before truncation. |
| `returned_content_length` | integer | Returned content length after truncation. |
| `content_truncated` | boolean | Whether the plugin truncated the standard `text` output. |
| `content` | string | Full converted content after `max_output_chars` is applied. Use this JSON field when downstream nodes need an explicit content variable. |
| `content_preview` | string | Short preview of returned content. |

Use `content` from the JSON output or the standard `text` output in downstream nodes:

```text
Please summarize the following document:

{{ parse_file.content }}
```

The exact variable path depends on the Dify node name. Select it from Dify's variable picker when possible.

### Async Mode

The recommended default is `execution_mode=auto`. It uses the synchronous fast path for normal files and switches larger PDFs to Docling Serve async mode.

When `execution_mode=async`, the plugin uses Docling Serve's async endpoints:

```text
POST /v1/convert/file/async
GET  /v1/status/poll/{task_id}
GET  /v1/result/{task_id}
```

Async mode is better for larger files because the plugin does not keep one synchronous HTTP request open while Docling parses the document. It polls every `poll_interval` seconds until the task completes or `request_timeout` is reached.

If your gateway only exposes the synchronous conversion endpoint, set `execution_mode=sync`.

## Notes On Advanced Options

This plugin only forwards options to Docling Serve. It does not enable OCR engines, GPU acceleration, PDF backends, VLM models, or image processing capabilities by itself.

For a conservative CPU-only deployment, start with:

- `pipeline=standard`
- `output_format=markdown`
- `force_ocr=false`
- `do_ocr=false`
- `include_images=false`
- `image_export_mode=placeholder`
- `table_mode=accurate`

If an option is unsupported by your Docling Serve deployment, the API may return an error and the plugin will surface it in Dify.

## Development

Run local checks:

```bash
python3 -m py_compile main.py provider/docling.py tools/parse_file.py
python3 -c 'import yaml; [yaml.safe_load(open(p)) for p in ["manifest.yaml", "provider/docling.yaml", "tools/parse_file.yaml"]]; print("yaml ok")'
python3 -c 'import tomllib; tomllib.load(open("pyproject.toml", "rb")); print("toml ok")'
```

Build a package into `dist/` from the parent directory:

```bash
mkdir -p dify_plugin_docling/dist
dify plugin package dify_plugin_docling --output_path dify_plugin_docling/dist/docling-0.1.19.difypkg
```

If plugin verification is enabled, sign the package:

```bash
dify signature sign dist/docling-0.1.19.difypkg \
  -p signing_keys/docling_plugin.private.pem \
  -c community
```

Keep private signing keys and generated packages out of Git.

## Troubleshooting

### `localhost` Works In My Browser But Fails In Dify

Your browser and Dify `plugin_daemon` are not the same network namespace. In Docker, `localhost` inside `plugin_daemon` points to the `plugin_daemon` container itself.

Use an address reachable from `plugin_daemon`, such as `host.docker.internal`, a Docker service name, a LAN IP, an internal DNS name, or an HTTPS endpoint.

### Invalid File URL `/files/...`

Dify may provide root-relative file URLs. The plugin resolves them using:

1. `FILES_URL`
2. `DIFY_INNER_API_URL`
3. `PLUGIN_DIFY_INNER_API_URL`
4. fallback `http://api:5001`

If your self-hosted Dify deployment uses custom service names or networks, configure one of the environment variables above for the plugin runtime.

### 504 Gateway Timeout From `/v1/convert/file`

This means the plugin reached the configured Docling API, but a gateway, reverse proxy, load balancer, or Docling service wrapper timed out while waiting for parsing to finish.

Common fixes:

- Increase timeout settings in the gateway in front of Docling Serve.
- Check Docling Serve logs and resource usage.
- Give Docling Serve more CPU, memory, or GPU resources.
- Reduce parsing cost by setting `page_range`, disabling OCR when not needed, using `table_mode=fast`, or avoiding `pipeline=vlm` unless the service is configured for it.
- Increase `document_timeout` if your Docling Serve deployment supports longer document processing.

If the same file also times out when calling Docling Serve directly with `curl`, the issue is in the Docling service path rather than Dify.

### Large Word Or PDF Files Keep Running

Large documents with many images can be slow or produce very large responses, especially when images are embedded or OCR is enabled.

Recommended settings for LLM workflows:

- `output_format=markdown`
- `execution_mode=auto`
- `send_advanced_options=false`
- `do_ocr=false`
- `force_ocr=false`
- `include_images=false`
- `image_export_mode=placeholder`
- `table_mode=fast` if table accuracy is not critical
- `request_timeout=600`
- `async_timeout=3600` to `7200`, depending on how long you want Dify to wait
- `poll_interval=5`
- `max_output_chars=200000`, or increase carefully if the next node really needs more text
- `include_raw_response=false`

If this still hangs, test the same file directly against your Docling API. If the direct API call returns quickly but Dify stays running, check whether your workflow is trying to pass a very large `text` value into the next node.

## Project Status

This project is community-maintained and is not an official Docling or Dify project.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT License. See [LICENSE](LICENSE).
