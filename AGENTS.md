# Repository Guidelines

## Project Overview

TurboOCR-python is a typed Python SDK for the TurboOCR server. It provides sync and async clients over HTTP and optional gRPC, plus a `turbo-ocr` CLI, layout-aware Markdown rendering, and searchable-PDF generation.

This repository is the Python client only. The OCR engine is the external TurboOCR server, normally reachable at `http://localhost:8000` for HTTP and `localhost:50051` for gRPC.

## Architecture & Data Flow

High-level flow:

1. Public callers import from `src/turboocr/__init__.py` or run the Typer CLI in `src/turboocr/cli.py`.
2. Inputs are normalized in `src/turboocr/_core/content.py` from paths, bytes, file-like objects, iterables, numpy arrays, or PIL images.
3. OCR flags are normalized in `src/turboocr/_core/options.py`; `include_blocks` implies `reading_order`, which implies `layout`.
4. Transport layer builds and sends requests:
   - HTTP: `Client` / `AsyncClient` in `src/turboocr/_http/client.py`, request specs in `src/turboocr/_http/specs.py`.
   - gRPC: `GrpcClient` / `AsyncGrpcClient` in `src/turboocr/_grpc/client.py`, protobuf request builders in `src/turboocr/_grpc/requests.py`.
5. Retry wrappers apply `RetryPolicy` from `src/turboocr/_core/retry.py`; HTTP retries rebuild request kwargs so streamed file bodies replay safely.
6. Responses are parsed into shared Pydantic models in `src/turboocr/models.py`.
7. Optional post-processing:
   - Markdown: `src/turboocr/markdown/render.py` and `src/turboocr/markdown/style.py`.
   - Searchable PDF: `src/turboocr/searchable_pdf.py`, using bundled `src/turboocr/_data/glyphless.ttf`.
     The default `standard` profile preserves the existing ReportLab + pypdf
     overlay path at 200 DPI. The opt-in `pdfa-4` profile uses fpdf2 +
     pypdfium2 to regenerate a PDF/A-4 document from page images plus
     invisible OCR text at 200 DPI by default.

Important architectural patterns:

- HTTP is the default transport; gRPC is optional via the `grpc` extra.
- PDF/A-4 searchable-PDF generation is optional via the `pdfa` extra.
- Sync and async APIs are separate classes, not one polymorphic wrapper.
- HTTP and gRPC map failures into the same exception hierarchy in `src/turboocr/errors.py`.
- gRPC PDF requests cannot support `reading_order=True` because the proto lacks that field; keep this limitation explicit.
- Standard searchable-PDF font registration uses process-global ReportLab state guarded by a lock.
- The PDF/A-4 profile intentionally does not preserve source PDF vectors, annotations, forms, bookmarks, or metadata.
- Response models tolerate additive server fields via Pydantic extra data; avoid breaking forward compatibility.

## Key Directories

- `src/turboocr/` — package source and public SDK implementation.
- `src/turboocr/_core/` — shared auth, input normalization, retry policy, OCR option logic, and version helpers.
- `src/turboocr/_http/` — HTTP clients, request specs, response/error parsing, and HTTP retry behavior.
- `src/turboocr/_grpc/` — optional gRPC clients, channel setup, protobuf request/response adapters, gRPC retry/error mapping, generated stubs.
- `src/turboocr/markdown/` — Markdown document/node rendering and style customization.
- `src/turboocr/_data/` — packaged runtime assets, especially `glyphless.ttf` for searchable PDFs.
- `tests/` — fast offline behavior tests, mostly using `pytest`, `respx`, and `httpx` mocks.
- `tests/_grpc/` — optional gRPC tests with in-process gRPC servers; skips when `grpcio` is unavailable.
- `tests/integration/` — live server smoke tests gated by `TURBO_OCR_BASE_URL` and server health.
- `examples/` — runnable usage examples against bundled sample fixtures.
- `docs/` — MkDocs Material site and mkdocstrings API docs.
- `scripts/` — one-off build/support scripts such as glyphless font generation.
- `.github/workflows/` — CI, release, docs deployment, and release-please automation.

