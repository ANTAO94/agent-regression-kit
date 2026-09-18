from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, FrozenSet, Tuple


DEFAULT_SECRET_KEYS = frozenset(
    {
        "authorization",
        "proxyauthorization",
        "apikey",
        "token",
        "accesstoken",
        "refreshtoken",
        "password",
        "passwd",
        "secret",
        "secretvalues",
        "cookie",
        "setcookie",
    }
)


@dataclass(frozen=True)
class RedactionPolicy:
    """Recursively redacts sensitive keys and configured literal values."""

    secret_keys: FrozenSet[str] = field(default_factory=lambda: DEFAULT_SECRET_KEYS)
    secret_values: Tuple[str, ...] = ()
    replacement: str = "[REDACTED]"

    def redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self.replacement
                if self._is_secret_key(str(key))
                else self.redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, tuple):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            redacted = value
            for secret in sorted((item for item in self.secret_values if item), key=len, reverse=True):
                redacted = redacted.replace(secret, self.replacement)
            return redacted
        return value

    def _is_secret_key(self, key: str) -> bool:
        normalized = "".join(character for character in key.lower() if character.isalnum())
        return normalized in self.secret_keys


DEFAULT_REDACTION_POLICY = RedactionPolicy()
