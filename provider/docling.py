from typing import Any

import requests
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class DoclingProvider(ToolProvider):
    VALIDATION_PATHS = ("/health", "/docs", "/openapi.json", "/")

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        base_url = str(credentials.get("docling_api_url") or "").strip().rstrip("/")
        api_key = str(credentials.get("docling_api_key") or "").strip()

        if not base_url:
            raise ToolProviderCredentialValidationError("Docling API URL is required.")
        if not base_url.startswith(("http://", "https://")):
            raise ToolProviderCredentialValidationError(
                "Docling API URL must start with http:// or https://."
            )

        headers = {}
        if api_key:
            headers["X-Api-Key"] = api_key

        failures = []
        for path in self.VALIDATION_PATHS:
            try:
                response = requests.get(f"{base_url}{path}", headers=headers, timeout=10)
            except Exception as exc:
                failures.append(f"{path}: {exc}")
                continue

            if response.status_code < 400:
                return
            failures.append(f"{path}: HTTP {response.status_code}")

        failure_text = "; ".join(failures[-3:])
        raise ToolProviderCredentialValidationError(
            "Unable to connect to Docling API service. "
            "The URL must be reachable from Dify plugin-daemon and should expose "
            f"one of {', '.join(self.VALIDATION_PATHS)}. Last checks: {failure_text}"
        )