## Development Commands

Environment and package setup:

```bash
uv sync --extra dev
pip install turboocr
pip install 'turboocr[grpc]'
pip install 'turboocr[pdfa]'
pip install 'turboocr[all]'
```

Run the local TurboOCR server for examples or integration tests:

```bash
docker run --gpus all -p 8000:8000 -p 50051:50051 \
  -v trt-cache:/home/ocr/.cache/turbo-ocr \
  -e OCR_LANG=latin \
  ghcr.io/aiptimizer/turboocr:v2.2.3
```

Common checks:

```bash
ruff check .
mypy .
uv run pytest tests -q --ignore=tests/integration
```

Focused test examples:

```bash
uv run pytest tests/test_client.py -q
uv run pytest tests/test_searchable_pdf.py -q
uv run pytest tests/_grpc -q
TURBO_OCR_BASE_URL=http://localhost:8000 uv run pytest tests/integration -v
```

Build and docs:

```bash
uv build
uv run --extra docs mkdocs serve -f docs/mkdocs.yml
uv run --extra docs mkdocs build -f docs/mkdocs.yml
```

CLI examples:

```bash
turbo-ocr ocr page.png --output markdown
turbo-ocr pdf doc.pdf --dpi 150 --output json
turbo-ocr searchable-pdf doc.pdf -o out.pdf --font-path /path/to/font.ttf
turbo-ocr searchable-pdf doc.pdf -o out.pdf --profile pdfa-4
turbo-ocr health --ready
```

## Code Conventions & Common Patterns

Formatting and typing:

- Python `>=3.12`; Ruff target is `py312` with line length 100.
- Ruff selects `E,F,I,N,B,UP,SIM,PL,RUF`; keep existing ignores unless changing the underlying rule violation intentionally.
- Mypy is strict for source code. Tests have type-discipline relief via mypy overrides.
- Prefer explicit typed APIs, small value objects, and stable public re-exports through `src/turboocr/__init__.py`.

Naming and API shape:

- Modules/functions use `snake_case`; public classes use `PascalCase`.
- Public transport classes are `Client`, `AsyncClient`, `GrpcClient`, and `AsyncGrpcClient`.
- Keep sync and async surfaces parallel when adding client methods.
- Keep HTTP and gRPC behavior semantically aligned unless the protocol makes that impossible; document protocol-specific exceptions.

Error handling:

- Raise SDK exceptions from `src/turboocr/errors.py`, rooted at `TurboOcrError`.
- Preserve typed domain errors such as `InvalidParameter`, `ImageDecodeError`, `DimensionsTooLarge`, `LayoutDisabled`, `PoolExhausted`, `PdfRenderError`, and `ServerError`.
- Map transport failures to `APIConnectionError` subclasses such as `Timeout`, `NetworkError`, and `ProtocolError`.
- Preserve `status_code`, `code`, and structured payload data when available.

Async and concurrency:

- Async HTTP uses `httpx.AsyncClient`; async gRPC uses `grpc.aio`.
- Retry sleeps must use the correct sync/async sleep path.
- For bulk OCR, follow the example pattern in `examples/11_folder_pipeline.py`: bound concurrency with `asyncio.Semaphore` and aggregate with `asyncio.gather`.
- Do not introduce unbounded parallel request fan-out.

Data/model patterns:

- Pydantic v2 models in `src/turboocr/models.py` are the shared response contract.
- Tests expect model serialization, alias handling, extra-field tolerance, reading-order text, table/formula synthesis, and PDF aggregation to remain stable.
- Markdown rendering should prefer `include_blocks=True`, `reading_order=True`, and `layout=True` inputs when structure matters.

Release and docs conventions:

- Use Conventional Commits for commit messages.
- Do not edit `pyproject.toml` version, `.release-please-manifest.json`, or `CHANGELOG.md` manually for releases; release-please owns them.
- Docs API pages use MkDocs + mkdocstrings with Google-style docstrings.

## Important Files

