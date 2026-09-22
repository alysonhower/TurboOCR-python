# Errors

## Hierarchy

```
TurboOcrError
├── APIConnectionError       # transport-level
│   ├── Timeout
│   ├── NetworkError
│   └── ProtocolError
├── InvalidParameter         # 4xx: bad params / headers / dims
├── EmptyBody                # 4xx: empty body / batch / PDF
├── LayoutDisabled           # asked for layout when server has it off
├── ImageDecodeError         # bad bytes / bad base64
├── DimensionsTooLarge       # image / PDF over server limits
├── PoolExhausted            # "Server at capacity"
├── PdfRenderError           # PDF rasterization failed
└── ServerError              # 5xx, no specific code
```

Server-side exceptions carry `.code`, `.status_code`, and `.payload`. Transport
exceptions inherit from `APIConnectionError`.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `NetworkError: Connection refused` | server not running | start the docker container |
| `DimensionsTooLarge` | image > `MAX_IMAGE_DIM` (default 16384) | downscale or raise the server limit |
| `LayoutDisabled` | server started with `DISABLE_LAYOUT=1` | restart without that env var |
| `PoolExhausted` | server queue full | retry with backoff, or scale `PIPELINE_POOL_SIZE` |
| `Timeout` | per-request timeout hit | pass `timeout=N` or raise `RetryPolicy.attempts` |

## Reference

::: turboocr.TurboOcrError

::: turboocr.APIConnectionError

::: turboocr.NetworkError

::: turboocr.Timeout

::: turboocr.ProtocolError

::: turboocr.InvalidParameter

::: turboocr.EmptyBody

::: turboocr.BackendDisabled

::: turboocr.LayoutDisabled

::: turboocr.ImageDecodeError

::: turboocr.DimensionsTooLarge

::: turboocr.PoolExhausted

::: turboocr.PdfRenderError

::: turboocr.InferenceTimeout

::: turboocr.ServerError
