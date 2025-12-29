# FastAPI Allowed Hosts

A FastAPI middleware that validates the `Host` header against a list of allowed hosts — inspired by Django's `ALLOWED_HOSTS` setting. Protects your application from HTTP Host header attacks and provides easy access to the client's IP address.

## Features

- 🛡️ **Host Header Validation** — Reject requests with invalid or spoofed `Host` headers
- 🌐 **Proxy Support** — Handles `X-Forwarded-Host`, `X-Forwarded-For`, and `X-Real-IP` headers
- 🎯 **Wildcard Matching** — Support for subdomain wildcards (e.g., `.example.com`)
- 🔄 **WWW Redirect** — Optional automatic redirect from `example.com` to `www.example.com`
- 📍 **Client IP Extraction** — Automatically extracts and exposes the real client IP via `request.state.client_ip`
- ⚡ **Zero Dependencies** — Only requires FastAPI/Starlette (which you already have)

## Installation

```bash
pip install fastapi-allowed-hosts
```

Or with Poetry:

```bash
poetry add fastapi-allowed-hosts
```

## Quick Start

```python
from fastapi import FastAPI, Request
from fastapi_allowed_hosts import AllowedHostsMiddleware

app = FastAPI()

# Add the middleware with your allowed hosts
app.add_middleware(
    AllowedHostsMiddleware,
    allowed_hosts=["example.com", "www.example.com", "localhost"],
)

@app.get("/")
async def root(request: Request):
    # Access the client IP extracted by the middleware
    client_ip = request.state.client_ip
    return {"message": "Hello World", "your_ip": client_ip}
```

## Configuration

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `allowed_hosts` | `Sequence[str]` | `("*",)` | List of allowed host patterns |
| `www_redirect` | `bool` | `True` | Redirect non-www to www if www variant is in allowed_hosts |
| `on_error` | `Callable` | `None` | Custom error handler `(request, host) -> Response` |

### Host Patterns

The middleware supports several host pattern formats:

| Pattern | Description | Example Matches |
|---------|-------------|-----------------|
| `"example.com"` | Exact match | `example.com` |
| `".example.com"` | Subdomain wildcard | `example.com`, `api.example.com`, `sub.api.example.com` |
| `"*"` | Match all hosts | Any host (use only in development!) |

## Usage Examples

### Production Setup

```python
from fastapi import FastAPI
from fastapi_allowed_hosts import AllowedHostsMiddleware

app = FastAPI()

app.add_middleware(
    AllowedHostsMiddleware,
    allowed_hosts=[
        "myapp.com",
        "www.myapp.com",
        "api.myapp.com",
    ],
)
```

### Allow All Subdomains

```python
app.add_middleware(
    AllowedHostsMiddleware,
    allowed_hosts=[".myapp.com"],  # Matches myapp.com and all subdomains
)
```

### Development Setup

```python
import os
from fastapi import FastAPI
from fastapi_allowed_hosts import AllowedHostsMiddleware

app = FastAPI()

# Use wildcard in development, strict hosts in production
allowed = ["*"] if os.getenv("DEBUG") else ["myapp.com", "www.myapp.com"]

app.add_middleware(
    AllowedHostsMiddleware,
    allowed_hosts=allowed,
)
```

### Disable WWW Redirect

```python
app.add_middleware(
    AllowedHostsMiddleware,
    allowed_hosts=["example.com", "www.example.com"],
    www_redirect=False,  # Don't auto-redirect to www
)
```

### Accessing Client IP

The middleware automatically extracts the client IP and makes it available on `request.state.client_ip`:

```python
from fastapi import FastAPI, Request
from fastapi_allowed_hosts import AllowedHostsMiddleware

app = FastAPI()

app.add_middleware(
    AllowedHostsMiddleware,
    allowed_hosts=["*"],
)

@app.get("/whoami")
async def whoami(request: Request):
    return {
        "ip": request.state.client_ip,
        "host": request.headers.get("host"),
    }

@app.post("/log-action")
async def log_action(request: Request):
    client_ip = request.state.client_ip
    # Log the action with the real client IP
    print(f"Action performed by {client_ip}")
    return {"status": "logged"}
```

## How It Works

### Host Extraction

The middleware extracts the host following the same algorithm as Django's `HttpRequest.get_host()`:

1. Check `X-Forwarded-Host` header (set by reverse proxies)
2. Fall back to `Host` header
3. Strip port number (handles both IPv4 and IPv6)
4. Normalize to lowercase

### Client IP Extraction

The client IP is determined using the following priority:

1. `X-Forwarded-For` header (first IP in the comma-separated list)
2. `X-Real-IP` header (commonly used by Nginx)
3. Direct client connection (`request.client.host`)

This ensures the real client IP is captured even when behind load balancers or reverse proxies.

### Security Note

When using `X-Forwarded-For` or `X-Forwarded-Host`, ensure your reverse proxy is configured to set these headers correctly and that direct access to your application is blocked. Trusting these headers without proper proxy configuration can lead to IP spoofing.

## Custom Error Handling

By default, when a request comes from a disallowed host, the middleware returns a `400 Bad Request` with the text "Invalid host header". You can customize this behavior using the `on_error` parameter:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from fastapi_allowed_hosts import AllowedHostsMiddleware

app = FastAPI()

def custom_error_handler(request: Request, host: str) -> Response:
    """Custom handler for disallowed hosts."""
    return JSONResponse(
        status_code=403,
        content={
            "error": "Access denied",
            "message": f"Host '{host}' is not allowed",
            "path": str(request.url.path),
        },
    )

app.add_middleware(
    AllowedHostsMiddleware,
    allowed_hosts=["example.com"],
    on_error=custom_error_handler,
)
```

The `on_error` callback receives:
- `request`: The Starlette `Request` object
- `host`: The invalid host that was rejected

It must return a Starlette `Response` object.

## Requirements

- Python 3.14+
- FastAPI 0.128.0+

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

Inspired by Django's `ALLOWED_HOSTS` setting and host validation implementation. See the [Django documentation](https://docs.djangoproject.com/en/5.0/ref/settings/#allowed-hosts) for more details on the security benefits of host validation.
