from typing import Callable, Sequence

from starlette.datastructures import URL
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp


class AllowedHostsMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates the Host header against a list of allowed hosts.
    Similar to Django's ALLOWED_HOSTS validation.

    Also extracts the client IP address from the request, handling proxy headers
    like X-Forwarded-For.
    """

    def __init__(
        self,
        app: ASGIApp,
        allowed_hosts: Sequence[str] = ("*",),
        www_redirect: bool = True,
        on_error: Callable[[Request, str], Response] | None = None,
    ) -> None:
        super().__init__(app)
        # Normalize allowed hosts to lowercase
        self.allowed_hosts = [host.lower() for host in allowed_hosts]
        self.www_redirect = www_redirect
        self.on_error = on_error or self._default_error_response

    @staticmethod
    def _default_error_response(request: Request, host: str) -> Response:
        """Default error response for disallowed hosts."""
        return PlainTextResponse("Invalid host header", status_code=400)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request and validate the host."""
        # Get and validate the host
        host = self.get_host(request)

        if not self.is_valid_host(host):
            return self.on_error(request, host)

        # Get the client IP and store it on request.state for later use
        request.state.client_ip = self.get_client_ip(request)

        # Handle www redirect if configured
        if self.www_redirect and self.should_redirect_to_www(host):
            url = URL(scope=request.scope)
            redirect_url = url.replace(netloc=f"www.{host}")
            return Response(
                status_code=307,
                headers={"Location": str(redirect_url)},
            )

        response = await call_next(request)
        return response

    def get_host(self, request: Request) -> str:
        """
        Return the HTTP host using the algorithm from PEP 333.

        Similar to Django's HttpRequest.get_host():
        - First checks X-Forwarded-Host header (for reverse proxy setups)
        - Falls back to Host header
        - Removes port number if present
        - Returns lowercase host

        Reference: Django documentation on HttpRequest.META
        - HTTP_HOST: The HTTP Host header sent by the client
        - HTTP_X_FORWARDED_HOST: Set by reverse proxies
        """
        # Check X-Forwarded-Host first (set by reverse proxies)
        x_forwarded_host = request.headers.get("x-forwarded-host")
        if x_forwarded_host:
            # Take the first host if multiple are provided (comma-separated)
            host = x_forwarded_host.split(",")[0].strip()
        else:
            # Fallback to the Host header
            host = request.headers.get("host", "")

        # Strip the port number if present
        # Handle both IPv4 (host:port) and IPv6 ([host]:port) formats
        host = self._strip_port(host)

        return host.lower()

    def _strip_port(self, host: str) -> str:
        """
        Strip the port from the host.

        Handles:
        - IPv4: 'example.com:8000' -> 'example.com'
        - IPv6: '[::1]:8000' -> '[::1]'
        """
        # Check for IPv6 format [host]:port
        if host.startswith("["):
            # IPv6 address - find the closing bracket
            bracket_pos = host.find("]")
            if bracket_pos != -1:
                # Return everything up to and including the bracket
                return host[: bracket_pos + 1]

        # IPv4 or hostname - split on the last colon
        # Use rsplit to handle IPv6 addresses without brackets correctly
        if ":" in host and not host.startswith("["):
            # For non-bracketed addresses, only strip if it looks like a port
            parts = host.rsplit(":", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return parts[0]

        return host

    def get_client_ip(self, request: Request) -> str:
        """
        Get the client IP address from the request.

        Similar to how Django handles REMOTE_ADDR and X-Forwarded-For:
        - First checks X-Forwarded-For header (for proxied requests)
        - Falls back to the direct client connection (REMOTE_ADDR equivalent)

        Reference: Django documentation on HttpRequest.META
        - REMOTE_ADDR: The IP address of the client
        - HTTP_X_FORWARDED_FOR: Set by proxies, contains comma-separated IPs

        The X-Forwarded-For header format is: client, proxy1, proxy2, ...
        The leftmost IP is the original client IP.
        """
        # Check X-Forwarded-For header first (set by proxies/load balancers)
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            # The header can contain multiple IPs: "client, proxy1, proxy2"
            # The first (leftmost) IP is the original client
            client_ip = x_forwarded_for.split(",")[0].strip()
            return client_ip

        # Check X-Real-IP header (used by some proxies like Nginx)
        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip:
            return x_real_ip.strip()

        # Fallback to direct client connection (equivalent to REMOTE_ADDR)
        if request.client:
            return request.client.host

        return ""

    def is_valid_host(self, host: str) -> bool:
        """
        Check if the host is valid against the allowed hosts list.

        Supports:
        - Exact matches: 'example.com'
        - Wildcard subdomains: '.example.com' matches 'sub.example.com'
        - Wildcard all: '*' matches any host
        """
        if not host:
            return False

        # Wildcard allows any host
        if "*" in self.allowed_hosts:
            return True

        # Normalize the host for comparison
        host = host.lower()

        for allowed_host in self.allowed_hosts:
            if allowed_host == host:
                # Exact match
                return True

            if allowed_host.startswith("."):
                # Subdomain wildcard: '.example.com' matches 'sub.example.com'
                # Also matches 'example.com' itself
                domain = allowed_host[1:]  # Remove leading dot
                if host == domain or host.endswith(allowed_host):
                    return True

        return False

    def should_redirect_to_www(self, host: str) -> bool:
        """
        Check if the request should be redirected to the www subdomain.

        Only redirects if:
        - www_redirect is enabled
        - Host doesn't already start with 'www.'
        - 'www.{host}' is in allowed_hosts
        """
        if host.startswith("www."):
            return False

        www_host = f"www.{host}"
        return www_host in self.allowed_hosts or f".{host}" in self.allowed_hosts
