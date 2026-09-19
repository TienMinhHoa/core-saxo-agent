"""Public, fixed reason codes used by the source-response contract."""


class MusicRagError(Exception):
    """Base exception that carries a safe, machine-readable reason code."""

    code = "system_error"


class ValidationError(MusicRagError):
    code = "validation_error"


class AccessDenied(MusicRagError):
    code = "access_denied"


class NotFound(MusicRagError):
    code = "not_found"


class AssetError(MusicRagError):
    code = "asset_invalid"
