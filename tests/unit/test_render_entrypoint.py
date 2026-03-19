from __future__ import annotations

from fastapi.testclient import TestClient

from main import app as render_entrypoint_app


def test_render_entrypoint_exposes_control_plane_routes_with_cors() -> None:
    client = TestClient(render_entrypoint_app)
    response = client.options(
        "/repos",
        headers={
            "Origin": "https://trickl.github.io",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://trickl.github.io"
