"""Tests for AllowedHostsMiddleware."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from fastapi_allowed_hosts import AllowedHostsMiddleware
from fastapi_allowed_hosts.exceptions import DisallowedHostException
from starlette.responses import Response


def create_app(
    allowed_hosts: list[str],
    www_redirect: bool = True,
    on_error: callable | None = None,
) -> FastAPI:
    """Create a test FastAPI app with the middleware configured."""
    app = FastAPI()

    app.add_middleware(
        AllowedHostsMiddleware,
        allowed_hosts=allowed_hosts,
        www_redirect=www_redirect,
        on_error=on_error,
    )

    @app.get("/")
    async def root(request: Request):
        return {
            "host": request.headers.get("host"),
            "client_ip": request.state.client_ip,
        }

    return app


class TestHostValidation:
    """Tests for host header validation."""

    def test_exact_match_allowed(self):
        """Test that exact host matches are allowed."""
        app = create_app(allowed_hosts=["example.com"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "example.com"})

        assert response.status_code == 200
        assert response.json()["host"] == "example.com"

    def test_exact_match_denied(self):
        """Test that non-matching hosts are denied."""
        app = create_app(allowed_hosts=["example.com"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "evil.com"})

        assert response.status_code == 400
        assert response.text == "Invalid host header"

    def test_wildcard_allows_all(self):
        """Test that '*' allows any host."""
        app = create_app(allowed_hosts=["*"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "anything.com"})

        assert response.status_code == 200

    def test_subdomain_wildcard_matches_subdomain(self):
        """Test that '.example.com' matches subdomains."""
        app = create_app(allowed_hosts=[".example.com"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "api.example.com"})
        assert response.status_code == 200

        response = client.get("/", headers={"host": "sub.api.example.com"})
        assert response.status_code == 200

    def test_subdomain_wildcard_matches_base_domain(self):
        """Test that '.example.com' also matches 'example.com'."""
        app = create_app(allowed_hosts=[".example.com"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "example.com"})

        assert response.status_code == 200

    def test_subdomain_wildcard_does_not_match_other_domains(self):
        """Test that '.example.com' doesn't match 'notexample.com'."""
        app = create_app(allowed_hosts=[".example.com"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "notexample.com"})

        assert response.status_code == 400

    def test_multiple_allowed_hosts(self):
        """Test that multiple allowed hosts work correctly."""
        app = create_app(allowed_hosts=["example.com", "api.example.com", "localhost"])
        client = TestClient(app)

        assert client.get("/", headers={"host": "example.com"}).status_code == 200
        assert client.get("/", headers={"host": "api.example.com"}).status_code == 200
        assert client.get("/", headers={"host": "localhost"}).status_code == 200
        assert client.get("/", headers={"host": "evil.com"}).status_code == 400

    def test_host_is_case_insensitive(self):
        """Test that host matching is case insensitive."""
        app = create_app(allowed_hosts=["example.com"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "EXAMPLE.COM"})

        assert response.status_code == 200

    def test_empty_host_is_denied(self):
        """Test that empty host is denied."""
        app = create_app(allowed_hosts=["example.com"])
        client = TestClient(app)

        response = client.get("/", headers={"host": ""})

        assert response.status_code == 400


class TestPortStripping:
    """Tests for port number stripping from host."""

    def test_strips_port_from_host(self):
        """Test that port numbers are stripped from the host."""
        app = create_app(allowed_hosts=["example.com"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "example.com:8000"})

        assert response.status_code == 200

    def test_strips_port_from_localhost(self):
        """Test that port is stripped from localhost."""
        app = create_app(allowed_hosts=["localhost"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "localhost:3000"})

        assert response.status_code == 200


class TestClientIPExtraction:
    """Tests for client IP extraction."""

    def test_extracts_ip_from_x_forwarded_for(self):
        """Test that client IP is extracted from X-Forwarded-For header."""
        app = create_app(allowed_hosts=["*"])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={
                "host": "example.com",
                "x-forwarded-for": "203.0.113.195",
            },
        )

        assert response.status_code == 200
        assert response.json()["client_ip"] == "203.0.113.195"

    def test_extracts_first_ip_from_x_forwarded_for_chain(self):
        """Test that first IP is extracted from X-Forwarded-For chain."""
        app = create_app(allowed_hosts=["*"])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={
                "host": "example.com",
                "x-forwarded-for": "203.0.113.195, 70.41.3.18, 150.172.238.178",
            },
        )

        assert response.status_code == 200
        assert response.json()["client_ip"] == "203.0.113.195"

    def test_extracts_ip_from_x_real_ip(self):
        """Test that client IP is extracted from X-Real-IP header."""
        app = create_app(allowed_hosts=["*"])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={
                "host": "example.com",
                "x-real-ip": "198.51.100.178",
            },
        )

        assert response.status_code == 200
        assert response.json()["client_ip"] == "198.51.100.178"

    def test_x_forwarded_for_takes_precedence_over_x_real_ip(self):
        """Test that X-Forwarded-For takes precedence over X-Real-IP."""
        app = create_app(allowed_hosts=["*"])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={
                "host": "example.com",
                "x-forwarded-for": "203.0.113.195",
                "x-real-ip": "198.51.100.178",
            },
        )

        assert response.status_code == 200
        assert response.json()["client_ip"] == "203.0.113.195"

    def test_falls_back_to_client_host(self):
        """Test that client IP falls back to direct connection."""
        app = create_app(allowed_hosts=["*"])
        client = TestClient(app)

        response = client.get("/", headers={"host": "example.com"})

        assert response.status_code == 200
        # TestClient uses 'testclient' as the client host
        assert response.json()["client_ip"] is not None


