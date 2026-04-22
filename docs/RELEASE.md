# Release Guide

This guide is for maintainers publishing a new Dify Docling Plugin release.

## 1. Update Versioned Files

Update the version in:

- `manifest.yaml`
- `pyproject.toml`
- `tools/parse_file.py` user agent string
- `CHANGELOG.md`

## 2. Run Checks

```bash
python3 -m py_compile main.py provider/docling.py tools/parse_file.py
python3 -c 'import yaml; [yaml.safe_load(open(p)) for p in ["manifest.yaml", "provider/docling.yaml", "tools/parse_file.yaml"]]; print("yaml ok")'
python3 -c 'import tomllib; tomllib.load(open("pyproject.toml", "rb")); print("toml ok")'
```

## 3. Build Package

Run from the parent directory:

```bash
mkdir -p dify_plugin_docling/dist
dify plugin package dify_plugin_docling --output_path dify_plugin_docling/dist/docling-0.1.2.difypkg
```

## 4. Sign Package

```bash
cd dify_plugin_docling
dify signature sign dist/docling-0.1.2.difypkg \
  -p signing_keys/docling_plugin.private.pem \
  -c community
```

## 5. Verify

```bash
dify signature verify dist/docling-0.1.2.signed.difypkg \
  -p signing_keys/docling_plugin.public.pem
dify plugin checksum dist/docling-0.1.2.signed.difypkg
```

## 6. Publish

Create a GitHub Release and upload:

- `dist/docling-0.1.2.difypkg`
- `dist/docling-0.1.2.signed.difypkg`

Do not commit generated packages or private signing keys.
