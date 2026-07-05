from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import as_file, files
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast

import pypdf
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from .errors import ProtocolError
from .models import OcrResponse, PdfPage, PdfResponse, TextItem

if TYPE_CHECKING:
    from fpdf import FPDF
    from fpdf.enums import DocumentCompliance
    from PIL.Image import Image as PILImage
    from reportlab.pdfgen.canvas import Canvas


logger = logging.getLogger("turboocr.searchable_pdf")

PDF_POINTS_PER_INCH: Final[float] = 72.0
INVISIBLE_TEXT_MODE: Final[int] = 3
DEFAULT_STANDARD_DPI: Final[int] = 200
DEFAULT_PDFA_DPI: Final[int] = 200

# Bundled glyphless font: one zero-mark glyph that every BMP codepoint
# (U+0001..U+FFFF) maps to. Same trick Tesseract's GlyphLessFont uses —
# the visible page is the original scan, so the font is only needed so
# PDF readers can compute text-selection bboxes. ~760 bytes; ships in
# the wheel via package-data.
GLYPHLESS_FONT_NAME: Final[str] = "TurboOcrGlyphless"
_GLYPHLESS_FONT_FILE: Final[str] = "glyphless.ttf"

# reportlab's pdfmetrics holds a process-wide global font registry. Multiple
# threads calling make_searchable_pdf concurrently would race the check +
# register pair. Lock + idempotent check protects against double registration.
_REGISTRATION_LOCK: Final[threading.Lock] = threading.Lock()


_PDF_MAGIC: Final[bytes] = b"%PDF-"


class SearchablePdfProfile(StrEnum):
    """Searchable PDF generation profile."""

    standard = "standard"
    pdfa_4 = "pdfa-4"


@dataclass(frozen=True, slots=True)
class _OverlayPage:
    width_pt: float
    height_pt: float
    dpi: int
    items: list[TextItem]


@dataclass(frozen=True, slots=True)
class _RasterPage:
    image: PILImage
    width_pt: float
    height_pt: float


class _ImageModule(Protocol):
    def open(self, fp: BytesIO) -> PILImage: ...


class _PdfBitmap(Protocol):
    def to_pil(self) -> PILImage: ...


class _PdfPage(Protocol):
    def get_size(self) -> tuple[float, float]: ...

    def render(self, *, scale: float) -> _PdfBitmap: ...


class _PdfDocument(Protocol):
    def __len__(self) -> int: ...

    def __getitem__(self, index: int) -> _PdfPage: ...

    def close(self) -> None: ...


class _PdfDocumentFactory(Protocol):
    def __call__(self, source: bytes) -> _PdfDocument: ...


class _PdfiumModule(Protocol):
    PdfDocument: _PdfDocumentFactory


class _VariablePageFpdf(Protocol):
    def add_page(self, *, format: tuple[float, float]) -> None: ...


class MissingPdfAExtra(ImportError):
    """Raised when PDF/A generation dependencies are not installed."""


def _pdfa_extra_error() -> MissingPdfAExtra:
    return MissingPdfAExtra(
        "install turboocr[pdfa] to generate PDF/A-4 searchable PDFs"
    )


def _wrap_image_as_pdf(image_bytes: bytes, *, dpi: int) -> bytes:
    """Wrap a single image (JPEG/PNG/TIFF/BMP/…) as a one-page PDF.

    The page is sized so that the image fills it at the given DPI:
    `page_width_pt = pixels * 72 / dpi`. The image is drawn at full
    bleed so the OCR bounding boxes (which are in pixel coordinates at
    the source resolution) land in the right place.
    """
    reader = ImageReader(BytesIO(image_bytes))
    width_px, height_px = reader.getSize()
    width_pt = width_px * PDF_POINTS_PER_INCH / dpi
    height_pt = height_px * PDF_POINTS_PER_INCH / dpi
    buf = BytesIO()
    canvas = rl_canvas.Canvas(buf, pagesize=(width_pt, height_pt))
    canvas.drawImage(reader, 0, 0, width=width_pt, height=height_pt)
    canvas.showPage()
    canvas.save()
    return buf.getvalue()


