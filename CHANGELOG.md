# Changelog

## [0.3.0](https://github.com/aiptimizer/TurboOCR-python/compare/v0.2.0...v0.3.0) (2026-07-15)


### ⚠ BREAKING CHANGES

* supported server range is now >=3.1,<4. Table/Formula models take the server wire shape (id/text optional, cells removed); PdfMode.text is gone (removed server-side); /ocr/pixels sends width/height/channels as query params instead of the deprecated X-Width/X-Height headers.

### Features

* sync client with TurboOCR server v3.x API (tables/formulas, markdown, streaming, capabilities) ([487fb0f](https://github.com/aiptimizer/TurboOCR-python/commit/487fb0f0447ea51e22cc2128c3f6f040ee1cbeb8))


### Bug Fixes

* typed overloads for pdf_markdown so as_pages narrows the return type ([9c23751](https://github.com/aiptimizer/TurboOCR-python/commit/9c2375121c37c2600e3f8cc70bcb67d93cc35873))


### Documentation

* link turboocr.com and add sponsor footer ([a86d8a7](https://github.com/aiptimizer/TurboOCR-python/commit/a86d8a74466f17d585183f59405ef827002d45b1))
* quickstart writes the Markdown export to a file ([bed5856](https://github.com/aiptimizer/TurboOCR-python/commit/bed5856c76a4da021fd4b4db0b49585b7380eaf3))

## [0.2.0](https://github.com/aiptimizer/TurboOCR-python/compare/v0.1.0...v0.2.0) (2026-05-12)


### ⚠ BREAKING CHANGES

* UnicodeFontRequired is no longer in the public API. The default code path never raises a font-discovery error now.

### Features

* bundled glyphless font + image-input auto-detect ([3e07a43](https://github.com/aiptimizer/TurboOCR-python/commit/3e07a439945783fd8b3b05e489b5b00d5d814555))


### Bug Fixes

* **grpc:** merge PdfPage scalars from proto wrapper ([6b40af7](https://github.com/aiptimizer/TurboOCR-python/commit/6b40af72d656922bec469f9d0db1acc1f367a96a))


### Documentation

* drop misleading slow-PDF disclaimers — server is fast ([b5c57f2](https://github.com/aiptimizer/TurboOCR-python/commit/b5c57f2840764acddb7218107323470c7a26597a))
* fix stale repo URL casing + branch references ([238abfa](https://github.com/aiptimizer/TurboOCR-python/commit/238abfa7023458a8b2dcc33d36e47c5e7d167eb7))

## [0.1.0](https://github.com/aiptimizer/TurboOCR-python/compare/v0.1.0...v0.1.0) (2026-05-12)


### Features

* initial release of the turboocr Python SDK ([efa4816](https://github.com/aiptimizer/TurboOCR-python/commit/efa4816fc6f0d58301b92d851d234072c91ff75c))
