__version__ = "0.2.0"
SERVER_API_VERSION_MIN = "2.2.0"
SERVER_API_VERSION_MAX_EXCLUSIVE = "3.0.0"

from ._core.retry import RetryPolicy  # noqa: E402
from ._http.client import AsyncClient, Client  # noqa: E402
from .errors import (  # noqa: E402
    APIConnectionError,
    DimensionsTooLarge,
    EmptyBody,
    ImageDecodeError,
    InvalidParameter,
    LayoutDisabled,
    NetworkError,
    PdfRenderError,
    PoolExhausted,
    ProtocolError,
    ServerError,
    Timeout,
    TurboOcrError,
)
from .markdown import (  # noqa: E402
    MarkdownDocument,
    MarkdownNode,
    MarkdownStyle,
    NodeKind,
    render_to_markdown,
)
from .models import (  # noqa: E402
    BatchFailure,
    BatchResponse,
    BatchResult,
    BatchSuccess,
    Block,
    BoundingBox,
    Formula,
    HealthStatus,
    LayoutBox,
    LayoutLabel,
    OcrResponse,
    PdfMode,
    PdfPage,
    PdfResponse,
    Table,
    TextItem,
)


def supports_server_version(server_version: str) -> bool:
    def _parse(v: str) -> tuple[int, ...]:
        try:
            return tuple(int(p) for p in v.split("."))
        except ValueError as exc:
            raise InvalidParameter(f"invalid version: {v!r}") from exc

    version = _parse(server_version)
    return _parse(SERVER_API_VERSION_MIN) <= version < _parse(SERVER_API_VERSION_MAX_EXCLUSIVE)


__all__ = [
    "SERVER_API_VERSION_MAX_EXCLUSIVE",
    "SERVER_API_VERSION_MIN",
    "APIConnectionError",
    "AsyncClient",
    "BatchFailure",
    "BatchResponse",
    "BatchResult",
    "BatchSuccess",
    "Block",
    "BoundingBox",
    "Client",
    "DimensionsTooLarge",
    "EmptyBody",
    "Formula",
    "HealthStatus",
    "ImageDecodeError",
    "InvalidParameter",
    "LayoutBox",
    "LayoutDisabled",
    "LayoutLabel",
    "MarkdownDocument",
    "MarkdownNode",
    "MarkdownStyle",
    "NetworkError",
    "NodeKind",
    "OcrResponse",
    "PdfMode",
    "PdfPage",
    "PdfRenderError",
    "PdfResponse",
    "PoolExhausted",
    "ProtocolError",
    "RetryPolicy",
    "ServerError",
    "Table",
    "TextItem",
    "Timeout",
    "TurboOcrError",
    "__version__",
    "render_to_markdown",
    "supports_server_version",
]

# pypdf + reportlab ship with the core install, so searchable-PDF exports
# always work. noqa F401: ruff can't see the runtime __all__.extend below.
from .searchable_pdf import (  # noqa: E402, F401
    FontError,
    FontGlyphMissing,
    SearchablePdfProfile,
)

__all__.extend(["FontError", "FontGlyphMissing", "SearchablePdfProfile"])

# gRPC transport is gated behind the [grpc] extra (grpcio + protobuf). We
# probe with find_spec so `import turboocr` succeeds even without
# grpc installed; the actual import of generated stubs happens lazily.
import importlib.util as _importlib_util  # noqa: E402

if _importlib_util.find_spec("grpc") is not None:
    from ._grpc.client import AsyncGrpcClient, GrpcClient  # noqa: F401

    __all__.extend(["AsyncGrpcClient", "GrpcClient"])