- `pyproject.toml` — package metadata, dependencies/extras, console script, Hatch build config, Ruff, mypy, and pytest settings.
- `uv.lock` — locked dependency graph; use uv for reproducible local tooling.
- `README.md` — user-facing install, Docker server quickstart, CLI examples, logging, and testing commands.
- `CONTRIBUTING.md` — branch policy, Conventional Commits, local checks, and release flow.
- `src/turboocr/__init__.py` — public API and compatibility/version helpers.
- `src/turboocr/cli.py` — `turbo-ocr` console entry point.
- `src/turboocr/_http/client.py` — sync/async HTTP client implementation.
- `src/turboocr/_grpc/client.py` — sync/async gRPC client implementation.
- `src/turboocr/models.py` — response and health model contracts.
- `src/turboocr/errors.py` — public exception hierarchy.
- `src/turboocr/markdown/render.py` — OCR/PDF-to-Markdown renderer.
- `src/turboocr/searchable_pdf.py` — searchable-PDF overlay implementation.
- `docs/mkdocs.yml` — docs navigation, mkdocstrings, and versioned docs config.
- `.github/workflows/ci.yml` — PR/push QA matrix for Python 3.12 and 3.13.
- `.github/workflows/release.yml` — tag build/test/publish workflow.
- `release-please-config.json` — release automation and changelog section mapping.

## Runtime/Tooling Preferences

- Runtime: Python 3.12+; CI covers Python 3.12 and 3.13.
- Package/tool runner: prefer `uv` for sync, test, build, and docs commands.
- Build backend: Hatchling.
- Main runtime dependencies: `httpx`, `pydantic`, `typer`, `rich`, `pypdf`, and `reportlab`.
- Optional gRPC dependencies: `grpcio` and `protobuf` under `turboocr[grpc]`.
- Optional PDF/A dependencies: `fpdf2` and `pypdfium2` under `turboocr[pdfa]`.
- Docs tooling: MkDocs Material, mkdocstrings, and mike under the `docs` extra.
- Environment variables used by clients/CLI:
  - `TURBO_OCR_BASE_URL` — server origin, defaulting to localhost behavior in client docs.
  - `TURBO_OCR_API_KEY` — optional auth key.
  - `TURBO_OCR_SAMPLE_IMAGE` — optional integration-test sample override.
- Server language/runtime examples use `OCR_LANG=latin` by default; other server languages are documented in `README.md`.
- The generated gRPC stubs under `src/turboocr/_grpc/_stubs/` are treated as generated code; do not hand-format them.

## Testing & QA

Test stack:

- `pytest` is the primary runner.
- `pytest-asyncio` is configured with `asyncio_mode = "auto"`.
- HTTP tests use `respx` and `httpx` mock transports.
- gRPC tests use in-process `grpc` / `grpc.aio` servers and skip when optional gRPC dependencies are absent.
- Integration tests require a live TurboOCR server and skip when health checks fail.

Behavior covered by tests:

- HTTP auth headers, query params, environment fallbacks, hooks, health endpoints, streaming body replay, retries, and error mapping.
- gRPC metadata, interceptors, retries, status/error mapping, parsing fast paths, and sync/async method parity.
- Pydantic model validation, aliases, extra fields, reading-order text, synthesized tables/formulas, and PDF response aggregation.
- Markdown rendering from blocks, layout/reading-order fallback, protocol-error cases, and PDF page breaks.
- Searchable-PDF round trips, image input formats, page-count mismatches, DPI
  requirements, non-Latin text, degenerate bounding boxes, profile-specific
  default DPI, and PDF/A-4 generation.

QA expectations for changes:

- Run the narrowest relevant `uv run pytest ... -q` command for touched behavior.
- For transport changes, test both sync and async surfaces where applicable.
- For public API changes, update examples/docs and preserve import stability unless intentionally making a breaking change.
- For searchable-PDF changes, include a PDF text-extraction or round-trip
  assertion. For PDF/A-4 profile changes, test the bundled glyphless font path,
  200 DPI default, and PDF input rasterization through pypdfium2.
- For Markdown/layout changes, test both block-based rendering and layout/reading-order fallback.
- Keep integration tests separate from default local checks; they require `TURBO_OCR_BASE_URL` and a running server.