class FontError(RuntimeError):
    """Raised when a caller-supplied font cannot render the OCR text.

    The default code path never raises this — the bundled glyphless font
    covers every Basic Multilingual Plane codepoint. You can only hit it
    by passing `font_path=<my.ttf>` to a font that lacks glyphs the OCR
    text needs.
    """


class FontGlyphMissing(FontError):
    """A user-supplied font has no glyph for some OCR character."""


def _register_glyphless_font() -> str:
    """Register the bundled glyphless TTF with reportlab. Idempotent."""
    with _REGISTRATION_LOCK:
        if GLYPHLESS_FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return GLYPHLESS_FONT_NAME
        font_resource = files("turboocr._data").joinpath(_GLYPHLESS_FONT_FILE)
        with as_file(font_resource) as font_path:
            pdfmetrics.registerFont(TTFont(GLYPHLESS_FONT_NAME, str(font_path)))
    return GLYPHLESS_FONT_NAME


def _register_custom_font(font_path: str) -> str:
    """Register a user-supplied TTF under its file stem."""
    name = Path(font_path).stem or "TurboOcrCustomFont"
    with _REGISTRATION_LOCK:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, font_path))
    return name


def _resolve_font(font_path: str | None) -> str:
    if font_path:
        logger.debug("turbo-ocr searchable_pdf using custom font %s", font_path)
        return _register_custom_font(font_path)
    return _register_glyphless_font()


@contextlib.contextmanager
def _resolved_font_path(font_path: str | None) -> Iterator[tuple[str, str | Path]]:
    if font_path:
        logger.debug("turbo-ocr searchable_pdf using custom font %s", font_path)
        yield Path(font_path).stem or "TurboOcrCustomFont", font_path
        return
    font_resource = files("turboocr._data").joinpath(_GLYPHLESS_FONT_FILE)
    with as_file(font_resource) as path:
        yield GLYPHLESS_FONT_NAME, Path(path)


def _draw_invisible_item(
    canvas: Canvas, item: TextItem, *, font_name: str, dpi: int, page_height_pt: float
) -> None:
    if not item.text.strip():
        logger.debug("skipping whitespace-only OCR item id=%s", item.id)
        return
    x0, y0, x1, y1 = item.bounding_box.aabb
    box_w_pt = _px_to_pt(x1 - x0, dpi)
    box_h_pt = _px_to_pt(y1 - y0, dpi)
    if box_w_pt <= 0 or box_h_pt <= 0:
        raise ProtocolError(
            f"degenerate bbox {item.bounding_box.aabb} for OCR item id={item.id}"
        )

    text_pt_x = _px_to_pt(x0, dpi)
    text_pt_y = page_height_pt - _px_to_pt(y1, dpi)
    font_size = max(1.0, box_h_pt * 0.9)
    canvas.setFont(font_name, font_size)
    text_width = canvas.stringWidth(item.text, font_name, font_size)
    if text_width <= 0:
        raise FontGlyphMissing(
            f"font {font_name!r} cannot render OCR item id={item.id} "
            f"(text={item.text!r}); drop the font_path= override to fall "
            "back to the bundled glyphless font"
        )

    canvas.saveState()
    canvas.translate(text_pt_x, text_pt_y)
    canvas.scale(box_w_pt / text_width, 1.0)
    text_obj = canvas.beginText(0, 0)
    text_obj.setTextRenderMode(INVISIBLE_TEXT_MODE)
    text_obj.textOut(item.text)
    canvas.drawText(text_obj)
    canvas.restoreState()


