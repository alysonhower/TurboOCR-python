# Layout, blocks, geometry

## `Block`

Reading-order-grouped paragraph with bounding box, layout class, and content.
Emitted on the response when `include_blocks=True`.

::: turboocr.Block

## `TextItem`

A single recognised word/line with confidence and bounding box.

::: turboocr.TextItem

## `BoundingBox`

::: turboocr.BoundingBox

## `LayoutBox`

::: turboocr.LayoutBox

## `LayoutLabel`

::: turboocr.LayoutLabel

## `Table`

::: turboocr.Table

## `Formula`

::: turboocr.Formula

!!! info "Tables and formulas are strict opt-ins"

    Pass `tables=True` / `formulas=True` (server v3.1+, with
    `TABLE_BACKEND=slanext` / `FORMULA_BACKEND=ppformulanet_s` loaded) and the
    server recognizes structure: `Table.html` carries full `<table>` markup
    and `Formula.latex` the LaTeX source, each with a recognizer
    `confidence`. Without the opt-in the SDK synthesizes region-level
    entries from layout blocks (`text` only; `html` / `latex` stay `None`).
    Requesting a stage the server doesn't have raises `BackendDisabled` —
    check `client.capabilities()` first.
