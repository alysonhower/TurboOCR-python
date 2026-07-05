# turboocr

Typed Python client for the [TurboOCR](https://github.com/aiptimizer/TurboOCR) server.
Sync + async, HTTP + gRPC, layout-aware Markdown rendering, searchable-PDF generation.

[![PyPI](https://img.shields.io/pypi/v/turboocr.svg?v=1)](https://pypi.org/project/turboocr/)
[![Python](https://img.shields.io/pypi/pyversions/turboocr.svg?v=1)](https://pypi.org/project/turboocr/)
[![Typed](https://img.shields.io/badge/typed-PEP_561-blue.svg)](https://peps.python.org/pep-0561/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

- [Install](#install) · [Quickstart](#quickstart) · [What you get](#what-you-get)
- [Examples](examples/) · [API reference](docs/) · [CLI](#cli) · [Errors](#errors)

## Install

```bash
pip install turboocr             # HTTP client + CLI + searchable-PDF
pip install 'turboocr[grpc]'     # add the gRPC transport
pip install 'turboocr[pdfa]'     # add PDF/A-4 searchable-PDF generation
pip install 'turboocr[all]'      # everything optional
```

Requires Python 3.12+.

## Quickstart

Start a [TurboOCR](https://github.com/aiptimizer/TurboOCR) server (the C++/CUDA
OCR engine — this repo is just the Python client):

```bash
docker run --gpus all -p 8000:8000 -p 50051:50051 \
  -v trt-cache:/home/ocr/.cache/turbo-ocr \
  -e OCR_LANG=latin \
  ghcr.io/aiptimizer/turboocr:v2.2.3
```

`OCR_LANG=latin` (default) covers English, French, German, Spanish, …. Swap for
`chinese`, `greek`, `eslav`, `arabic`, `korean`, or `thai` — all are baked in.
See the [TurboOCR repo](https://github.com/aiptimizer/TurboOCR) for build-from-source,
benchmarks, and the full set of server env vars.

Then recognise an image and turn a PDF into Markdown:

```python
from turboocr import Client, render_to_markdown

with Client(base_url="http://localhost:8000") as client:
    # Image OCR
    img = client.recognize_image("page.png", layout=True, include_blocks=True)
    print(f"{len(img.results)} text items, {len(img.blocks)} blocks")
    print(img.text)

    # PDF → Markdown
    pdf = client.recognize_pdf("paper.pdf", dpi=150, include_blocks=True)
    print(render_to_markdown(pdf).markdown)

    # Searchable PDF (invisible text overlay)
    overlay = client.make_searchable_pdf("scan.pdf", dpi=200)
    open("scan.searchable.pdf", "wb").write(overlay)

    # PDF/A-4 searchable PDF (requires `pip install 'turboocr[pdfa]'`)
    pdfa = client.make_searchable_pdf("scan.pdf", profile="pdfa-4")
    open("scan.pdfa.pdf", "wb").write(pdfa)
```

That's the 80% case. Full runnable examples for async, gRPC, batch, retries,
custom `httpx.Client`, hooks, Markdown styling, folder pipelines, and more live
in [`examples/`](examples/) — every script runs end-to-end against the bundled
ACME invoice fixture.

## What you get

- **Sync + async, HTTP + gRPC.** Four clients (`Client`, `AsyncClient`,
  `GrpcClient`, `AsyncGrpcClient`) with identical method surfaces.
- **Typed, immutable responses (pydantic v2).** IDE autocomplete, and if a newer
  server adds a field your SDK doesn't know about, parsing still succeeds — the
  extra lands on `.model_extra` instead of crashing.
- **Layout-aware Markdown.** `render_to_markdown(...)` walks the reading order
  and maps each layout class (`doc_title`, `display_formula`, `table`, …) to a
  Markdown construct. Pluggable via `MarkdownStyle`.
- **Searchable PDFs.** `make_searchable_pdf(...)` overlays an invisible text
  layer aligned to the page geometry. Auto-discovers a Unicode font for
  non-Latin scripts, or pass `font_path=`. Install `turboocr[pdfa]` and pass
  `profile="pdfa-4"` to regenerate PDF/A-4 output at 200 DPI by default.
- **Production-friendly.** Configurable retry policy (HTTP status + gRPC status
  + `Retry-After`), per-request timeouts, custom `httpx.Client`, `on_request` /
  `on_response` event hooks, uuid7 `X-Request-ID` per call.
- **Precise exception hierarchy.** Maps the server's `error_code` to typed
  exceptions — see [Errors](#errors).
- **`turbo-ocr` CLI** included in the default install.

Today's server does plain OCR + layout classification. Table-structure and
LaTeX-formula source are **not** yet emitted; the SDK exposes `page.tables` /
`page.formulas` as a forward-compatible surface that populates automatically
when those server features ship.

## Configuration

```python
from turboocr import Client, RetryPolicy

client = Client(
    base_url="http://localhost:8000",   # or TURBO_OCR_BASE_URL env
    api_key="sk-...",                   # or TURBO_OCR_API_KEY env
    auth_scheme="bearer",               # "bearer" | "x-api-key"
    timeout=30.0,
    default_headers={"X-Tenant": "acme"},
    retry=RetryPolicy(attempts=5, backoff=0.5),
)
```

Pass `http_client=httpx.Client(...)` for custom TLS, connection limits, or
proxies — see [`examples/08_custom_httpx_client.py`](examples/08_custom_httpx_client.py).

Retry defaults: HTTP `{429, 502, 503, 504}`, gRPC
`{UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED}`, 3 attempts, exponential
backoff + jitter, `Retry-After` honoured. Tune via `RetryPolicy(...)` — see
[`examples/07_retry_and_timeout.py`](examples/07_retry_and_timeout.py).

## Errors

```
TurboOcrError
├── APIConnectionError       # transport-level
│   ├── Timeout
│   ├── NetworkError
│   └── ProtocolError
├── InvalidParameter         # 4xx: bad params / headers / dims
├── EmptyBody                # 4xx: empty body / batch / PDF
├── LayoutDisabled           # asked for layout when server has it off
├── ImageDecodeError         # bad bytes / bad base64
├── DimensionsTooLarge       # image / PDF over server limits
├── PoolExhausted            # "Server at capacity"
├── PdfRenderError           # PDF rasterization failed
└── ServerError              # 5xx, no specific code
```

Server-side exceptions carry `.code`, `.status_code`, and `.payload`. Transport
exceptions inherit from `APIConnectionError`.

| Symptom | Cause | Fix |
|---|---|---|
| `NetworkError: Connection refused` | server not running | start the docker container (above) |
| `DimensionsTooLarge` | image > `MAX_IMAGE_DIM` (default 16384) | downscale, or raise the server limit |
| `LayoutDisabled` | server started with `DISABLE_LAYOUT=1` | restart without that env var |
| `PoolExhausted` | server queue full | retry with backoff, or scale `PIPELINE_POOL_SIZE` |
| `Timeout` | per-request timeout hit | pass `timeout=N`, or raise `RetryPolicy.attempts` |

## CLI

```bash
turbo-ocr ocr page.png --output markdown
turbo-ocr pdf doc.pdf --dpi 150 --output json
turbo-ocr searchable-pdf doc.pdf -o out.pdf --font-path /path/to/font.ttf
turbo-ocr searchable-pdf doc.pdf -o out.pdf --profile pdfa-4
turbo-ocr health --ready
```

`--output` accepts `json | blocks | text | markdown`. Reads `TURBO_OCR_BASE_URL`
and `TURBO_OCR_API_KEY` from the environment. Run `turbo-ocr --help`
for the full surface.

## Logging

```python
import logging
logging.getLogger("turboocr").setLevel(logging.DEBUG)
```

Emits `method path -> status (Xms) [req=<short-id>]` per HTTP request. Retry
warnings go to `turboocr.retry` / `turboocr.grpc.retry`. Searchable-PDF font
resolution logs to `turboocr.searchable_pdf`. Every HTTP request sends a uuid7
`X-Request-ID` header (gRPC uses `x-request-id` metadata).

## Learn more

- [`examples/`](examples/) — 13 runnable scripts (each runs against the bundled
  ACME invoice fixture; the PDF/A-4 searchable-PDF example also needs
  `turboocr[pdfa]`)
- [`docs/`](docs/) — full docs source (MkDocs + mkdocstrings, deployed at
  https://aiptimizer.github.io/TurboOCR-python/). Preview locally with
  `uv run --extra docs mkdocs serve -f docs/mkdocs.yml`
- Server compatibility: `SERVER_API_VERSION_MIN` /
  `SERVER_API_VERSION_MAX_EXCLUSIVE` document the supported server range;
  `extra="allow"` on response models means additive server changes don't break
  parsing

## Testing

```bash
pytest -q                                                # offline (respx)
TURBO_OCR_BASE_URL=http://localhost:8000 pytest tests/integration -v
python examples/03_searchable_pdf.py                         # smoke test
# includes a PDF/A-4 branch when `turboocr[pdfa]` is installed
```

## License

MIT. See [LICENSE](LICENSE).
