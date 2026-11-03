import asyncio
import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.websockets import WebSocketState
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

BACKEND_TIMEOUT = httpx.Timeout(connect=8.0, read=120.0, write=30.0, pool=5.0)
HEALTH_TIMEOUT = httpx.Timeout(connect=3.0, read=9.0, write=5.0, pool=3.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.backend_client = httpx.AsyncClient(
        timeout=BACKEND_TIMEOUT,
        follow_redirects=False,
    )
    try:
        yield
    finally:
        await app.state.backend_client.aclose()


app = FastAPI(lifespan=lifespan)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
HTTP_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def get_backend_url() -> str:
    backend_url = os.environ.get("BACKEND_URL")
    if not backend_url:
        raise HTTPException(status_code=503, detail="Backend service is unavailable")
    return backend_url.rstrip("/")


@app.api_route("/api", methods=HTTP_METHODS)
@app.api_route("/api/{path:path}", methods=HTTP_METHODS)
async def proxy_http(request: Request, path: str = ""):
    target_url = f"{get_backend_url()}{request.url.path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    request_headers = [
        (name.decode("latin-1"), value.decode("latin-1"))
        for name, value in request.headers.raw
        if name.decode("latin-1").lower() not in HOP_BY_HOP_HEADERS | {"host"}
    ]
    client: httpx.AsyncClient = request.app.state.backend_client
    request_timeout = HEALTH_TIMEOUT if request.url.path == "/api/health" else BACKEND_TIMEOUT
    outbound_request = client.build_request(
        request.method,
        target_url,
        headers=request_headers,
        content=request.stream(),
        timeout=request_timeout,
    )

    try:
        upstream_response = await client.send(outbound_request, stream=True)
    except httpx.RequestError as error:
        raise HTTPException(status_code=502, detail="Backend service request failed") from error

    response_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in upstream_response.headers.multi_items()
        if name.lower() not in HOP_BY_HOP_HEADERS
    ]

    async def close_upstream():
        await upstream_response.aclose()

    response = StreamingResponse(
        upstream_response.aiter_raw(),
        status_code=upstream_response.status_code,
        background=BackgroundTask(close_upstream),
    )
    response.raw_headers = response_headers
    return response


@app.websocket("/api/ws/{path:path}")
async def proxy_websocket(websocket: WebSocket, path: str):
    backend_url = os.environ.get("BACKEND_URL")
    if not backend_url:
        await websocket.close(code=1011, reason="Backend service is unavailable")
        return

    parsed_url = urlsplit(backend_url)
    backend_scheme = {"http": "ws", "https": "wss"}.get(parsed_url.scheme, parsed_url.scheme)
    target_url = urlunsplit(
        (
            backend_scheme,
            parsed_url.netloc,
            f"/api/ws/{path}",
            websocket.url.query,
            "",
        )
    )
    excluded_headers = HOP_BY_HOP_HEADERS | {
        "host",
        "sec-websocket-accept",
        "sec-websocket-extensions",
        "sec-websocket-key",
        "sec-websocket-protocol",
        "sec-websocket-version",
    }
    forwarded_headers = {
        name: value
        for name, value in websocket.headers.items()
        if name.lower() not in excluded_headers
    }

    try:
        async with connect(
            target_url,
            additional_headers=forwarded_headers,
            open_timeout=10,
            ping_interval=20,
        ) as backend_socket:
            await websocket.accept()

            async def forward_client_messages():
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("text") is not None:
                        await backend_socket.send(message["text"])
                    elif message.get("bytes") is not None:
                        await backend_socket.send(message["bytes"])

            async def forward_backend_messages():
                async for message in backend_socket:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            tasks = {
                asyncio.create_task(forward_client_messages()),
                asyncio.create_task(forward_backend_messages()),
            }
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.close(code=1000)
    except (ConnectionClosed, OSError, TimeoutError, httpx.HTTPError, WebSocketDisconnect):
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011, reason="Backend WebSocket unavailable")
    except Exception:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011, reason="Backend WebSocket unavailable")
