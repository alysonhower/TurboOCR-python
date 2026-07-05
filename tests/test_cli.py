from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from turboocr import cli
from turboocr.searchable_pdf import SearchablePdfProfile


def test_searchable_pdf_cli_accepts_pdfa4_profile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def make_searchable_pdf(self, source: Path, **kwargs: object) -> bytes:
            captured["source"] = source
            captured.update(kwargs)
            return b"%PDF-2.0\n"

    monkeypatch.setattr(cli, "_build_client", lambda base_url, api_key: FakeClient())
    src = tmp_path / "scan.pdf"
    out = tmp_path / "out.pdf"
    src.write_bytes(b"%PDF-1.7\n")

    result = CliRunner().invoke(
        cli.app,
        [
            "searchable-pdf",
            str(src),
            "--out",
            str(out),
            "--profile",
            "pdfa-4",
            "--dpi",
            "150",
        ],
    )

    assert result.exit_code == 0
    assert out.read_bytes() == b"%PDF-2.0\n"
    assert captured["dpi"] == 150
    assert captured["profile"] is SearchablePdfProfile.pdfa_4
