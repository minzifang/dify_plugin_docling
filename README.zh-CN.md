# Dify Docling 插件

简体中文 | [English](README.md)

在 Dify 中通过你自己部署的 [Docling Serve](https://github.com/docling-project/docling-serve) API 解析文档。

这个项目只提供 Dify 插件，不负责安装、打包或运行 Docling。请按照 Docling 官方文档部署 Docling Serve，然后在插件中填写 Dify 插件运行环境能够访问到的 Docling Serve 地址。

## 特性

- 支持 Dify Workflow、Chatflow、Agent 中的文件变量。
- 调用独立部署的 Docling Serve 兼容 HTTP API。
- 支持 Markdown、纯文本、HTML、JSON、DocTags 输出。
- 通过 Dify 标准 `text` 输出返回转换后的正文。
- 支持自动、同步和手动异步三种执行模式；默认走更稳定的同步路径，避免工作流长时间 running。
- 转发常见 Docling Serve 参数，例如 OCR、表格结构、PDF backend、图片导出模式、页码范围、文档超时等。
- Docling 服务独立部署，便于单独扩容、限流、加密、挂载模型或接入内网服务。

## 工作方式

```text
Dify 文件变量
  -> Dify Docling 插件
  -> Docling Serve API
  -> 解析结果返回 Dify
```

插件会在 Dify 插件运行环境中读取文件变量，将文件发送到你配置的 Docling 解析地址，并把结构化 JSON 返回给 Dify。

## 前置条件

- 已启用插件能力的 Dify。
- 如果需要自行打包或签名，需要安装 Dify CLI。
- 一个 Dify `plugin_daemon` 能够访问到的 Docling Serve 服务。

Docling Serve 的安装和运行配置请参考官方项目：

- [Docling](https://github.com/docling-project/docling)
- [Docling Serve](https://github.com/docling-project/docling-serve)

## 配置 Docling API 地址

这里填写的地址必须能从 Dify 插件运行环境访问到，而不只是你的浏览器能访问。

常见示例：

| 场景 | 示例地址 |
| --- | --- |
| Docling Serve 与 Dify 在同一个 Docker 网络 | `http://docling-serve:5001` |
| Docling Serve 基础地址 | `http://docling-serve:5001` |
| Source JSON 完整解析地址 | `http://docling-serve:5001/v1/convert/source` |
| Multipart 完整解析地址 | `http://docling-serve:5001/v1/convert/file` |
| 容器访问宿主机上的 Docling Serve | `http://host.docker.internal:5001` |
| Docling Serve 在局域网其它机器 | `http://192.168.1.20:5001` |
| 内网 DNS | `http://docling.internal:5001` |
| 公网或内网 HTTPS 网关 | `https://docling.example.com` |

除非 Docling Serve 和 Dify `plugin_daemon` 在同一个容器里，否则不要填 `http://localhost:5001`。在 Docker 中，`localhost` 通常表示当前容器自己。

插件保存凭据时会尝试：

```text
GET /health
GET /docs
GET /openapi.json
GET /
```

只要其中任意一个端点可访问，就会认为服务地址可用。

解析时，`Docling API 地址` 可以填基础地址，也可以填完整解析地址。只填基础地址时，插件会自动使用官方 Docling Serve 解析路径：

```text
http://docling-serve:5001
-> http://docling-serve:5001/v1/convert/file
```

如果你的网关把解析接口暴露在其它路径，可以填写完整的官方兼容解析地址，也可以使用高级凭据 `解析路径`。例如服务地址本身就是解析接口时，设置：

```text
Docling API 地址: http://192.168.4.211:5009
解析路径: /
```

## Provider 凭据

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `Docling API 地址` | 是 | Docling Serve 基础地址或完整文件解析地址。 |
| `API Key` | 否 | 可选，会作为 `X-Api-Key` 请求头发送。服务没有启用鉴权时留空。 |
| `解析路径` | 否 | 高级网关覆盖项。官方 Docling Serve 留空；如果你配置的 API 地址本身就是解析接口，填 `/`。 |

## 工具：解析文件

### 输入参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `file` | 必填 | 需要解析的 Dify 文件变量。 |
| `output_format` | `markdown` | Dify `text` 输出的正文格式。用于 LLM 时通常推荐 Markdown。 |
| `execution_mode` | `auto` | 执行模式。`auto` 普通文件走同步，超过 2MB 的 PDF 走异步；`sync` 直接调用同步转换接口；`async` 提交任务并轮询结果。 |
| `max_file_size_mb` | `100` | 插件侧文件大小限制，超过后不会发送到 Docling Serve。 |
| `do_ocr` | `false` | 请求 Docling Serve 对扫描 PDF 或图片执行 OCR。大文件中 OCR 可能很慢，建议只在需要时开启。 |
| `send_advanced_options` | `false` | 发送 OCR、表格、图片、PDF backend、pipeline 等高级参数。关闭时更接近 Docling Serve UI 或服务端默认行为。 |
| `request_transport` | `auto` | 请求方式。自动模式下 20MB 以内的 PDF 使用 Source JSON，更大的 PDF 使用 Multipart，避免 base64 膨胀；大多数非 PDF 使用 Multipart。 |
| `force_ocr` | `false` | 即使已有文本层也强制 OCR，适合文本层质量差的 PDF，但更慢。 |
| `ocr_lang` | 空 | OCR 语言提示，例如 `en,zh`。具体取值取决于服务端 OCR 后端。 |
| `do_table_structure` | `true` | 请求 Docling 提取表格单元格、行、列结构。 |
| `table_mode` | `accurate` | `accurate` 偏质量，`fast` 偏速度。 |
| `pdf_backend` | `auto` | 请求使用的 PDF backend。`auto` 表示不发送该字段，由 Docling Serve 选择默认值。 |
| `image_export_mode` | `placeholder` | 控制图片在 Markdown、HTML、JSON 输出中的表示方式。 |
| `include_images` | `false` | 当输出格式支持时，请求 Docling 包含图片。给 LLM 使用或解析大文件时建议关闭。 |
| `pipeline` | `standard` | 普通部署使用 `standard`；`vlm` 需要服务端已配置 VLM 能力。 |
| `page_range` | 空 | 可选页码闭区间，例如 `1,3` 或 `1-3`。 |
| `document_timeout` | 自动 | 单文档超时时间，单位秒。大文件或 OCR 场景可调大。 |
| `request_timeout` | `600` | 同步转换或异步任务提交的 HTTP 超时时间，单位秒。大文件可能需要几分钟；该值需要和 Dify/plugin-daemon、Docling 网关超时配置匹配。 |
| `async_timeout` | `7200` | 异步轮询的总等待时间，单位秒。复杂 PDF 可能需要很多分钟。仅在实际执行模式为 `async` 时使用。 |
| `file_download_timeout` | `120` | 插件下载 Dify 文件的超时时间，单位秒。 |
| `poll_interval` | `5` | 异步模式下查询任务状态的间隔秒数。 |
| `max_output_chars` | `200000` | Dify `text` 输出最多返回的字符数。填 `0` 表示不截断。 |
| `include_raw_response` | `false` | 在 JSON 中包含 Docling API 原始响应，便于调试，但可能非常大。 |

### 输出结果

工具返回 JSON：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `output_format` | string | 当前输出格式。 |
| `execution_mode` | string | 实际使用的执行模式，`async` 或 `sync`。 |
| `requested_execution_mode` | string | 用户请求的执行模式，`auto`、`async` 或 `sync`。 |
| `filename` | string | 原始或推断出的文件名。 |
| `mime_type` | string | 原始或推断出的 MIME 类型。 |
| `size` | integer | 输入文件大小，单位字节。 |
| `status` | string | Docling Serve 返回的状态。 |
| `processing_time` | number | Docling Serve 返回的处理耗时。 |
| `content_length` | integer | 截断前的转换内容长度。 |
| `returned_content_length` | integer | 截断后的返回内容长度。 |
| `content_truncated` | boolean | 内容是否被插件截断。 |
| `content` | string | 应用 `max_output_chars` 后的完整解析内容。下游节点需要明确内容变量时建议选这个 JSON 字段。 |
| `content_preview` | string | 返回内容预览。 |

下游节点建议引用 JSON 输出里的 `content`，也可以使用标准 `text` 输出：

```text
请总结以下文档：

{{ parse_file.content }}
```

实际变量路径取决于你的 Dify 节点名称，建议在 Dify 变量选择器中点选。

### 异步模式

默认建议使用 `execution_mode=auto`。普通文件会走同步快路径，较大的 PDF 会切换到 Docling Serve 异步模式。

选择 `execution_mode=async` 时，插件会调用 Docling Serve 的异步接口：

```text
POST /v1/convert/file/async
GET  /v1/status/poll/{task_id}
GET  /v1/result/{task_id}
```

异步模式更适合大文件，因为插件不需要一直等待同步 HTTP 请求返回；它会按 `poll_interval` 查询任务状态，直到任务完成或超过 `request_timeout`。

如果你的网关只暴露同步接口，可以把 `execution_mode` 改为 `sync`。

## 高级参数说明

插件只负责把参数转发给 Docling Serve。它不会自动启用 OCR 引擎、GPU 加速、PDF backend、VLM 模型或图片处理能力。

CPU-only 部署建议从以下保守设置开始：

- `pipeline=standard`
- `output_format=markdown`
- `force_ocr=false`
- `do_ocr=false`
- `include_images=false`
- `image_export_mode=placeholder`
- `table_mode=accurate`

如果某个参数在你的 Docling Serve 部署中不支持，API 可能会返回错误，插件会把错误展示到 Dify。

## 开发

本地检查：

```bash
python3 -m py_compile main.py provider/docling.py tools/parse_file.py
python3 -c 'import yaml; [yaml.safe_load(open(p)) for p in ["manifest.yaml", "provider/docling.yaml", "tools/parse_file.yaml"]]; print("yaml ok")'
python3 -c 'import tomllib; tomllib.load(open("pyproject.toml", "rb")); print("toml ok")'
```

从上级目录打包到 `dist/`：

```bash
mkdir -p dify_plugin_docling/dist
dify plugin package dify_plugin_docling --output_path dify_plugin_docling/dist/docling-0.1.19.difypkg
```

如果 Dify 开启了插件签名校验，需要签名：

```bash
dify signature sign dist/docling-0.1.19.difypkg \
  -p signing_keys/docling_plugin.private.pem \
  -c community
```

签名私钥和打包产物不应提交到 Git。

## 常见问题

### 浏览器能访问 localhost，但 Dify 插件保存失败

浏览器和 Dify `plugin_daemon` 不在同一个网络命名空间。Docker 中 `plugin_daemon` 里的 `localhost` 指的是 `plugin_daemon` 容器自己。

请使用 `plugin_daemon` 能访问到的地址，例如 `host.docker.internal`、Docker 服务名、局域网 IP、内网 DNS 或 HTTPS 地址。

### Invalid File URL `/files/...`

Dify 可能提供根相对路径形式的文件 URL。插件会按以下顺序补全：

1. `FILES_URL`
2. `DIFY_INNER_API_URL`
3. `PLUGIN_DIFY_INNER_API_URL`
4. fallback `http://api:5001`

如果你的 Dify 自托管环境改过服务名或 Docker 网络，请为插件运行环境配置上面的环境变量之一。

### `/v1/convert/file` 返回 504 Gateway Timeout

这表示插件已经连到了你配置的 Docling API，但是 Docling 前面的网关、反向代理、负载均衡或服务包装层在等待解析完成时超时了。

常见处理方式：

- 调大 Docling Serve 前面网关或反向代理的超时时间。
- 检查 Docling Serve 日志和资源占用。
- 给 Docling Serve 分配更多 CPU、内存或 GPU 资源。
- 降低解析成本，例如设置 `page_range`、不需要 OCR 时关闭 OCR、使用 `table_mode=fast`、没有配置 VLM 时不要使用 `pipeline=vlm`。
- 如果服务端支持更长处理时间，调大 `document_timeout`。

如果同一个文件直接用 `curl` 调 Docling Serve 也会超时，那问题在 Docling 服务链路，不在 Dify 插件。

### 大 Word 或 PDF 一直 Running

包含大量图片的 Word/PDF 可能解析很慢，也可能产生非常大的返回内容，尤其是在启用 OCR 或内嵌图片时。

给 LLM 工作流使用时建议：

- `output_format=markdown`
- `execution_mode=auto`
- `send_advanced_options=false`
- `do_ocr=false`
- `force_ocr=false`
- `include_images=false`
- `image_export_mode=placeholder`
- 如果不强依赖表格精度，使用 `table_mode=fast`
- `request_timeout=600`
- `async_timeout=3600` 到 `7200`，取决于你希望 Dify 最多等多久
- `poll_interval=5`
- `max_output_chars=200000`，确实需要更多正文时再谨慎调大
- `include_raw_response=false`

如果这样仍然卡住，请用同一个文件直接请求你的 Docling API 测试。如果直接 API 很快返回但 Dify 一直 running，重点检查工作流是否正在把超大的 `text` 传给下游节点。

## 项目状态

这是社区维护项目，不是 Docling 或 Dify 官方项目。

版本历史见 [CHANGELOG.md](CHANGELOG.md)。

## License

MIT License. See [LICENSE](LICENSE).
