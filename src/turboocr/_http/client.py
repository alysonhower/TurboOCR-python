from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from types import MappingProxyType, TracebackType
from typing import Any, Final, NotRequired, Self, TypedDict, TypeVar, Unpack

import httpx
from pydantic import BaseModel

from .._core.auth import build_headers
from .._core.content import ImageInput, read_image_bytes
from .._core.env import DEFAULT_TIMEOUT, AuthScheme, resolve_api_key, resolve_base_url
from .._core.ids import short_request_id
from .._core.options import OcrOptions
from .._core.retry import RetryPolicy
from ..errors import InvalidParameter
from ..markdown import MarkdownDocument, MarkdownStyle, render_to_markdown
from ..models import BatchResponse, HealthStatus, OcrResponse, PdfMode, PdfResponse
from ..searchable_pdf import (
    SearchablePdfProfile,
    default_dpi_for_profile,
)
from ..searchable_pdf import (
    make_searchable_pdf as _overlay,
)
from ._kwargs import _httpx_kwargs, _httpx_kwargs_async
from .retry import execute_with_retries, execute_with_retries_async
from .specs import (
    BoolParam,
    HealthEndpoint,
    RequestSpec,
    health_spec,
    recognize_base64_spec,
    recognize_batch_spec,
    recognize_image_spec,
    recognize_pdf_spec,
    recognize_pixels_spec,
)
from .transport import classify_httpx_error, parse_response

logger = logging.getLogger("turboocr")

T = TypeVar("T", bound=BaseModel)


def _health_status_from(response: httpx.Response) -> HealthStatus:
    body = response.text
    content_type = response.headers.get("Content-Type", "")
    body_json: dict[str, object] | None = None
    if body and "json" in content_type.lower():
        decoded = response.json()
        if isinstance(decoded, dict):
            body_json = decoded
    return HealthStatus(
        ok=response.is_success,
        status_code=response.status_code,
        body=body,
        body_json=body_json,
    )


def _health_endpoint(ready: bool, live: bool) -> HealthEndpoint:
    if ready and live:
        raise InvalidParameter("health(): `ready` and `live` are mutually exclusive")
    if ready:
        return "ready"
    if live:
        return "live"
    return "health"


def _log_request(req_id: str, spec: RequestSpec, status: int, elapsed_ms: float) -> None:
    logger.debug(
        "turbo-ocr %s %s -> %d (%.1fms) [req=%s]",
        spec.method,
        spec.path,
        status,
        elapsed_ms,
        req_id,
    )


DEFAULT_LIMITS: Final[httpx.Limits] = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=15.0,
)


class _BaseClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        auth_scheme: AuthScheme = "bearer",
        timeout: float = DEFAULT_TIMEOUT,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        # Both base_url and api_key fall back to env vars when not passed —
        # so `Client()` and `Client.from_env()` produce identical clients.
        self._base_url = resolve_base_url(base_url).rstrip("/")
        self._auth_scheme: AuthScheme = auth_scheme
        self._default_headers: dict[str, str] = dict(default_headers or {})
        self._headers = build_headers(
            api_key=resolve_api_key(api_key),
            auth_scheme=auth_scheme,
            extra=default_headers,
        )
        self._timeout = timeout
        self._retry = retry if retry is not None else RetryPolicy()

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def auth_scheme(self) -> AuthScheme:
        return self._auth_scheme

    @property
    def default_headers(self) -> Mapping[str, str]:
        # Read-only view so callers can introspect without mutating internals.
        return MappingProxyType(self._default_headers)

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def retry(self) -> RetryPolicy:
        return self._retry

    def _repr_fields(self, kind: str) -> str:
        has_auth = "Authorization" in self._headers or "X-API-Key" in self._headers
        masked = "set" if has_auth else "none"
        return (
            f"{kind}(base_url={self._base_url!r}, "
            f"timeout={self._timeout}, "
            f"auth={self._auth_scheme!r}/{masked}, "
            f"retry=attempts={self._retry.attempts})"
        )


