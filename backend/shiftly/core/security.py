from starlette.types import ASGIApp, Message, Receive, Scope, Send


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, secure_cookies: bool):
        self.app = app
        self.secure_cookies = secure_cookies

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        async def send_with_headers(message: Message):
            if message["type"] == "http.response.start":
                additions = dict(SECURITY_HEADERS)
                if self.secure_cookies:
                    additions["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
                if scope.get("path", "").startswith("/api/"):
                    additions["Cache-Control"] = "no-store"
                existing = {
                    name.decode("latin-1").lower()
                    for name, _ in message.get("headers", [])
                }
                message["headers"] = list(message.get("headers", []))
                for name, value in additions.items():
                    if name.lower() not in existing:
                        message["headers"].append(
                            (name.encode("latin-1"), value.encode("latin-1"))
                        )
            await send(message)

        await self.app(scope, receive, send_with_headers)
