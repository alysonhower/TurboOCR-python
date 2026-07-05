"""PDF -> searchable PDF profiles, verified with pypdf."""

from io import BytesIO
from pathlib import Path

import pypdf

from turboocr import Client, SearchablePdfProfile

PDF = Path(__file__).parent / "sample" / "acme_invoice.pdf"
OUT = Path("/tmp/acme_invoice_searchable.pdf")
PDFA_OUT = Path("/tmp/acme_invoice_pdfa4_searchable.pdf")

client = Client(timeout=180.0)
overlay = client.make_searchable_pdf(PDF, dpi=200)
OUT.write_bytes(overlay)
print(f"wrote {OUT} ({len(overlay):,} bytes)")

reader = pypdf.PdfReader(BytesIO(overlay))
text = reader.pages[0].extract_text() or ""
print(f"pages in output: {len(reader.pages)}")
print(f"page-1 text length: {len(text)}")
print(f"page-1 text (first 200 chars): {text.strip()[:200]!r}")

try:
    pdfa_overlay = client.make_searchable_pdf(
        PDF,
        profile=SearchablePdfProfile.pdfa_4,
    )
except ImportError as exc:
    print(f"skipped PDF/A-4 output: {exc}")
else:
    PDFA_OUT.write_bytes(pdfa_overlay)
    pdfa_reader = pypdf.PdfReader(BytesIO(pdfa_overlay))
    pdfa_text = pdfa_reader.pages[0].extract_text() or ""
    print(f"wrote {PDFA_OUT} ({len(pdfa_overlay):,} bytes)")
    print(f"PDF/A-4 pages in output: {len(pdfa_reader.pages)}")
    print(f"PDF/A-4 page-1 text length: {len(pdfa_text)}")

# Output:
# wrote /tmp/acme_invoice_searchable.pdf (19,519 bytes)
# pages in output: 2
# page-1 text length: 1758
# page-1 text (first 200 chars): 'ACME Corporation\n123 Roadrunner Way, Tumbleweed, AZ 86001\ninvoices@acme.example · +1 (555) 010-0182\nInvoice\nInvoice #\nINV-2026-00482\nIssue date\n2026-04-15\nDue date\n2026-05-15\nCustomer\nCoyote Logistics'
# wrote /tmp/acme_invoice_pdfa4_searchable.pdf (... bytes)
# PDF/A-4 pages in output: 2
# PDF/A-4 page-1 text length: 1758
