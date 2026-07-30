"""Domain exceptions."""


class KiloError(Exception):
    """Base class for user-facing Kilo failures."""


class ParseError(KiloError):
    """Raised when a KiCad S-expression cannot be parsed safely."""


class ConflictError(KiloError):
    """Raised when a non-interactive operation requires a user decision."""


class TransactionError(KiloError):
    """Raised when a transactional write or rollback fails."""
