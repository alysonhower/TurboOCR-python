# examples — runnable scripts

Each script is self-contained and runs against the bundled
[`sample/acme_invoice.pdf`](sample/acme_invoice.pdf) +
[`sample/acme_invoice.png`](sample/acme_invoice.png) fixtures. The base URL
defaults to `http://localhost:8000` (override with `TURBO_OCR_BASE_URL`).

```bash
export TURBO_OCR_BASE_URL=http://localhost:8000  # optional, this is the default
python examples/00_quickstart.py
python examples/02_pdf_to_markdown.py
```

| # | Example | What it shows | README section |
|---|---------|---------------|----------------|
| 00 | [`00_quickstart.py`](00_quickstart.py) | The smallest useful script — sync image OCR. | [Quickstart](../README.md#quickstart) |
| 01 | [`01_image_ocr_with_layout.py`](01_image_ocr_with_layout.py) | Image OCR with `layout`, `reading_order`, `include_blocks`; dump blocks as JSON. | [Image OCR](../README.md#image-ocr) |
| 02 | [`02_pdf_to_markdown.py`](02_pdf_to_markdown.py) | PDF -> Markdown via `render_to_markdown`. | [PDF -> Markdown](../README.md#pdf--markdown) |
| 03 | [`03_searchable_pdf.py`](03_searchable_pdf.py) | Standard searchable PDF plus optional PDF/A-4 output with `turboocr[pdfa]`; both verified with `pypdf`. | [Searchable PDF](../README.md#searchable-pdf) |
| 04 | [`04_async_client.py`](04_async_client.py) | `AsyncClient` + `asyncio.gather` for concurrent OCR. | [Async](../README.md#async) |
| 05 | [`05_batch.py`](05_batch.py) | `recognize_batch` over multiple images. | [Batch](../README.md#batch) |
| 06 | [`06_grpc.py`](06_grpc.py) | `GrpcClient` — same surface as `Client`, gRPC transport. | [gRPC](../README.md#grpc) |
| 07 | [`07_retry_and_timeout.py`](07_retry_and_timeout.py) | Custom `RetryPolicy` + per-request `timeout=`. | [Retry policy](../README.md#retry-policy) |
| 08 | [`08_custom_httpx_client.py`](08_custom_httpx_client.py) | Pass your own `httpx.Client` for TLS / limits. | [Custom httpx.Client](../README.md#custom-httpxclient) |
| 09 | [`09_markdown_style.py`](09_markdown_style.py) | Register a custom layout label + renderer on `MarkdownStyle`. | [Custom Markdown labels](../README.md#custom-markdown-labels) |
| 10 | [`10_tables_and_formulas.py`](10_tables_and_formulas.py) | Iterate `response.tables` / `response.formulas` — see caveat below. | [Tables and formulas](../README.md#tables-and-formulas) |
| 11 | [`11_folder_pipeline.py`](11_folder_pipeline.py) | AsyncClient + `asyncio.Semaphore` for a bounded-concurrency folder pipeline. | — |
| 12 | [`12_hooks_and_logging.py`](12_hooks_and_logging.py) | httpx event hooks + the SDK's stdlib logger. | [Logging](../README.md#logging) |

> **Tables and formulas — partial support today.** As of server v2.2.3, the
> server detects table and formula *regions* (you get a `bounding_box` and
> row-major OCR'd `text`) but does **not** emit cell structure or LaTeX
> source. `Table.html`, `Table.cells`, and `Formula.latex` are always `None`
> in the current responses. The SDK is forward-compatible: when the server
> ships table-structure-recognition and LaTeX OCR, those fields will
> populate without any SDK code changes.

## Sample fixtures

`sample/acme_invoice.pdf` and `sample/acme_invoice.png` are a fictional
two-page ACME Corp invoice (line items, totals, terms). They're committed
so the examples run out of the box; regenerate with:

```bash
python examples/sample/generate.py
```

Requires `reportlab` and `pypdfium2`. `reportlab` ships with the default SDK
install; `pypdfium2` is included in the `dev` and `pdfa` extras.
