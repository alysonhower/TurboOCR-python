# Get started

Typed Python client for the [TurboOCR](https://github.com/aiptimizer/TurboOCR)
server. Sync + async, HTTP + gRPC, layout-aware Markdown rendering,
searchable-PDF generation.

This page is the entire usage surface in one read. Pick the section that
matches what you want to do, copy the code, run it.

## Install

```bash
pip install turboocr             # HTTP + CLI + searchable-PDF
pip install 'turboocr[grpc]'     # add the gRPC transport
pip install 'turboocr[pdfa]'     # add PDF/A-4 searchable-PDF generation
pip install 'turboocr[all]'      # everything optional
```

Requires Python 3.12+.

## The three things you'll do 90% of the time

| Task | One-liner | Full snippet below |
|---|---|---|
| Image → text | `client.recognize_image("page.png")` | [Image OCR](#image-text-layout) |
| PDF → Markdown | `render_to_markdown(client.recognize_pdf("doc.pdf")).markdown` | [PDF to Markdown](#pdf-markdown) |
| PDF or image → searchable PDF | `client.make_searchable_pdf("scan.jpg")` | [Searchable PDF](#searchable-pdf) |

## Start a server

The client talks to a TurboOCR server (the OCR engine itself). Easiest
way to get one running:

```bash
docker run --gpus all -p 8000:8000 -p 50051:50051 \
  -v trt-cache:/home/ocr/.cache/turbo-ocr \
  -e OCR_LANG=latin \
  ghcr.io/aiptimizer/turboocr:v2.2.3
```

`OCR_LANG=latin` covers English, French, German, Spanish, …. Swap for
`chinese`, `greek`, `eslav`, `arabic`, `korean`, or `thai` — all baked in.
The first start primes the TRT engine cache (~30 s); subsequent starts
are instant.

## Image → text & layout

```python
from turboocr import Client

with Client(base_url="http://localhost:8000") as client:
    response = client.recognize_image("page.png")

print(f"{len(response.results)} text items")
for item in response.results[:3]:
    print(f"  {item.text!r} (conf={item.confidence:.2f})")
```

`response.results` is a list of [`TextItem`][turboocr.TextItem]s. Each has
`.text`, `.confidence`, and `.bounding_box`.

For paragraph grouping + layout classes (`paragraph_title`, `table`,
`formula`, …) and reading order, pass three more flags:

```python
from turboocr import Client

with Client(base_url="http://localhost:8000") as client:
    response = client.recognize_image(
        "page.png",
        layout=True,
        reading_order=True,
        include_blocks=True,
    )

print(f"{len(response.results)} text items, {len(response.blocks)} blocks")
for block in response.blocks:
    x0, y0, x1, y1 = block.bounding_box.aabb
    print(f"  [{block.class_name}] ({x0},{y0})-({x1},{y1})")
    print(f"      {block.content[:80]!r}")
```

`response.blocks` is the reading-order-grouped paragraphs;
`response.layout` is the per-region layout boxes without text grouping.

## PDF → Markdown

```python
from turboocr import Client, render_to_markdown

with Client(base_url="http://localhost:8000") as client:
    response = client.recognize_pdf(
        "report.pdf", dpi=150, include_blocks=True
    )

doc = render_to_markdown(response)
print(f"pages={len(response.pages)} chars={len(doc.markdown)}")
print(doc.markdown[:500])
```

The renderer walks the reading order and maps each layout class to a
Markdown construct (`doc_title` → `# H1`, `display_formula` → `$$ … $$`,
`table` → fenced block, etc.). Customise the mapping with
[`MarkdownStyle`][turboocr.MarkdownStyle] — see
[`examples/09_markdown_style.py`](https://github.com/aiptimizer/TurboOCR-python/blob/main/examples/09_markdown_style.py)
for a runnable demo.

## Searchable PDF

Generate a PDF with an invisible text overlay aligned to page geometry —
selectable, copyable, full-text-searchable in every viewer. Input can be
a PDF *or* a single-page image. Tested against PNG, JPEG, BMP, TIFF,
GIF, and WebP; the SDK detects format via magic bytes and wraps images
into a one-page PDF automatically:

```python
from pathlib import Path
from turboocr import Client

with Client(base_url="http://localhost:8000") as client:
    overlay = client.make_searchable_pdf("scan.pdf", dpi=200)   # PDF in
    # or:
    overlay = client.make_searchable_pdf("photo.jpg", dpi=200)  # image in
    # or, with `pip install 'turboocr[pdfa]'`:
    overlay = client.make_searchable_pdf("scan.pdf", profile="pdfa-4")

Path("scan.searchable.pdf").write_bytes(overlay)
```

Non-Latin scripts (CJK, Arabic, Cyrillic, …) work without setup — the
bundled glyphless font covers every BMP codepoint. See
[Non-Latin PDFs](how-tos/handle_non_latin_pdfs.md) only if you need to
override the default font.

The `pdfa-4` profile regenerates pages from raster images plus invisible
OCR text. It intentionally does not preserve source PDF vectors,
annotations, forms, or bookmarks. Validate archival workflows with a
PDF/A validator such as veraPDF.

## Async

Same surface, `await`-prefixed. Pair with `asyncio.gather` to fan out:

```python
import asyncio
from turboocr import AsyncClient

IMAGES = ["a.png", "b.png", "c.png"]

async def main() -> None:
    async with AsyncClient(base_url="http://localhost:8000") as client:
        responses = await asyncio.gather(
            *(client.recognize_image(img) for img in IMAGES)
        )
    for img, resp in zip(IMAGES, responses, strict=True):
        print(f"{img}: {len(resp.results)} items")

asyncio.run(main())
```

For folder-scale workloads, see the
[folder-pipeline recipe](how-tos/folder_pipeline.md).

## Configuration cheat-sheet

```python
from turboocr import Client, RetryPolicy

client = Client(
    base_url="http://localhost:8000",   # or TURBO_OCR_BASE_URL env
    api_key="sk-...",                   # or TURBO_OCR_API_KEY env
    auth_scheme="bearer",               # "bearer" | "x-api-key"
    timeout=30.0,                       # per-request, seconds
    default_headers={"X-Tenant": "acme"},
    retry=RetryPolicy(attempts=5, backoff=0.5),
)
```

Pass `http_client=httpx.Client(...)` for custom TLS, mTLS, proxies, or
connection limits — see
[Custom httpx.Client](how-tos/use_custom_httpx_client.md).

Retry defaults: HTTP `{429, 502, 503, 504}`, gRPC
`{UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED}`, 3 attempts,
exponential backoff + jitter, `Retry-After` honoured. Tune via
`RetryPolicy(...)` — see [Configure retries](how-tos/configure_retries.md).

## CLI

```bash
turbo-ocr ocr page.png --output markdown
turbo-ocr pdf report.pdf --dpi 150 --output json
turbo-ocr searchable-pdf scan.pdf -o out.pdf --font-path /path/to/font.ttf
turbo-ocr searchable-pdf scan.pdf -o out.pdf --profile pdfa-4
turbo-ocr health --ready
```

`--output` accepts `json | blocks | text | markdown`. Full surface at
[CLI reference](api/cli.md).

## Where to go next

| You want… | Go to |
|---|---|
| A recipe for a specific problem | [How-to guides](how-tos/index.md) |
| A long-form walkthrough | [Tutorials](tutorials/index.md) |
| Method signatures + types | [API reference](api/clients.md) |
| Conceptual background | [Explanation](explanation/index.md) |
| Runnable scripts against bundled fixtures | [Examples](examples.md) |

## Server compatibility

`SERVER_API_VERSION_MIN` and `SERVER_API_VERSION_MAX_EXCLUSIVE` document
the supported server range. Response models use `extra="allow"` so
additive server changes (e.g. a new `request_id` field) are preserved
on `.model_extra` instead of crashing on parse.

## Versioning

Names exported by `turboocr.__all__` are the public API. Underscored
modules (`_core`, `_http`, `_grpc`) are internal and may change at any
time. Pre-1.0, breaking changes are signalled by a minor-version bump;
deprecated public APIs emit `DeprecationWarning` and stay supported for
at least one minor version after deprecation.
