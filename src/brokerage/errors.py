class BrokerageInspectError(Exception):
    """Base error for user-facing failures."""


class PdfPasswordRequiredError(BrokerageInspectError):
    """Raised when a PDF is encrypted and no valid password is available."""


class PdfInvalidPasswordError(BrokerageInspectError):
    """Raised when a supplied PDF password is invalid."""


class UnsupportedBrokerError(BrokerageInspectError):
    """Raised when no parser can handle the extracted text."""
