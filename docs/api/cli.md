# CLI — `turbo-ocr`

The `turbo-ocr` command ships with the default install — no extras needed.

```bash
turbo-ocr ocr page.png --output markdown
turbo-ocr pdf doc.pdf --dpi 150 --output json
turbo-ocr searchable-pdf doc.pdf -o out.pdf --font-path /path/to/font.ttf
turbo-ocr searchable-pdf doc.pdf -o out.pdf --profile pdfa-4 --dpi 150
turbo-ocr blocks doc.pdf
turbo-ocr health --ready
```

## Commands

### `turbo-ocr ocr <image>`

Single-image OCR.

| Option | Notes |
|---|---|
| `--output` | `json` (default) · `blocks` · `text` · `markdown` |
| `--base-url` | env: `TURBO_OCR_BASE_URL` (default `http://localhost:8000`) |
| `--api-key` | env: `TURBO_OCR_API_KEY` |
| `--layout / --no-layout` | request layout (default on) |
| `--reading-order` | request reading-order grouping |
| `--include-blocks` | request reading-order-grouped paragraphs |

### `turbo-ocr pdf <pdf>`

PDF OCR.

| Option | Notes |
|---|---|
| `--output` | `json` · `blocks` · `text` · `markdown` |
| `--dpi` | rasterization DPI (default `150`) |
| `--mode` | `ocr` · `text` · `auto` · `auto_verified` · `geometric` |
| `--base-url`, `--api-key`, `--layout`, `--reading-order`, `--include-blocks` | as above |

### `turbo-ocr searchable-pdf <pdf>`

Generate a searchable PDF with an invisible text overlay.

| Option | Notes |
|---|---|
| `-o`, `--out` | output PDF path (required) |
| `--dpi` | rasterization DPI (default `200`, or `150` with `--profile pdfa-4`) |
| `--mode` | `ocr` · `text` · `auto` · `auto_verified` · `geometric` (default `ocr`) |
| `--font-path` | optional custom TTF (default is the bundled glyphless font, covers all BMP) |
| `--profile` | `standard` · `pdfa-4`; `pdfa-4` requires `turboocr[pdfa]` and defaults to 150 DPI |
| `--base-url`, `--api-key` | as above |

### `turbo-ocr blocks <pdf>`

Dump reading-order-grouped blocks as JSON (shortcut for
`pdf --include-blocks --output blocks`).

### `turbo-ocr health [--ready]`

Probe `/healthz`; with `--ready`, also requires the pipeline to be ready.

## Environment

| Variable | Used by |
|---|---|
| `TURBO_OCR_BASE_URL` | every command — default `http://localhost:8000` |
| `TURBO_OCR_API_KEY` | every command — sent as bearer or `X-API-Key` |

Run `turbo-ocr <command> --help` for the live, authoritative option list.
