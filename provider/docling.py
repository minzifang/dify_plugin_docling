from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class DoclingProvider(ToolProvider):
    VALIDATION_PATHS = ("/health", "/docs", "/openapi.json", "/")

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_url = str(credentials.get("docling_api_url") or "").strip().rstrip("/")
        api_key = str(credentials.get("docling_api_key") or "").strip()
        convert_path = str(credentials.get("docling_convert_path") or "").strip()

        if not api_url:
            raise ToolProviderCredentialValidationError("Docling API URL is required.")
        if not api_url.startswith(("http://", "https://")):
            raise ToolProviderCredentialValidationError(
                "Docling API URL must start with http:// or https://."
            )

        headers = {}
        if api_key:
            headers["X-Api-Key"] = api_key

        validation_base_url = self._origin_url(api_url)
        failures = []
        validation_paths = self.VALIDATION_PATHS
        if convert_path:
            validation_paths = (convert_path, *self.VALIDATION_PATHS)

        for path in validation_paths:
            try:
                check_url = path if path.startswith(("http://", "https://")) else urljoin(validation_base_url.rstrip("/") + "/", path.lstrip("/"))
                response = requests.get(check_url, headers=headers, timeout=10)
            except Exception as exc:
                failures.append(f"{path}: {exc}")
                continue

            if response.status_code < 400 or (convert_path and response.status_code in {401, 403, 405}):
                return
            failures.append(f"{path}: HTTP {response.status_code}")

        failure_text = "; ".join(failures[-3:])
        raise ToolProviderCredentialValidationError(
            "Unable to connect to Docling API service. "
            "The URL must be reachable from Dify plugin-daemon and should expose "
            f"one of {', '.join(self.VALIDATION_PATHS)}. Last checks: {failure_text}"
        )

    def _origin_url(self, url: str) -> str:
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")
