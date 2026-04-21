# Security Policy

## Reporting

If you discover a security issue, please open a private security advisory on GitHub if available, or contact the repository maintainer through a private channel.

Please do not publish sensitive details before maintainers have had time to investigate.

## Data Handling

This plugin sends uploaded Dify files to the Docling API URL configured by the workspace administrator. Review your Docling Serve deployment, network path, logs, storage, and retention policies before using the plugin with sensitive documents.

## Signing Keys

Do not commit private signing keys. Generated `.difypkg` files and signed packages should be published as release assets, not source files.