def _draw_invisible_item_fpdf(
    pdf: FPDF, item: TextItem, *, font_name: str, dpi: int
) -> None:
    if not item.text.strip():
        logger.debug("skipping whitespace-only OCR item id=%s", item.id)
        return
    x0, y0, x1, y1 = item.bounding_box.aabb
    box_w_pt = _px_to_pt(x1 - x0, dpi)
    box_h_pt = _px_to_pt(y1 - y0, dpi)
    if box_w_pt <= 0 or box_h_pt <= 0:
        raise ProtocolError(
            f"degenerate bbox {item.bounding_box.aabb} for OCR item id={item.id}"
        )

    font_size = max(1.0, box_h_pt * 0.9)
    pdf.set_font(font_name, size=font_size)
    text_width = pdf.get_string_width(item.text)
    if text_width <= 0:
        raise FontGlyphMissing(
            f"font {font_name!r} cannot render OCR item id={item.id} "
            f"(text={item.text!r}); drop the font_path= override to fall "
            "back to the bundled glyphless font"
        )

    from fpdf.enums import TextMode

    text_pt_x = _px_to_pt(x0, dpi)
    text_pt_y = _px_to_pt(y1, dpi)
    stretching = 100.0 * box_w_pt / text_width
    with pdf.local_context(text_mode=TextMode.INVISIBLE, font_stretching=stretching):
        pdf.text(text_pt_x, text_pt_y, text=item.text)


def _px_to_pt(px: float, dpi: int) -> float:
    return px * PDF_POINTS_PER_INCH / dpi


def _build_overlay_pdf(pages: list[_OverlayPage], font_name: str) -> bytes:
    buffer = BytesIO()
    pdf = rl_canvas.Canvas(buffer)
    for page in pages:
        pdf.setPageSize((page.width_pt, page.height_pt))
        for item in page.items:
            _draw_invisible_item(
                pdf, item, font_name=font_name, dpi=page.dpi, page_height_pt=page.height_pt
            )
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _items_for_page(page: PdfPage) -> list[TextItem]:
    """Order a page's text items by reading_order, falling back to natural order.

    Validates that reading_order is a complete permutation of result indices
    (every index present exactly once). On any drift — out-of-range index,
    duplicate, or missing index — logs a warning and returns the unordered
    `page.results` list. Silently using a partial reading_order would lose or
    duplicate text in the invisible PDF layer.
    """
    if not page.reading_order:
        return list(page.results)
    n = len(page.results)
    if sorted(page.reading_order) != list(range(n)):
        logger.warning(
            "page %d reading_order is not a permutation of results "
            "(len=%d, results=%d) — falling back to natural order to avoid "
            "lost/duplicated text",
            page.page, len(page.reading_order), n,
        )
        return list(page.results)
    return [page.results[i] for i in page.reading_order]


def _profile_value(profile: SearchablePdfProfile | str) -> SearchablePdfProfile:
    try:
        return SearchablePdfProfile(profile)
    except ValueError as exc:
        allowed = ", ".join(p.value for p in SearchablePdfProfile)
        raise ValueError(f"invalid searchable PDF profile {profile!r}; expected {allowed}") from exc


def default_dpi_for_profile(profile: SearchablePdfProfile | str) -> int:
    """Return the SDK default DPI for a searchable PDF profile."""

    if _profile_value(profile) is SearchablePdfProfile.pdfa_4:
        return DEFAULT_PDFA_DPI
    return DEFAULT_STANDARD_DPI


def _coerce_to_pdf_response(
    response: PdfResponse | OcrResponse,
    *,
    dpi: int | None,
    page_width_pt: float | None = None,
    page_height_pt: float | None = None,
) -> PdfResponse:
    if isinstance(response, PdfResponse):
        return response
    if dpi is None:
        raise ValueError("dpi must be provided when overlaying an OcrResponse")
    # Pixel dimensions at the rendered DPI. When called from make_searchable_pdf
    # we pass the source PDF's mediabox so introspection of page.width/height
    # returns truthful values; when called standalone we fall back to 0 — the
    # overlay loop uses mediabox directly and doesn't read these fields.
    width_px = int(page_width_pt * dpi / PDF_POINTS_PER_INCH) if page_width_pt else 0
    height_px = int(page_height_pt * dpi / PDF_POINTS_PER_INCH) if page_height_pt else 0
    return PdfResponse(
        pages=[
            PdfPage(
                page=1,
                page_index=0,
                dpi=dpi,
                width=width_px,
                height=height_px,
                results=response.results,
                layout=response.layout,
                reading_order=response.reading_order,
                blocks=response.blocks,
                mode="ocr",  # type: ignore[arg-type]
                text_layer_quality="ocr",
            )
        ]
    )


