# Examples

Every example below is a runnable script in
[`examples/`](https://github.com/aiptimizer/TurboOCR-python/tree/main/examples).
Each runs end-to-end against the bundled ACME invoice fixture with a
TurboOCR server reachable at `http://localhost:8000` (override with
`TURBO_OCR_BASE_URL`). The PDF/A-4 branch in the searchable-PDF example
also needs `turboocr[pdfa]`.

```bash
export TURBO_OCR_BASE_URL=http://localhost:8000  # optional, this is the default
python docs/00_quickstart.py
python docs/02_pdf_to_markdown.py
```

## 00 Quickstart

The smallest useful script — sync image OCR with `Client`.

[`examples/00_quickstart.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/00_quickstart.py)

## 01 Image OCR with layout

Image OCR with `layout`, `reading_order`, `include_blocks`. Dumps both text
items (with bbox + confidence) and reading-order-grouped blocks.

[`examples/01_image_ocr_with_layout.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/01_image_ocr_with_layout.py)

## 02 PDF → Markdown

`recognize_pdf` + `render_to_markdown` on a multi-page invoice.

[`examples/02_pdf_to_markdown.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/02_pdf_to_markdown.py)

## 03 Searchable PDF

PDF → invisible-text-overlay PDF, verified via `pypdf.extract_text()`.
Also demonstrates PDF/A-4 output when `turboocr[pdfa]` is installed.

[`examples/03_searchable_pdf.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/03_searchable_pdf.py)

## 04 Async client

`AsyncClient` + `asyncio.gather` for concurrent OCR.

[`examples/04_async_client.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/04_async_client.py)

## 05 Batch

`recognize_batch` over multiple images, walked via `iter_results()` so
per-slot failures surface cleanly.

[`examples/05_batch.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/05_batch.py)

## 06 gRPC

`GrpcClient` — same surface as `Client`, gRPC transport. Requires
`pip install 'turboocr[grpc]'`.

[`examples/06_grpc.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/06_grpc.py)

## 07 Retry and timeout

Custom `RetryPolicy` (5 attempts, bounded backoff) plus per-request
`timeout=`.

[`examples/07_retry_and_timeout.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/07_retry_and_timeout.py)

## 08 Custom httpx.Client

Pass your own `httpx.Client` for custom TLS / mTLS / connection limits /
proxies.

[`examples/08_custom_httpx_client.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/08_custom_httpx_client.py)

## 09 Markdown style

Register a custom layout label + renderer on `MarkdownStyle` to extend the
default label-to-Markdown mapping.

[`examples/09_markdown_style.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/09_markdown_style.py)

## 10 Tables and formulas

Iterate `response.tables` / `response.formulas`. See [Layout →
Tables/Formulas](api/layout.md#table) for the partial-support caveat.

[`examples/10_tables_and_formulas.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/10_tables_and_formulas.py)

## 11 Folder pipeline

`AsyncClient` + `asyncio.Semaphore` for a bounded-concurrency PDF→Markdown
folder pipeline.

[`examples/11_folder_pipeline.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/11_folder_pipeline.py)

## 12 Hooks and logging

httpx `on_request` / `on_response` event hooks plus the SDK's stdlib logger.

[`examples/12_hooks_and_logging.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/12_hooks_and_logging.py)
