# Response models

All response objects are immutable pydantic v2 models with
`extra="allow"` — additive server changes survive a SDK version skew by
landing on `.model_extra` instead of failing parse.

## `OcrResponse`

Returned by `recognize_image()` and `recognize_pixels()`.

::: turboocr.OcrResponse

## `PdfResponse`

Returned by `recognize_pdf()`.

::: turboocr.PdfResponse

::: turboocr.PdfPage

::: turboocr.PdfMode

## `BatchResponse`

Returned by `recognize_batch()`. Per-slot failures are surfaced via
`iter_results()` — use it to walk results without manually zipping
`batch_results` and `errors`.

::: turboocr.BatchResponse

::: turboocr.BatchResult

::: turboocr.BatchSuccess

::: turboocr.BatchFailure

## `HealthStatus`

::: turboocr.HealthStatus

## Capabilities

::: turboocr.Capabilities

::: turboocr.CapabilityFeatures

::: turboocr.CapabilityPdf

::: turboocr.CapabilityLimits

## Server-side Markdown

::: turboocr.MarkdownPagesResponse

::: turboocr.MarkdownPage

## Streaming

::: turboocr.StreamEvent