def _load_pdfa_dependencies() -> tuple[type[FPDF], type[DocumentCompliance], _PdfiumModule]:
    try:
        import pypdfium2 as pdfium
        from fpdf import FPDF
        from fpdf.enums import DocumentCompliance
    except ImportError as exc:
        raise _pdfa_extra_error() from exc
    return FPDF, DocumentCompliance, cast(_PdfiumModule, pdfium)


def _load_pillow_image() -> _ImageModule:
    try:
        from PIL import Image
    except ImportError as exc:
        raise _pdfa_extra_error() from exc
    return cast(_ImageModule, Image)


def _raster_pages_from_image(original: bytes, *, dpi: int) -> list[_RasterPage]:
    image_cls = _load_pillow_image()
    image = image_cls.open(BytesIO(original))
    if image.mode != "RGB":
        image = image.convert("RGB")
    width_px, height_px = image.size
    return [
        _RasterPage(
            image=image,
            width_pt=_px_to_pt(width_px, dpi),
            height_pt=_px_to_pt(height_px, dpi),
        )
    ]


def _raster_pages_from_pdf(original: bytes, *, dpi: int) -> list[_RasterPage]:
    _, _, pdfium = _load_pdfa_dependencies()
    doc = pdfium.PdfDocument(original)
    scale = dpi / PDF_POINTS_PER_INCH
    pages: list[_RasterPage] = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            width_pt, height_pt = page.get_size()
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            if image.mode != "RGB":
                image = image.convert("RGB")
            pages.append(_RasterPage(image=image, width_pt=width_pt, height_pt=height_pt))
    finally:
        close = getattr(doc, "close", None)
        if callable(close):
            close()
    return pages


def _make_searchable_pdfa4(
    original: bytes,
    response: PdfResponse | OcrResponse,
    *,
    dpi: int,
    font_path: str | None,
) -> bytes:
    fpdf_cls, document_compliance, _ = _load_pdfa_dependencies()
    raster_pages = (
        _raster_pages_from_pdf(original, dpi=dpi)
        if original.startswith(_PDF_MAGIC)
        else _raster_pages_from_image(original, dpi=dpi)
    )
    if isinstance(response, OcrResponse) and raster_pages:
        page = raster_pages[0]
        pdf_response = _coerce_to_pdf_response(
            response,
            dpi=dpi,
            page_width_pt=page.width_pt,
            page_height_pt=page.height_pt,
        )
    else:
        pdf_response = _coerce_to_pdf_response(response, dpi=dpi)
    if len(raster_pages) != len(pdf_response.pages):
        hint = ""
        if isinstance(response, OcrResponse) and len(raster_pages) > 1:
            hint = (
                " — you passed an OcrResponse (single-image OCR) for a "
                "multi-page PDF; call client.recognize_pdf() to get a "
                "PdfResponse instead"
            )
        raise ValueError(
            f"PDF has {len(raster_pages)} pages but OCR response has "
            f"{len(pdf_response.pages)}{hint}"
        )

    items_per_page = [_items_for_page(p) for p in pdf_response.pages]
    pdf = fpdf_cls(unit="pt", enforce_compliance=document_compliance.PDFA_4)
    pdf.set_margins(0, 0, 0)
    pdf.set_auto_page_break(auto=False)
    with _resolved_font_path(font_path) as (font_name, resolved_font_path):
        pdf.add_font(font_name, fname=str(resolved_font_path))

        for raster_page, ocr_page, items in zip(
            raster_pages, pdf_response.pages, items_per_page, strict=True
        ):
            cast(_VariablePageFpdf, pdf).add_page(
                format=(raster_page.width_pt, raster_page.height_pt)
            )
            pdf.image(
                raster_page.image,
                x=0,
                y=0,
                w=raster_page.width_pt,
                h=raster_page.height_pt,
            )
            for item in items:
                _draw_invisible_item_fpdf(
                    pdf,
                    item,
                    font_name=font_name,
                    dpi=ocr_page.dpi,
                )

        return bytes(pdf.output())