class TestXForwardedHost:
    """Tests for X-Forwarded-Host header handling."""

    def test_uses_x_forwarded_host(self):
        """Test that X-Forwarded-Host is used when present."""
        app = create_app(allowed_hosts=["proxy.example.com"])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={
                "host": "internal.server.local",
                "x-forwarded-host": "proxy.example.com",
            },
        )

        assert response.status_code == 200

    def test_x_forwarded_host_first_value_used(self):
        """Test that first X-Forwarded-Host value is used when multiple."""
        app = create_app(allowed_hosts=["first.example.com"])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={
                "host": "internal.server.local",
                "x-forwarded-host": "first.example.com, second.example.com",
            },
        )

        assert response.status_code == 200

    def test_x_forwarded_host_denied_if_not_allowed(self):
        """Test that X-Forwarded-Host is validated against allowed hosts."""
        app = create_app(allowed_hosts=["allowed.com"])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={
                "host": "allowed.com",
                "x-forwarded-host": "evil.com",
            },
        )

        assert response.status_code == 400


class TestWWWRedirect:
    """Tests for WWW redirect functionality."""

    def test_redirects_to_www_when_configured(self):
        """Test that non-www is redirected to www when www is in allowed hosts."""
        app = create_app(
            allowed_hosts=["example.com", "www.example.com"],
            www_redirect=True,
        )
        client = TestClient(app, follow_redirects=False)

        response = client.get("/", headers={"host": "example.com"})

        assert response.status_code == 307
        assert "www.example.com" in response.headers["location"]

    def test_no_redirect_when_already_www(self):
        """Test that www hosts are not redirected."""
        app = create_app(
            allowed_hosts=["example.com", "www.example.com"],
            www_redirect=True,
        )
        client = TestClient(app)

        response = client.get("/", headers={"host": "www.example.com"})

        assert response.status_code == 200

    def test_no_redirect_when_disabled(self):
        """Test that redirect is disabled when www_redirect=False."""
        app = create_app(
            allowed_hosts=["example.com", "www.example.com"],
            www_redirect=False,
        )
        client = TestClient(app)

        response = client.get("/", headers={"host": "example.com"})

        assert response.status_code == 200

    def test_no_redirect_when_www_not_in_allowed_hosts(self):
        """Test that no redirect happens when www is not in allowed hosts."""
        app = create_app(
            allowed_hosts=["example.com"],
            www_redirect=True,
        )
        client = TestClient(app)

        response = client.get("/", headers={"host": "example.com"})

        assert response.status_code == 200


class TestCustomErrorHandler:
    """Tests for custom error handler functionality."""

    def test_custom_error_handler(self):
        """Test that custom error handler is called for disallowed hosts."""

        def custom_error(request: Request, host: str) -> Response:
            return JSONResponse(
                status_code=403,
                content={"error": "Forbidden", "invalid_host": host},
            )

        app = create_app(
            allowed_hosts=["example.com"],
            on_error=custom_error,
        )
        client = TestClient(app)

        response = client.get("/", headers={"host": "evil.com"})

        assert response.status_code == 403
        assert response.json()["error"] == "Forbidden"
        assert response.json()["invalid_host"] == "evil.com"

    def test_custom_error_handler_receives_request(self):
        """Test that custom error handler receives the request object."""

        def custom_error(request: Request, host: str) -> Response:
            # Access request properties to verify it's valid
            path = request.url.path
            return JSONResponse(
                status_code=400,
                content={"path": path, "host": host},
            )

        app = create_app(
            allowed_hosts=["example.com"],
            on_error=custom_error,
        )
        client = TestClient(app)

        response = client.get("/some/path", headers={"host": "evil.com"})

        assert response.status_code == 400
        assert response.json()["path"] == "/some/path"


class TestDisallowedHostException:
    """Tests for DisallowedHostException."""

    def test_exception_contains_host(self):
        """Test that DisallowedHostException contains the invalid host."""
        exc = DisallowedHostException("evil.com")

        assert exc.host == "evil.com"
        assert "evil.com" in str(exc)

    def test_exception_message(self):
        """Test the exception message format."""
        exc = DisallowedHostException("evil.com")

        assert "evil.com" in exc.message
        assert "allowed hosts" in exc.message.lower()