type SyncRequestHook = Callable[[httpx.Request], None]
type SyncResponseHook = Callable[[httpx.Response], None]
type AsyncRequestHook = Callable[[httpx.Request], Awaitable[None]]
type AsyncResponseHook = Callable[[httpx.Response], Awaitable[None]]


class _ClientKwargs(TypedDict, total=False):
    base_url: NotRequired[str | None]
    api_key: NotRequired[str | None]
    auth_scheme: NotRequired[AuthScheme]
    timeout: NotRequired[float]
    default_headers: NotRequired[Mapping[str, str] | None]
    retry: NotRequired[RetryPolicy | None]
    transport: NotRequired[httpx.BaseTransport | None]
    http_client: NotRequired[httpx.Client | None]
    limits: NotRequired[httpx.Limits | None]
    on_request: NotRequired[SyncRequestHook | None]
    on_response: NotRequired[SyncResponseHook | None]


class _AsyncClientKwargs(TypedDict, total=False):
    base_url: NotRequired[str | None]
    api_key: NotRequired[str | None]
    auth_scheme: NotRequired[AuthScheme]
    timeout: NotRequired[float]
    default_headers: NotRequired[Mapping[str, str] | None]
    retry: NotRequired[RetryPolicy | None]
    transport: NotRequired[httpx.AsyncBaseTransport | None]
    http_client: NotRequired[httpx.AsyncClient | None]
    limits: NotRequired[httpx.Limits | None]
    on_request: NotRequired[AsyncRequestHook | None]
    on_response: NotRequired[AsyncResponseHook | None]


