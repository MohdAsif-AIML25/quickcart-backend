"""The generated API documentation must keep working behind a reverse proxy."""

from fastapi.testclient import TestClient


def test_token_url_is_relative(client: TestClient) -> None:
    """In production, nginx serves the API under /api.

    An absolute tokenUrl ("/auth/login") would make Swagger's Authorize button
    post to http://host/auth/login, which is the frontend, not the API.
    A relative one ("auth/login") is resolved against the API's own address.
    """
    schema = client.get("/openapi.json").json()
    token_url = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]["tokenUrl"]

    assert token_url == "auth/login"
