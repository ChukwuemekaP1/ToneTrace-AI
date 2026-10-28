"""URL validation and SSRF protection primitives."""

import ipaddress
from urllib.parse import urlsplit

_FORBIDDEN_SSRF_HOSTS: frozenset[str] = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
        "169.254.169.254",
        "0.0.0.0",
    }
)


def validate_safe_external_url(url: str | None) -> str | None:
    """Validate that a supplied URL uses HTTPS and does not target internal/SSRF hosts.

    Rejects:
    - Non-HTTPS schemes (`file://`, `javascript:`, `data:`, `ftp://`, `http://`)
    - Embedded credentials (`user:pass@host`)
    - Loopback, private, link-local, multicast, reserved, or unspecified IP literals
    - Internal hostnames (`localhost`, `*.local`, `*.internal`, `metadata.google.internal`)
    """
    if url is None:
        return None
    cleaned = url.strip()
    if not cleaned:
        return None

    parsed = urlsplit(cleaned)
    if parsed.scheme.lower() != "https":
        raise ValueError("External URLs must use the 'https://' scheme.")

    if parsed.username or parsed.password:
        raise ValueError("External URLs must not contain embedded user credentials.")

    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise ValueError("External URL must contain a valid hostname.")

    if (
        host in _FORBIDDEN_SSRF_HOSTS
        or host.endswith(".local")
        or host.endswith(".internal")
        or host.endswith(".localhost")
    ):
        raise ValueError(f"Forbidden internal or loopback hostname in URL: '{host}'.")

    try:
        ip_obj = ipaddress.ip_address(host)
    except ValueError:
        ip_obj = None

    if ip_obj is not None and (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    ):
        raise ValueError(f"Forbidden private, loopback, or reserved IP address in URL: '{host}'.")

    return cleaned
