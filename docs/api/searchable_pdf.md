# Searchable PDF

`Client.make_searchable_pdf(...)` returns a PDF with an invisible OCR
text layer aligned to the original page geometry. Selectable, copyable,
full-text-searchable. Bundled glyphless font covers every BMP codepoint;
no setup needed for non-Latin scripts. Thread-safe.

Install `turboocr[pdfa]` and pass `profile="pdfa-4"` to regenerate a
PDF/A-4 searchable PDF from page images plus invisible OCR text. The
PDF/A-4 profile uses 200 DPI by default and intentionally does not
preserve source PDF vectors, annotations, forms, or bookmarks.

## `Client.make_searchable_pdf`

See [Client.make_searchable_pdf][turboocr.Client.make_searchable_pdf] on
the [Clients](clients.md) page for the full signature.

## `turboocr.searchable_pdf` module

::: turboocr.searchable_pdf.make_searchable_pdf

## Font errors

::: turboocr.FontError

::: turboocr.FontGlyphMissing

## Profiles

::: turboocr.SearchablePdfProfile