class Client(_BaseClient):
    """Synchronous HTTP client for the Turbo-OCR server.

    Holds a pooled `httpx.Client` and the auth / retry configuration used
    by every request method. Prefer instantiating with `with Client(...) as
    client:` so the underlying connection pool is closed deterministically.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        auth_scheme: AuthScheme = "bearer",
        timeout: float = DEFAULT_TIMEOUT,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        http_client: httpx.Client | None = None,
        limits: httpx.Limits | None = None,
        on_request: SyncRequestHook | None = None,
        on_response: SyncResponseHook | None = None,
    ) -> None:
        """Build a `Client` and (unless `http_client` is supplied) its `httpx.Client`.

        Args:
            base_url: Server origin, e.g. `"https://ocr.example.com"`. Falls
                back to the `TURBO_OCR_BASE_URL` env var, and finally to
                `"http://localhost:8000"` when both are absent.
            api_key: Secret used for bearer auth (or `X-API-Key` when
                `auth_scheme="x-api-key"`). Falls back to the
                `TURBO_OCR_API_KEY` env var. May be `None` for unauthenticated
                deployments.
            auth_scheme: `"bearer"` (default) sends `Authorization: Bearer
                <key>`; `"x-api-key"` sends an `X-API-Key` header. May also
                be a custom callable `(api_key) -> (header_name,
                header_value)` for non-standard schemes.
            timeout: Per-request timeout in seconds, applied to the
                underlying `httpx.Client`. Overridable per call via the
                `timeout=` kwarg on each `recognize_*` method.
            default_headers: Extra headers merged into every request (e.g.
                tenant tags, trace IDs). Authorization headers derived from
                `api_key`/`auth_scheme` win on conflict.
            retry: [`RetryPolicy`][turboocr.RetryPolicy] for transient
                failures. Defaults to `RetryPolicy()` (3 attempts, 0.25s
                base backoff with jitter, retrying 429/502/503/504).
            transport: Optional `httpx.BaseTransport` to swap in — useful
                for `httpx.MockTransport` in tests. Ignored when
                `http_client` is also passed.
            http_client: Pre-configured `httpx.Client` to reuse instead of
                letting `Client` build its own. When supplied, `transport`,
                `limits`, `on_request`, `on_response`, and the auth/header
                kwargs only affect the auth dict used per request — the
                provided client's own headers/transport are respected as-is.
            limits: Connection pool sizing. Defaults to `max_connections=100`,
                `max_keepalive_connections=20`, `keepalive_expiry=15.0s`.
            on_request: Synchronous hook `(httpx.Request) -> None` invoked
                before each request is sent. Use for trace propagation or
                logging.
            on_response: Synchronous hook `(httpx.Response) -> None` invoked
                after each response is received.

        Raises:
            InvalidParameter: If `auth_scheme` is unrecognised when
                `api_key` is present.
        """
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            auth_scheme=auth_scheme,
            timeout=timeout,
            default_headers=default_headers,
            retry=retry,
        )
        if http_client is not None:
            self._http = http_client
        else:
            event_hooks: dict[str, list[Callable[..., Any]]] = {}
            if on_request is not None:
                event_hooks["request"] = [on_request]
            if on_response is not None:
                event_hooks["response"] = [on_response]
            self._http = httpx.Client(
                base_url=self._base_url,
                headers=self._headers,
                timeout=timeout,
                transport=transport,
                limits=limits if limits is not None else DEFAULT_LIMITS,
                event_hooks=event_hooks or None,
            )

    def __repr__(self) -> str:
        return self._repr_fields("Client")

    @classmethod
    def from_env(cls, **overrides: Unpack[_ClientKwargs]) -> Self:
        """Construct a `Client` driven by `TURBO_OCR_BASE_URL` / `TURBO_OCR_API_KEY` env vars.

        Plain `Client()` already reads those env vars when the corresponding
        kwarg is `None`. This factory exists for callers who want the
        env-aware origin to be explicit in their code. Pass keyword overrides
        to take precedence over the env values.
        """
        return cls(**overrides)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session. Use the context manager when possible."""
        self._http.close()

    def _send(self, spec: RequestSpec, *, timeout: float | None = None) -> httpx.Response:
        # Body factories are re-invoked per attempt inside this closure, so
        # streamed Path inputs replay correctly across retries.
        def attempt() -> httpx.Response:
            req_id = short_request_id()
            start = time.monotonic()
            kwargs = _httpx_kwargs(spec, request_id=req_id, timeout=timeout)
            response = self._http.request(spec.method, spec.path, **kwargs)
            _log_request(req_id, spec, response.status_code, (time.monotonic() - start) * 1000.0)
            return response

        try:
            return execute_with_retries(
                policy=self._retry,
                method=spec.method,
                path=spec.path,
                attempt_send=attempt,
            )
        except httpx.HTTPError as exc:
            raise classify_httpx_error(exc) from exc

    def _dispatch(self, spec: RequestSpec, model: type[T], *, timeout: float | None = None) -> T:
        return model.model_validate(parse_response(self._send(spec, timeout=timeout)))

    def recognize_image(
        self,
        image: ImageInput,
        *,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> OcrResponse:
        """OCR a single image and return text plus optional layout structure.

        Accepts the broadest possible set of image-shaped inputs: file paths
        (`str` / `Path`), in-memory bytes, file-like objects with `.read()`,
        numpy arrays, and PIL `Image` instances. The bytes are POSTed as
        `multipart/form-data`; image decoding happens server-side.

        Args:
            image: The image to recognize. See
                `ImageInput` for the accepted types.
            layout: Pass `True` to have the server return region
                classifications (titles, paragraphs, tables, formulas, …)
                on `OcrResponse.layout`. Defaults to the server's default
                when `None`.
            reading_order: Pass `True` to receive a `reading_order` list of
                indices into `results` giving human reading order. Requires
                `layout` (implicitly enabled server-side).
            include_blocks: Pass `True` for paragraph-level blocks with
                their reading order on `OcrResponse.blocks` (and synthesises
                `.tables` / `.formulas`).
            timeout: Per-request timeout override in seconds. `None` uses
                the client-level `timeout`.

        Returns:
            An [`OcrResponse`][turboocr.OcrResponse] with `.results` (token
            boxes), plus `.layout`, `.reading_order`, `.blocks`, `.tables`,
            and `.formulas` when requested.

        Raises:
            InvalidParameter: Malformed input (e.g. unsupported image
                format, missing file).
            ImageDecodeError: The server could not decode the bytes as an
                image.
            DimensionsTooLarge: Image exceeds the server's pixel budget.
            APIConnectionError: Network failure, timeout, or unparseable
                response after the retry policy is exhausted.
            ServerError: 5xx response that is not retryable.

        Example:
            ```python
            from turboocr import Client

            with Client(base_url="http://localhost:8000") as client:
                response = client.recognize_image(
                    "invoice.png", layout=True, reading_order=True
                )
                print(response.text)
                for table in response.tables:
                    print(table.text)
            ```
        """
        return self._dispatch(
            recognize_image_spec(image, opts=OcrOptions(layout, reading_order, include_blocks)),
            OcrResponse,
            timeout=timeout,
        )

    def recognize_base64(
        self,
        b64: str,
        *,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> OcrResponse:
        """OCR an image whose bytes are already base64-encoded.

        Useful when the image arrived over a JSON wire and you'd rather not
        round-trip through `b64decode` just to hand it back to the SDK.

        Args:
            b64: Base64-encoded image bytes (the raw payload — no
                `"data:image/..."` URI prefix).
            layout: Same semantics as
                [`recognize_image`][turboocr.Client.recognize_image].
            reading_order: Same semantics as
                [`recognize_image`][turboocr.Client.recognize_image].
            include_blocks: Same semantics as
                [`recognize_image`][turboocr.Client.recognize_image].
            timeout: Per-request timeout override in seconds.

        Returns:
            An [`OcrResponse`][turboocr.OcrResponse], identical in shape to
            what [`recognize_image`][turboocr.Client.recognize_image]
            returns.

        Raises:
            InvalidParameter: Malformed or non-base64 input.
            ImageDecodeError: Decoded bytes are not a valid image.
            APIConnectionError: Network failure, timeout, or unparseable
                response.
            ServerError: 5xx response.
        """
        return self._dispatch(
            recognize_base64_spec(b64, opts=OcrOptions(layout, reading_order, include_blocks)),
            OcrResponse,
            timeout=timeout,
        )

    def recognize_pixels(
        self,
        pixels: ImageInput,
        *,
        width: int,
        height: int,
        channels: int = 3,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> OcrResponse:
        """OCR a raw RGB/RGBA pixel buffer, skipping image-decode on both ends.

        The server's JPEG/PNG decoder is bypassed, which removes ~5-15 ms
        per request for pipelines that already hold uncompressed pixels.

        Args:
            pixels: Raw pixel buffer. Pass `bytes` directly, or anything
                `ImageInput` accepts (numpy
                `.tobytes()`, PIL `Image.tobytes()`, …).
            width: Image width in pixels. Must match the buffer's row
                stride.
            height: Image height in pixels.
            channels: Number of channels per pixel — `3` for RGB
                (default), `4` for RGBA. Other values are rejected by the
                server.
            layout: Same semantics as
                [`recognize_image`][turboocr.Client.recognize_image].
            reading_order: Same semantics as
                [`recognize_image`][turboocr.Client.recognize_image].
            include_blocks: Same semantics as
                [`recognize_image`][turboocr.Client.recognize_image].
            timeout: Per-request timeout override in seconds.

        Returns:
            An [`OcrResponse`][turboocr.OcrResponse].

        Raises:
            InvalidParameter: Dimensions or channel count are invalid, or
                `width * height * channels` does not match the buffer
                length.
            DimensionsTooLarge: Image exceeds the server's pixel budget.
            APIConnectionError: Network failure or timeout.
            ServerError: 5xx response.
        """
        return self._dispatch(
            recognize_pixels_spec(
                pixels,
                width=width,
                height=height,
                channels=channels,
                opts=OcrOptions(layout, reading_order, include_blocks),
            ),
            OcrResponse,
            timeout=timeout,
        )

    def recognize_batch(
        self,
        images: Iterable[ImageInput],
        *,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> BatchResponse:
        """OCR multiple images in a single round-trip.

        Per-slot failures are surfaced on
        [`BatchResponse.errors`][turboocr.BatchResponse] (a parallel
        `list[str | None]`) so one bad input never fails the whole batch.

        Args:
            images: Iterable of image inputs (mixed types are fine —
                paths, bytes, file-like objects, numpy arrays, PIL images
                may all appear in the same batch).
            layout: Applied uniformly to every image. Same semantics as
                [`recognize_image`][turboocr.Client.recognize_image].
            reading_order: Applied uniformly to every image.
            include_blocks: Applied uniformly to every image.
            timeout: Per-request timeout override in seconds.

        Returns:
            A [`BatchResponse`][turboocr.BatchResponse] whose
            `batch_results` and `errors` lists are parallel and the same
            length as `images`. Prefer
            [`BatchResponse.iter_results`][turboocr.BatchResponse.iter_results]
            for tagged `BatchSuccess` / `BatchFailure` iteration instead of
            zipping the two lists by hand.

        Raises:
            ValueError: Empty input. The server rejects empty batches —
                feed at least one image, or skip the call entirely.
            APIConnectionError: Network failure or timeout on the
                round-trip itself (per-slot decode failures land in
                `errors`, not as exceptions).
            ServerError: 5xx response.

        Example:
            ```python
            from turboocr import Client

            with Client() as client:
                batch = client.recognize_batch(["a.png", "b.png", "c.png"])
                for result in batch.iter_results():
                    if isinstance(result, BatchSuccess):
                        print(result.index, result.response.text)
                    else:
                        print(result.index, "failed:", result.error)
            ```
        """
        return self._dispatch(
            recognize_batch_spec(images, opts=OcrOptions(layout, reading_order, include_blocks)),
            BatchResponse,
            timeout=timeout,
        )

    def recognize_pdf(
        self,
        pdf: ImageInput,
        *,
        dpi: int = 150,
        mode: PdfMode | str | None = None,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> PdfResponse:
        """OCR every page of a PDF.

        Args:
            pdf: PDF bytes, path, or file-like object. See
                `ImageInput`.
            dpi: Server-side rasterization DPI (default `150`). Increase to
                `200`-`300` for tiny text; higher values cost proportionally
                more compute.
            mode: PDF reader strategy. One of:

                - `"ocr"` — re-OCR every page, ignoring any embedded text.
                - `"text"` — use the embedded text layer verbatim; no OCR.
                - `"auto"` — server decides per page based on whether a
                  text layer exists.
                - `"auto_verified"` — like `"auto"` but cross-checks the
                  text layer against OCR and falls back to OCR when they
                  disagree.
                - `"geometric"` — skip text recognition and recover only
                  layout / reading order.

                `None` defers to the server default (currently `"auto"`).
                Accepts either the [`PdfMode`][turboocr.PdfMode] enum or
                a plain string.
            layout: Per-page layout. Same semantics as
                [`recognize_image`][turboocr.Client.recognize_image].
            reading_order: Per-page reading order.
            include_blocks: Per-page block grouping.
            timeout: Per-request timeout override in seconds.

        Returns:
            A [`PdfResponse`][turboocr.PdfResponse] with one
            [`PdfPage`][turboocr.PdfPage] per input page and a flattened
            `.text` joiner.

        Raises:
            InvalidParameter: `mode` is not a valid `PdfMode`, or `dpi` is
                out of the server's accepted range.
            PdfRenderError: Server failed to rasterize the PDF (corrupt
                file, encrypted without a password, etc.).
            APIConnectionError: Network failure or timeout.
            ServerError: 5xx response.

        Example:
            ```python
            from turboocr import Client

            with Client() as client:
                response = client.recognize_pdf(
                    "report.pdf", dpi=200, mode="auto_verified"
                )
                for page in response.pages:
                    print(page.page, page.text_layer_quality)
            ```
        """
        return self._dispatch(
            recognize_pdf_spec(
                pdf,
                dpi=dpi,
                mode=mode,
                opts=OcrOptions(layout, reading_order, include_blocks),
            ),
            PdfResponse,
            timeout=timeout,
        )

    def health(self, *, ready: bool = False, live: bool = False) -> HealthStatus:
        """Probe the server's health endpoints.

        Args:
            ready: Hit `/readyz` instead of `/healthz`. `/readyz`
                additionally requires the pipeline pool to be initialised
                and the GPU engines loaded.
            live: Hit `/livez` instead of `/healthz`. `/livez` is the
                cheapest probe — it returns 200 as long as the process is
                up.

        Returns:
            A [`HealthStatus`][turboocr.HealthStatus] carrying the HTTP
            status code, raw body, and (when JSON) the parsed body.

        Raises:
            InvalidParameter: Both `ready` and `live` are `True`.
            APIConnectionError: Network failure or timeout (note: HTTP
                errors are reflected as `status_code` / `ok=False`, not
                exceptions).
        """
        endpoint = _health_endpoint(ready, live)
        response = self._send(health_spec(endpoint=endpoint))
        return _health_status_from(response)

    def make_searchable_pdf(
        self,
        source: ImageInput,
        *,
        dpi: int | None = None,
        mode: PdfMode | str | None = None,
        font_path: str | None = None,
        profile: SearchablePdfProfile | str = SearchablePdfProfile.standard,
    ) -> bytes:
        """Return a PDF with an invisible OCR text layer.

        Accepts a PDF or a single-page image. Tested input formats: PDF,
        PNG, JPEG, BMP, TIFF, GIF, WebP. The SDK detects format from the
        first bytes and dispatches to
        [`recognize_pdf`][turboocr.Client.recognize_pdf] or
        [`recognize_image`][turboocr.Client.recognize_image] accordingly,
        wrapping the image into a one-page PDF when needed.

        Output is visually identical to the input; the text is selectable,
        copyable, and full-text-searchable in every viewer. The bundled
        glyphless font covers every Basic Multilingual Plane codepoint so
        non-Latin scans (CJK, Arabic, Cyrillic, …) work with no font setup.

        Args:
            source: PDF or image bytes / path / file-like object. See
                `ImageInput`.
            dpi: Rasterization DPI for PDF inputs and the page dimension
                used when wrapping an image input. Defaults to `200`.
            mode: PDF reader strategy; see
                [`recognize_pdf`][turboocr.Client.recognize_pdf]. Ignored
                for image inputs. `None` uses the server default.
            font_path: Absolute path to a custom `.ttf`/`.otf` to use
                instead of the bundled glyphless font. Only useful if you
                specifically want a visible-text overlay.
            profile: `standard` preserves the existing overlay behavior.
                `pdfa-4` regenerates the document as PDF/A-4 from page
                images plus invisible OCR text.

        Returns:
            The output PDF as `bytes`, ready to write to disk or stream.

        Raises:
            FontGlyphMissing: Only when you pass a `font_path` to a font
                that lacks glyphs for some of the OCR text. The default
                code path never raises this.
            PdfRenderError: Server failed to rasterize the PDF.
            APIConnectionError: Network failure or timeout on the
                underlying recognise call.
            ServerError: 5xx response.
        """
        raw = read_image_bytes(source)
        resolved_dpi = dpi if dpi is not None else default_dpi_for_profile(profile)
        if raw.startswith(b"%PDF-"):
            response: OcrResponse | PdfResponse = self.recognize_pdf(
                raw, dpi=resolved_dpi, mode=mode
            )
        else:
            response = self.recognize_image(
                raw, layout=True, reading_order=True, include_blocks=True
            )
        return _overlay(raw, response, dpi=resolved_dpi, font_path=font_path, profile=profile)

    def to_markdown(
        self,
        image_or_pdf: ImageInput,
        *,
        dpi: int = 150,
        mode: PdfMode | str | None = None,
        style: MarkdownStyle | None = None,
        timeout: float | None = None,
    ) -> MarkdownDocument:
        """One-call OCR + layout + reading-order + blocks → Markdown.

        Detects PDF vs image by the magic bytes `b"%PDF-"`, then calls
        [`recognize_pdf`][turboocr.Client.recognize_pdf] or
        [`recognize_image`][turboocr.Client.recognize_image] with
        `include_blocks=True` and pipes the response through
        [`render_to_markdown`][turboocr.render_to_markdown].

        Args:
            image_or_pdf: Image or PDF input. See
                `ImageInput`.
            dpi: Rasterization DPI for the PDF branch (default `150`).
                Ignored for images.
            mode: PDF reader strategy for the PDF branch; see
                [`recognize_pdf`][turboocr.Client.recognize_pdf]. Ignored
                for images.
            style: [`MarkdownStyle`][turboocr.MarkdownStyle] controlling
                label-to-node mapping and per-kind renderers. `None` uses
                `DEFAULT_STYLE`.
            timeout: Per-request timeout override in seconds.

        Returns:
            A [`MarkdownDocument`][turboocr.MarkdownDocument] with the
            rendered `.markdown` string and the structured `.nodes` list.

        Raises:
            ProtocolError: Server returned a layout-enabled response with
                inconsistent IDs (text item missing `layout_id`, dangling
                reference to a layout box).
            InvalidParameter: Underlying recognise call rejected the
                input.
            APIConnectionError: Network failure or timeout.
            ServerError: 5xx response.
        """
        body = read_image_bytes(image_or_pdf)
        response: OcrResponse | PdfResponse
        if body[:5] == b"%PDF-":
            response = self.recognize_pdf(
                body, dpi=dpi, mode=mode, include_blocks=True, timeout=timeout
            )
        else:
            response = self.recognize_image(body, include_blocks=True, timeout=timeout)
        return render_to_markdown(response, style=style)


class AsyncClient(_BaseClient):
    """Asynchronous HTTP client for the Turbo-OCR server.

    Mirror of [`Client`][turboocr.Client] over `httpx.AsyncClient`. Every
    request method is the awaitable counterpart of the sync one; see the
    `Client` method for full docs.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        auth_scheme: AuthScheme = "bearer",
        timeout: float = DEFAULT_TIMEOUT,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        http_client: httpx.AsyncClient | None = None,
        limits: httpx.Limits | None = None,
        on_request: AsyncRequestHook | None = None,
        on_response: AsyncResponseHook | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            auth_scheme=auth_scheme,
            timeout=timeout,
            default_headers=default_headers,
            retry=retry,
        )
        if http_client is not None:
            self._http = http_client
        else:
            event_hooks: dict[str, list[Callable[..., Any]]] = {}
            if on_request is not None:
                event_hooks["request"] = [on_request]
            if on_response is not None:
                event_hooks["response"] = [on_response]
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers,
                timeout=timeout,
                transport=transport,
                limits=limits if limits is not None else DEFAULT_LIMITS,
                event_hooks=event_hooks or None,
            )

    def __repr__(self) -> str:
        return self._repr_fields("AsyncClient")

    @classmethod
    def from_env(cls, **overrides: Unpack[_AsyncClientKwargs]) -> Self:
        """Async equivalent of [`Client.from_env`][turboocr.Client.from_env]."""
        return cls(**overrides)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying async HTTP session. Prefer `async with` over this."""
        await self._http.aclose()

    async def _send(self, spec: RequestSpec, *, timeout: float | None = None) -> httpx.Response:
        async def attempt() -> httpx.Response:
            req_id = short_request_id()
            start = time.monotonic()
            kwargs = _httpx_kwargs_async(spec, request_id=req_id, timeout=timeout)
            response = await self._http.request(spec.method, spec.path, **kwargs)
            _log_request(req_id, spec, response.status_code, (time.monotonic() - start) * 1000.0)
            return response

        try:
            return await execute_with_retries_async(
                policy=self._retry,
                method=spec.method,
                path=spec.path,
                attempt_send=attempt,
            )
        except httpx.HTTPError as exc:
            raise classify_httpx_error(exc) from exc

    async def _dispatch(
        self, spec: RequestSpec, model: type[T], *, timeout: float | None = None
    ) -> T:
        return model.model_validate(parse_response(await self._send(spec, timeout=timeout)))

    async def recognize_image(
        self,
        image: ImageInput,
        *,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> OcrResponse:
        """Async equivalent of [`Client.recognize_image`][turboocr.Client.recognize_image]."""
        return await self._dispatch(
            recognize_image_spec(image, opts=OcrOptions(layout, reading_order, include_blocks)),
            OcrResponse,
            timeout=timeout,
        )

    async def recognize_base64(
        self,
        b64: str,
        *,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> OcrResponse:
        """Async equivalent of [`Client.recognize_base64`][turboocr.Client.recognize_base64]."""
        return await self._dispatch(
            recognize_base64_spec(b64, opts=OcrOptions(layout, reading_order, include_blocks)),
            OcrResponse,
            timeout=timeout,
        )

    async def recognize_pixels(
        self,
        pixels: ImageInput,
        *,
        width: int,
        height: int,
        channels: int = 3,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> OcrResponse:
        """Async equivalent of [`Client.recognize_pixels`][turboocr.Client.recognize_pixels]."""
        return await self._dispatch(
            recognize_pixels_spec(
                pixels,
                width=width,
                height=height,
                channels=channels,
                opts=OcrOptions(layout, reading_order, include_blocks),
            ),
            OcrResponse,
            timeout=timeout,
        )

    async def recognize_batch(
        self,
        images: Iterable[ImageInput],
        *,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> BatchResponse:
        """Async equivalent of [`Client.recognize_batch`][turboocr.Client.recognize_batch]."""
        return await self._dispatch(
            recognize_batch_spec(images, opts=OcrOptions(layout, reading_order, include_blocks)),
            BatchResponse,
            timeout=timeout,
        )

    async def recognize_pdf(
        self,
        pdf: ImageInput,
        *,
        dpi: int = 150,
        mode: PdfMode | str | None = None,
        layout: BoolParam = None,
        reading_order: BoolParam = None,
        include_blocks: BoolParam = None,
        timeout: float | None = None,
    ) -> PdfResponse:
        """Async equivalent of [`Client.recognize_pdf`][turboocr.Client.recognize_pdf]."""
        return await self._dispatch(
            recognize_pdf_spec(
                pdf,
                dpi=dpi,
                mode=mode,
                opts=OcrOptions(layout, reading_order, include_blocks),
            ),
            PdfResponse,
            timeout=timeout,
        )

    async def health(self, *, ready: bool = False, live: bool = False) -> HealthStatus:
        """Async equivalent of [`Client.health`][turboocr.Client.health]."""
        endpoint = _health_endpoint(ready, live)
        response = await self._send(health_spec(endpoint=endpoint))
        return _health_status_from(response)

    async def make_searchable_pdf(
        self,
        source: ImageInput,
        *,
        dpi: int | None = None,
        mode: PdfMode | str | None = None,
        font_path: str | None = None,
        profile: SearchablePdfProfile | str = SearchablePdfProfile.standard,
    ) -> bytes:
        """Async equivalent of
        [Client.make_searchable_pdf][turboocr.Client.make_searchable_pdf].
        """
        raw = read_image_bytes(source)
        resolved_dpi = dpi if dpi is not None else default_dpi_for_profile(profile)
        if raw.startswith(b"%PDF-"):
            response: OcrResponse | PdfResponse = await self.recognize_pdf(
                raw, dpi=resolved_dpi, mode=mode
            )
        else:
            response = await self.recognize_image(
                raw, layout=True, reading_order=True, include_blocks=True
            )
        return _overlay(raw, response, dpi=resolved_dpi, font_path=font_path, profile=profile)

    async def to_markdown(
        self,
        image_or_pdf: ImageInput,
        *,
        dpi: int = 150,
        mode: PdfMode | str | None = None,
        style: MarkdownStyle | None = None,
        timeout: float | None = None,
    ) -> MarkdownDocument:
        """Async equivalent of [`Client.to_markdown`][turboocr.Client.to_markdown]."""
        body = read_image_bytes(image_or_pdf)
        response: OcrResponse | PdfResponse
        if body[:5] == b"%PDF-":
            response = await self.recognize_pdf(
                body, dpi=dpi, mode=mode, include_blocks=True, timeout=timeout
            )
        else:
            response = await self.recognize_image(body, include_blocks=True, timeout=timeout)
        return render_to_markdown(response, style=style)