def make_searchable_pdf(
    original: bytes,
    response: PdfResponse | OcrResponse,
    *,
    dpi: int | None = None,
    font_path: str | None = None,
    profile: SearchablePdfProfile | str = SearchablePdfProfile.standard,
) -> bytes:
    """Overlay an invisible OCR text layer on the input.

    Accepts a PDF or any single-page image. Tested input formats: PDF,
    PNG, JPEG, BMP, TIFF, GIF, WebP. Image inputs are wrapped into a
    single-page PDF first, sized to the image's pixel dimensions at
    `dpi`. The detection is by magic bytes, so the caller does not
    have to tell the function which format the input is in.

    By default uses a bundled glyphless font that covers every Basic
    Multilingual Plane codepoint, so non-Latin scans (CJK, Arabic, Cyrillic,
    …) work out of the box with zero configuration.

    Pass `font_path=<my.ttf>` only if you have a specific reason to embed a
    real visible font instead.
    """
    resolved_profile = _profile_value(profile)
    if resolved_profile is SearchablePdfProfile.pdfa_4:
        resolved_dpi = dpi if dpi is not None else DEFAULT_PDFA_DPI
        return _make_searchable_pdfa4(
            original,
            response,
            dpi=resolved_dpi,
            font_path=font_path,
        )

    if not original.startswith(_PDF_MAGIC):
        if dpi is None:
            raise ValueError(
                "dpi must be provided when overlaying an image input"
            )
        original = _wrap_image_as_pdf(original, dpi=dpi)
    reader = pypdf.PdfReader(BytesIO(original))
    if isinstance(response, OcrResponse) and reader.pages:
        media = reader.pages[0].mediabox
        pdf_response = _coerce_to_pdf_response(
            response, dpi=dpi,
            page_width_pt=float(media.width),
            page_height_pt=float(media.height),
        )
    else:
        pdf_response = _coerce_to_pdf_response(response, dpi=dpi)
    if len(reader.pages) != len(pdf_response.pages):
        hint = ""
        if isinstance(response, OcrResponse) and len(reader.pages) > 1:
            hint = (
                " — you passed an OcrResponse (single-image OCR) for a "
                "multi-page PDF; call client.recognize_pdf() to get a "
                "PdfResponse instead"
            )
        raise ValueError(
            f"PDF has {len(reader.pages)} pages but OCR response has "
            f"{len(pdf_response.pages)}{hint}"
        )

    items_per_page = [_items_for_page(p) for p in pdf_response.pages]
    font_name = _resolve_font(font_path)

    overlay_pages: list[_OverlayPage] = []
    for original_page, ocr_page, items in zip(
        reader.pages, pdf_response.pages, items_per_page, strict=True
    ):
        media = original_page.mediabox
        overlay_pages.append(
            _OverlayPage(
                width_pt=float(media.width),
                height_pt=float(media.height),
                dpi=ocr_page.dpi,
                items=items,
            )
        )

    overlay_bytes = _build_overlay_pdf(overlay_pages, font_name)
    overlay_reader = pypdf.PdfReader(BytesIO(overlay_bytes))
    writer = pypdf.PdfWriter(clone_from=reader)
    for writer_page, overlay_page in zip(writer.pages, overlay_reader.pages, strict=True):
        writer_page.merge_page(overlay_page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
