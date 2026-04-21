# Dify Docling 插件

简体中文 | [English](README.md)

在 Dify 中通过你自己部署的 [Docling Serve](https://github.com/docling-project/docling-serve) API 解析文档。

这个项目只提供 Dify 插件，不负责安装、打包或运行 Docling。请按照 Docling 官方文档部署 Docling Serve，然后在插件中填写 Dify 插件运行环境能够访问到的 Docling Serve 地址。

## 特性

- 支持 Dify Workflow、Chatflow、Agent 中的文件变量。
- 调用独立部署的 Docling Serve 兼容 HTTP API。
- 支持 Markdown、纯文本、HTML、JSON、DocTags 输出。
- 向下游节点提供稳定的 `content` 输出变量。
- 转发常见 Docling Serve 参数，例如 OCR、表格结构、PDF backend、图片导出模式、页码范围、文档超时等。
- Docling 服务独立部署，便于单独扩容、限流、加密、挂载模型或接入内网服务。

## 工作方式

```text
Dify 文件变量
  -> Dify Docling 插件
  -> Docling Serve API
  -> 解析结果返回 Dify
```

插件会在 Dify 插件运行环境中读取文件变量，将文件通过 `POST /v1/convert/file` 发送给 Docling Serve，并把结构化 JSON 返回给 Dify。

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

只要其中任意一个端点可访问，就会认为服务地址可用。真正解析文件时仍然调用：

```text
POST /v1/convert/file
```

## Provider 凭据

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `Docling API 地址` | 是 | Docling Serve 兼容 API 的基础地址。 |
| `API Key` | 否 | 可选，会作为 `X-Api-Key` 请求头发送。服务没有启用鉴权时留空。 |

## 工具：解析文件

### 输入参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `file` | 必填 | 需要解析的 Dify 文件变量。 |
| `output_format` | `markdown` | `content` 字段的输出格式。用于 LLM 时通常推荐 Markdown。 |
| `max_file_size_mb` | `100` | 插件侧文件大小限制，超过后不会发送到 Docling Serve。 |
| `do_ocr` | `true` | 请求 Docling Serve 对扫描 PDF 或图片执行 OCR，需要服务端支持。 |
| `force_ocr` | `false` | 即使已有文本层也强制 OCR，适合文本层质量差的 PDF，但更慢。 |
| `ocr_lang` | 空 | OCR 语言提示，例如 `en,zh`。具体取值取决于服务端 OCR 后端。 |
| `do_table_structure` | `true` | 请求 Docling 提取表格单元格、行、列结构。 |
| `table_mode` | `accurate` | `accurate` 偏质量，`fast` 偏速度。 |
| `pdf_backend` | `docling_parse` | 请求使用的 PDF backend，是否可用取决于 Docling Serve。 |
| `image_export_mode` | `embedded` | 控制图片在 Markdown、HTML、JSON 输出中的表示方式。 |
| `include_images` | `true` | 当输出格式支持时，请求 Docling 包含图片。 |
| `pipeline` | `standard` | 普通部署使用 `standard`；`vlm` 需要服务端已配置 VLM 能力。 |
| `page_range` | 空 | 可选页码闭区间，例如 `1,3` 或 `1-3`。 |
| `document_timeout` | 自动 | 单文档超时时间，单位秒。大文件或 OCR 场景可调大。 |

### 输出结果

工具返回 JSON：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `content` | string | 按所选格式转换后的文档内容。 |
| `output_format` | string | 当前输出格式。 |
| `filename` | string | 原始或推断出的文件名。 |
| `mime_type` | string | 原始或推断出的 MIME 类型。 |
| `size` | integer | 输入文件大小，单位字节。 |
| `status` | string | Docling Serve 返回的状态。 |
| `processing_time` | number | Docling Serve 返回的处理耗时。 |
| `service` | object | Docling Serve 原始响应，便于调试或高级工作流使用。 |

下游节点建议引用 `content`：

```text
请总结以下文档：

{{ parse_file.content }}
```

实际变量路径取决于你的 Dify 节点名称，建议在 Dify 变量选择器中点选。

## 高级参数说明

插件只负责把参数转发给 Docling Serve。它不会自动启用 OCR 引擎、GPU 加速、PDF backend、VLM 模型或图片处理能力。

CPU-only 部署建议从以下保守设置开始：

- `pipeline=standard`
- `output_format=markdown`
- `force_ocr=false`
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
dify plugin package dify_plugin_docling --output_path dify_plugin_docling/dist/docling-0.1.0.difypkg
```

如果 Dify 开启了插件签名校验，需要签名：

```bash
dify signature sign dist/docling-0.1.0.difypkg \
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

## 项目状态

这是社区维护项目，不是 Docling 或 Dify 官方项目。

版本历史见 [CHANGELOG.md](CHANGELOG.md)。

## License

MIT License. See [LICENSE](LICENSE).
