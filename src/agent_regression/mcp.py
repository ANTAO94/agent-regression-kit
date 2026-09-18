from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import select
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from copy import deepcopy
from typing import Any, Callable, Dict, Iterator, List, Mapping, Protocol, Sequence, Tuple

from .adapters import AgentAdapter
from .model import AgentTrace
from .record import ToolExecutionResult, record_run
from .redaction import RedactionPolicy


PROTOCOL_VERSION = "2025-11-25"


class McpTransportError(RuntimeError):
    """Raised when a stdio subprocess cannot exchange valid JSON-RPC messages."""


class McpTimeoutError(McpTransportError):
    """Raised when an MCP request exceeds its configured response deadline."""


class McpProtocolError(RuntimeError):
    """Raised for a JSON-RPC error response from the MCP server."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"MCP error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class McpClient(Protocol):
    timeout_seconds: float
    transcript: List[Dict[str, Any]]
    server_info: Dict[str, Any]
    tools: List[Dict[str, Any]]
    last_request_id: int | None

    def initialize(self) -> Dict[str, Any]: ...

    def list_tools(self) -> List[Dict[str, Any]]: ...

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        task: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]: ...


def _validate_initialize(result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("protocolVersion") != PROTOCOL_VERSION:
        raise McpTransportError(
            f"server negotiated unsupported protocol {result.get('protocolVersion')!r}"
        )
    return result


def _raise_for_rpc_error(response: Dict[str, Any]) -> Dict[str, Any]:
    if "error" in response:
        error = response["error"]
        raise McpProtocolError(
            int(error.get("code", -32603)),
            str(error.get("message", "unknown MCP error")),
            error.get("data"),
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise McpTransportError("MCP response result must be an object")
    return result


def _decode_http_response(body: bytes, content_type: str) -> Dict[str, Any]:
    """Decode the JSON or SSE response forms used by Streamable HTTP."""
    text = body.decode("utf-8")
    if "text/event-stream" not in content_type:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise McpTransportError(f"MCP HTTP response was not valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise McpTransportError("MCP HTTP response must be a JSON object")
        return value

    data_lines: List[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        raise McpTransportError("MCP SSE response did not contain a data event")
    for data in data_lines:
        if not data:
            continue
        try:
            value = json.loads(data)
        except json.JSONDecodeError as exc:
            continue
        if isinstance(value, dict) and ("result" in value or "error" in value):
            return value
    raise McpTransportError("MCP SSE response did not contain a JSON-RPC response")


def _page_items(
    result: Dict[str, Any], key: str
) -> Tuple[List[Dict[str, Any]], str | None]:
    items = result.get(key)
    if not isinstance(items, list):
        raise McpTransportError(f"MCP page did not contain a {key} array")
    cursor = result.get("nextCursor")
    if cursor is not None and not isinstance(cursor, str):
        raise McpTransportError("MCP page nextCursor must be a string")
    return deepcopy(items), cursor


def _iterate_pages(
    fetch: Callable[[str | None], Tuple[List[Dict[str, Any]], str | None]]
) -> Iterator[Dict[str, Any]]:
    cursor: str | None = None
    seen: set[str] = set()
    while True:
        items, next_cursor = fetch(cursor)
        yield from items
        if not next_cursor:
            return
        if next_cursor in seen:
            raise McpTransportError(f"MCP pagination cursor repeated: {next_cursor!r}")
        seen.add(next_cursor)
        cursor = next_cursor


class StdioMcpClient:
    """Small synchronous MCP client for deterministic local test fixtures.

    Supports newline-delimited JSON and MCP Content-Length framing.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 5.0,
        framing: str = "newline",
        client_capabilities: Mapping[str, Any] | None = None,
        server_request_handler: Callable[[Dict[str, Any]], Mapping[str, Any]] | None = None,
    ):
        if not command:
            raise ValueError("MCP server command must not be empty")
        if framing not in {"newline", "content-length"}:
            raise ValueError("stdio framing must be 'newline' or 'content-length'")
        self.command = list(command)
        self.timeout_seconds = timeout_seconds
        self.framing = framing
        self.client_capabilities = deepcopy(dict(client_capabilities or {}))
        self.server_request_handler = server_request_handler
        self.transcript: List[Dict[str, Any]] = []
        self._next_id = 1
        self._process: subprocess.Popen[bytes] | None = None
        self.server_info: Dict[str, Any] = {}
        self.tools: List[Dict[str, Any]] = []
        self.last_request_id: int | None = None

    def __enter__(self) -> "StdioMcpClient":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            raise McpTransportError("MCP client is already started")
        try:
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except OSError as exc:
            raise McpTransportError(f"failed to start MCP server: {exc}") from exc

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        for stream in (process.stdout, process.stderr):
            if stream and not stream.closed:
                stream.close()
        self._process = None

    def reconnect(self) -> Dict[str, Any]:
        self.close()
        self.start()
        return self.initialize()

    def initialize(self) -> Dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": deepcopy(self.client_capabilities),
                "clientInfo": {"name": "agent-regression-kit", "version": "2.2.0"},
            },
        )
        _validate_initialize(result)
        self.server_info = deepcopy(result.get("serverInfo", {}))
        self.notify("notifications/initialized", {})
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        tools, _ = self.list_tools_page()
        self.tools = deepcopy(tools)
        return deepcopy(tools)

    def list_tools_page(self, cursor: str | None = None) -> Tuple[List[Dict[str, Any]], str | None]:
        params = {"cursor": cursor} if cursor else {}
        return _page_items(self.request("tools/list", params), "tools")

    def iter_tools(self) -> Iterator[Dict[str, Any]]:
        return _iterate_pages(self.list_tools_page)

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        task: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"name": name, "arguments": dict(arguments)}
        if task is not None:
            params["task"] = dict(task)
        return self.request("tools/call", params)

    def list_resources(self) -> List[Dict[str, Any]]:
        resources, _ = self.list_resources_page()
        return deepcopy(resources)

    def list_resources_page(self, cursor: str | None = None) -> Tuple[List[Dict[str, Any]], str | None]:
        params = {"cursor": cursor} if cursor else {}
        return _page_items(self.request("resources/list", params), "resources")

    def iter_resources(self) -> Iterator[Dict[str, Any]]:
        return _iterate_pages(self.list_resources_page)

    def read_resource(self, uri: str) -> Dict[str, Any]:
        return self.request("resources/read", {"uri": uri})

    def list_prompts(self) -> List[Dict[str, Any]]:
        prompts, _ = self.list_prompts_page()
        return deepcopy(prompts)

    def list_prompts_page(self, cursor: str | None = None) -> Tuple[List[Dict[str, Any]], str | None]:
        params = {"cursor": cursor} if cursor else {}
        return _page_items(self.request("prompts/list", params), "prompts")

    def iter_prompts(self) -> Iterator[Dict[str, Any]]:
        return _iterate_pages(self.list_prompts_page)

    def get_prompt(
        self, name: str, arguments: Mapping[str, str] | None = None
    ) -> Dict[str, Any]:
        return self.request("prompts/get", {"name": name, "arguments": dict(arguments or {})})

    def cancel(self, request_id: Any, reason: str | None = None) -> None:
        params: Dict[str, Any] = {"requestId": request_id}
        if reason:
            params["reason"] = reason
        self.notify("notifications/cancelled", params)

    def list_tasks_page(self, cursor: str | None = None) -> Tuple[List[Dict[str, Any]], str | None]:
        params = {"cursor": cursor} if cursor else {}
        return _page_items(self.request("tasks/list", params), "tasks")

    def iter_tasks(self) -> Iterator[Dict[str, Any]]:
        return _iterate_pages(self.list_tasks_page)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self.request("tasks/get", {"taskId": task_id})

    def get_task_result(self, task_id: str) -> Dict[str, Any]:
        return self.request("tasks/result", {"taskId": task_id})

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        return self.request("tasks/cancel", {"taskId": task_id})

    def request(self, method: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self.last_request_id = request_id
        self._send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)}
        )
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            response = self._read(deadline)
            if "method" in response:
                self._handle_server_request(response)
                continue
            if response.get("id") != request_id:
                raise McpTransportError(
                    f"expected response id {request_id!r}, got {response.get('id')!r}"
                )
            if "error" in response:
                error = response["error"]
                raise McpProtocolError(
                    int(error.get("code", -32603)),
                    str(error.get("message", "unknown MCP error")),
                    error.get("data"),
                )
            result = response.get("result")
            if not isinstance(result, dict):
                raise McpTransportError("MCP response result must be an object")
            return result

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    def _handle_server_request(self, message: Dict[str, Any]) -> None:
        if not self.server_request_handler or "id" not in message:
            return
        try:
            result = self.server_request_handler(message)
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": dict(result)})
        except Exception as exc:
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32603, "message": str(exc)},
                }
            )

    def _send(self, message: Dict[str, Any]) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise McpTransportError("MCP server stdin is unavailable")
        self.transcript.append({"direction": "client_to_server", "message": deepcopy(message)})
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if self.framing == "content-length":
            rendered = b"Content-Length: " + str(len(payload)).encode("ascii") + b"\r\n\r\n" + payload
        else:
            rendered = payload + b"\n"
        try:
            process.stdin.write(rendered)
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise McpTransportError(f"failed to write to MCP server: {exc}") from exc

    def _read(self, deadline: float) -> Dict[str, Any]:
        process = self._require_process()
        if process.stdout is None:
            raise McpTransportError("MCP server stdout is unavailable")
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
            raise McpTimeoutError("timed out waiting for MCP server response")
        line = process.stdout.readline()
        if not line:
            stderr = process.stderr.read().decode("utf-8", errors="replace").strip() if process.stderr else ""
            detail = f": {stderr}" if stderr else ""
            raise McpTransportError(f"MCP server closed stdout{detail}")
        if self.framing == "content-length":
            if not line.lower().startswith(b"content-length:"):
                raise McpTransportError("MCP server did not return a Content-Length frame")
            try:
                length = int(line.split(b":", 1)[1].strip())
            except (IndexError, ValueError) as exc:
                raise McpTransportError("MCP server returned an invalid Content-Length") from exc
            while True:
                header = process.stdout.readline()
                if not header:
                    raise McpTransportError("MCP server closed an incomplete Content-Length frame")
                if header in {b"\n", b"\r\n"}:
                    break
            payload = process.stdout.read(length)
            if len(payload) != length:
                raise McpTransportError("MCP server returned a truncated Content-Length frame")
            line = payload
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise McpTransportError(f"MCP server emitted invalid JSON: {exc}") from exc
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise McpTransportError("MCP server emitted an invalid JSON-RPC message")
        self.transcript.append({"direction": "server_to_client", "message": deepcopy(message)})
        return message

    def _require_process(self) -> subprocess.Popen[bytes]:
        if self._process is None:
            raise McpTransportError("MCP client is not started")
        return self._process


class StreamableHttpMcpClient:
    """Small synchronous MCP client for Streamable HTTP request/response flows.

    It supports immediate JSON responses and server-sent-event responses. The
    client intentionally mirrors ``StdioMcpClient`` so the same adapter and
    trace recorder can exercise either transport.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout_seconds: float = 5.0,
        headers: Mapping[str, str] | None = None,
        client_capabilities: Mapping[str, Any] | None = None,
        server_request_handler: Callable[[Dict[str, Any]], Mapping[str, Any]] | None = None,
    ):
        if not url:
            raise ValueError("MCP HTTP URL must not be empty")
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.headers = {str(key): str(value) for key, value in (headers or {}).items()}
        self.client_capabilities = deepcopy(dict(client_capabilities or {}))
        self.server_request_handler = server_request_handler
        self.transcript: List[Dict[str, Any]] = []
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._request_local = threading.local()
        self.session_id: str | None = None
        self.last_event_id: str | None = None
        self.server_info: Dict[str, Any] = {}
        self.tools: List[Dict[str, Any]] = []
        self.last_request_id: int | None = None

    def __enter__(self) -> "StreamableHttpMcpClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        self.session_id = None

    def reconnect(self) -> Dict[str, Any]:
        self.close()
        return self.initialize()

    def initialize(self) -> Dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": deepcopy(self.client_capabilities),
                "clientInfo": {"name": "agent-regression-kit", "version": "2.2.0"},
            },
        )
        _validate_initialize(result)
        self.server_info = deepcopy(result.get("serverInfo", {}))
        self.notify("notifications/initialized", {})
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        tools, _ = self.list_tools_page()
        self.tools = deepcopy(tools)
        return deepcopy(tools)

    def list_tools_page(self, cursor: str | None = None) -> Tuple[List[Dict[str, Any]], str | None]:
        params = {"cursor": cursor} if cursor else {}
        return _page_items(self.request("tools/list", params), "tools")

    def iter_tools(self) -> Iterator[Dict[str, Any]]:
        return _iterate_pages(self.list_tools_page)

    @property
    def last_request_id(self) -> int | None:
        return getattr(self._request_local, "last_request_id", None)

    @last_request_id.setter
    def last_request_id(self, value: int | None) -> None:
        self._request_local.last_request_id = value

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        task: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"name": name, "arguments": dict(arguments)}
        if task is not None:
            params["task"] = dict(task)
        return self.request("tools/call", params)

    def call_tools_concurrently(
        self,
        calls: Sequence[Tuple[str, Mapping[str, Any]]],
        *,
        max_workers: int = 4,
    ) -> List[Dict[str, Any]]:
        """Call tools concurrently and return results in input order."""
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self.call_tool, name, arguments) for name, arguments in calls]
            return [future.result() for future in futures]

    def list_resources(self) -> List[Dict[str, Any]]:
        resources, _ = self.list_resources_page()
        return deepcopy(resources)

    def list_resources_page(self, cursor: str | None = None) -> Tuple[List[Dict[str, Any]], str | None]:
        params = {"cursor": cursor} if cursor else {}
        return _page_items(self.request("resources/list", params), "resources")

    def iter_resources(self) -> Iterator[Dict[str, Any]]:
        return _iterate_pages(self.list_resources_page)

    def read_resource(self, uri: str) -> Dict[str, Any]:
        return self.request("resources/read", {"uri": uri})

    def list_prompts(self) -> List[Dict[str, Any]]:
        prompts, _ = self.list_prompts_page()
        return deepcopy(prompts)

    def list_prompts_page(self, cursor: str | None = None) -> Tuple[List[Dict[str, Any]], str | None]:
        params = {"cursor": cursor} if cursor else {}
        return _page_items(self.request("prompts/list", params), "prompts")

    def iter_prompts(self) -> Iterator[Dict[str, Any]]:
        return _iterate_pages(self.list_prompts_page)

    def get_prompt(
        self, name: str, arguments: Mapping[str, str] | None = None
    ) -> Dict[str, Any]:
        return self.request("prompts/get", {"name": name, "arguments": dict(arguments or {})})

    def cancel(self, request_id: Any, reason: str | None = None) -> None:
        params: Dict[str, Any] = {"requestId": request_id}
        if reason:
            params["reason"] = reason
        self.notify("notifications/cancelled", params)

    def list_tasks_page(self, cursor: str | None = None) -> Tuple[List[Dict[str, Any]], str | None]:
        params = {"cursor": cursor} if cursor else {}
        return _page_items(self.request("tasks/list", params), "tasks")

    def iter_tasks(self) -> Iterator[Dict[str, Any]]:
        return _iterate_pages(self.list_tasks_page)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self.request("tasks/get", {"taskId": task_id})

    def get_task_result(self, task_id: str) -> Dict[str, Any]:
        return self.request("tasks/result", {"taskId": task_id})

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        return self.request("tasks/cancel", {"taskId": task_id})

    def request(self, method: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        with self._id_lock:
            request_id = self._next_id
            self._next_id += 1
        self.last_request_id = request_id
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": dict(params),
            }
        )
        if response.get("id") != request_id:
            raise McpTransportError(
                f"expected response id {request_id!r}, got {response.get('id')!r}"
            )
        return _raise_for_rpc_error(response)

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._post(
            {"jsonrpc": "2.0", "method": method, "params": dict(params)},
            notification=True,
        )

    def open_event_stream(
        self,
        *,
        last_event_id: str | None = None,
        request_handler: Callable[[Dict[str, Any]], Mapping[str, Any]] | None = None,
    ) -> "McpEventStream":
        """Open the server-to-client SSE stream for the current session.

        The returned stream is a context manager and iterator of JSON-RPC
        notifications or requests. It is deliberately separate from
        ``request`` so a caller can decide how to handle server-initiated
        messages without making the normal tool path concurrent implicitly.
        """
        headers = {
            "Accept": "text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        headers.update(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        resume_id = last_event_id if last_event_id is not None else self.last_event_id
        if resume_id:
            headers["Last-Event-ID"] = resume_id
        request = urllib.request.Request(self.url, headers=headers, method="GET")
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as exc:
            raise McpTransportError(
                f"MCP HTTP event stream failed with status {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise McpTransportError(f"MCP HTTP event stream failed: {exc.reason}") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise McpTimeoutError("timed out opening MCP HTTP event stream") from exc
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" not in content_type:
            response.close()
            raise McpTransportError("MCP HTTP GET did not return an event stream")
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self.session_id = session_id
        return McpEventStream(
            self,
            response,
            request_handler=request_handler or self.server_request_handler,
        )

    def respond(
        self,
        request_id: Any,
        *,
        result: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> None:
        """Send an explicit JSON-RPC response to a server-initiated request."""
        if (result is None) == (error is None):
            raise ValueError("exactly one of result or error must be provided")
        message: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
        if error is not None:
            message["error"] = dict(error)
        else:
            message["result"] = dict(result or {})
        self._post(message, notification=True)

    def _post(self, message: Dict[str, Any], *, notification: bool = False) -> Dict[str, Any]:
        with self._id_lock:
            self.transcript.append(
                {"direction": "client_to_server", "message": deepcopy(message)}
            )
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        headers.update(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(
            self.url,
            data=json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                session_id = response.headers.get("Mcp-Session-Id")
                if session_id:
                    self.session_id = session_id
                if notification and response.status in (200, 202, 204):
                    return {}
                content_type = response.headers.get("Content-Type", "")
                if "text/event-stream" in content_type:
                    decoded = self._read_sse_response(response, message.get("id"))
                else:
                    body = response.read()
                    decoded = _decode_http_response(body, content_type)
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except OSError:
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise McpTransportError(
                f"MCP HTTP request failed with status {exc.code}{suffix}"
            ) from exc
        except urllib.error.URLError as exc:
            raise McpTransportError(f"MCP HTTP request failed: {exc.reason}") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise McpTimeoutError("timed out waiting for MCP HTTP response") from exc
        with self._id_lock:
            self.transcript.append(
                {"direction": "server_to_client", "message": deepcopy(decoded)}
            )
        return decoded

    def _read_sse_response(self, response: Any, request_id: Any) -> Dict[str, Any]:
        """Read a POST response stream, dispatching server requests in-band."""
        data_lines: List[str] = []
        event_id: str | None = None
        while True:
            raw_line = response.readline()
            if not raw_line:
                if data_lines:
                    decoded = self._decode_sse_response_event(data_lines, event_id, request_id)
                    if decoded is not None:
                        return decoded
                raise McpTransportError("MCP SSE response did not contain a JSON-RPC response")
            line = raw_line.decode("utf-8").rstrip("\r\n")
            if not line:
                if data_lines:
                    decoded = self._decode_sse_response_event(data_lines, event_id, request_id)
                    data_lines = []
                    event_id = None
                    if decoded is not None:
                        return decoded
                continue
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line.startswith("id:"):
                event_id = line[3:].lstrip()

    def _decode_sse_response_event(
        self, data_lines: List[str], event_id: str | None, request_id: Any
    ) -> Dict[str, Any] | None:
        if event_id:
            self.last_event_id = event_id
        if not any(data_lines):
            return None
        try:
            value = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            return None
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
            return None
        if "method" in value:
            transcript_entry: Dict[str, Any] = {
                "direction": "server_to_client",
                "message": deepcopy(value),
            }
            if event_id:
                transcript_entry["event_id"] = event_id
            with self._id_lock:
                self.transcript.append(transcript_entry)
            self._handle_server_request(value)
            return None
        if value.get("id") != request_id:
            raise McpTransportError(
                f"expected response id {request_id!r}, got {value.get('id')!r}"
            )
        return value

    def _handle_server_request(self, message: Dict[str, Any]) -> None:
        if not self.server_request_handler or "id" not in message:
            return
        try:
            result = self.server_request_handler(message)
            self.respond(message["id"], result=result)
        except Exception as exc:
            self.respond(
                message["id"],
                error={"code": -32603, "message": str(exc)},
            )


class McpEventStream:
    """Incremental SSE decoder for MCP server-initiated messages."""

    def __init__(
        self,
        client: StreamableHttpMcpClient,
        response: Any,
        *,
        request_handler: Callable[[Dict[str, Any]], Mapping[str, Any]] | None = None,
    ):
        self.client = client
        self.response = response
        self.request_handler = request_handler
        self._closed = False

    def __enter__(self) -> "McpEventStream":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.response.close()

    def respond(
        self,
        request_id: Any,
        *,
        result: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> None:
        self.client.respond(request_id, result=result, error=error)

    def iter_progress(self) -> Iterator[Dict[str, Any]]:
        """Yield only MCP progress notifications from this event stream."""
        for event in self:
            if event.get("method") == "notifications/progress":
                yield event

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        data_lines: List[str] = []
        event_id: str | None = None
        try:
            while True:
                raw_line = self.response.readline()
                if not raw_line:
                    if data_lines:
                        decoded = self._decode_event(data_lines, event_id)
                        if decoded is not None:
                            yield decoded
                    return
                line = raw_line.decode("utf-8").rstrip("\r\n")
                if not line:
                    if data_lines:
                        decoded = self._decode_event(data_lines, event_id)
                        if decoded is not None:
                            yield decoded
                        data_lines = []
                        event_id = None
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
                elif line.startswith("id:"):
                    event_id = line[3:].lstrip()
        except socket.timeout as exc:
            raise McpTimeoutError("timed out waiting for MCP HTTP event") from exc
        finally:
            self.close()

    def _decode_event(
        self, data_lines: List[str], event_id: str | None
    ) -> Dict[str, Any] | None:
        if event_id:
            self.client.last_event_id = event_id
        if not any(data_lines):
            return None
        try:
            value = json.loads("\n".join(data_lines))
        except json.JSONDecodeError as exc:
            return None
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
            return None
        transcript_entry: Dict[str, Any] = {
            "direction": "server_to_client",
            "message": deepcopy(value),
        }
        if event_id:
            transcript_entry["event_id"] = event_id
        self.client.transcript.append(transcript_entry)
        if self.request_handler and "method" in value and "id" in value:
            try:
                result = self.request_handler(value)
                self.respond(value["id"], result=result)
            except Exception as exc:
                self.respond(
                    value["id"],
                    error={"code": -32603, "message": str(exc)},
                )
        return value


class McpToolExecutor:
    """Normalize MCP tool results into AgentTrace tool_result events."""

    def __init__(self, client: McpClient):
        self.client = client

    def call(self, tool: str, arguments: Dict[str, Any]) -> ToolExecutionResult:
        try:
            response = self.client.call_tool(tool, arguments)
        except McpProtocolError as exc:
            return ToolExecutionResult(
                result={"error": "mcp_protocol_error", "code": exc.code, "message": exc.message},
                is_error=True,
                error=str(exc),
                metadata=self._metadata(),
            )
        except McpTransportError as exc:
            error_kind = "mcp_timeout" if isinstance(exc, McpTimeoutError) else "mcp_transport_error"
            return ToolExecutionResult(
                result={"error": error_kind, "message": str(exc)},
                is_error=True,
                error=str(exc),
                metadata=self._metadata(),
            )
        is_error = bool(response.get("isError", False))
        result = response.get("structuredContent")
        if result is None:
            result = deepcopy(response.get("content", []))
        error = _text_content(response.get("content", [])) if is_error else None
        return ToolExecutionResult(
            result=result,
            is_error=is_error,
            error=error,
            metadata=self._metadata(),
        )

    def _metadata(self) -> Dict[str, Any]:
        return {
            "mcp_request_id": self.client.last_request_id,
            "attempt": 1,
            "retry_count": 0,
            "timeout_seconds": self.client.timeout_seconds,
        }


def _text_content(content: Any) -> str | None:
    if not isinstance(content, list):
        return None
    parts = [
        item["text"]
        for item in content
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
    ]
    return "\n".join(parts) or None


def record_mcp_run(
    adapter: AgentAdapter,
    request: Any,
    server_command: Sequence[str],
    *,
    run_id: str,
    metadata: Mapping[str, Any] | None = None,
    timeout_seconds: float = 5.0,
    framing: str = "newline",
    client_capabilities: Mapping[str, Any] | None = None,
    server_request_handler: Callable[[Dict[str, Any]], Mapping[str, Any]] | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> AgentTrace:
    """Launch an MCP stdio server and record one agent run as AgentTrace."""
    with StdioMcpClient(
        server_command,
        timeout_seconds=timeout_seconds,
        framing=framing,
        client_capabilities=client_capabilities,
        server_request_handler=server_request_handler,
    ) as client:
        initialization = client.initialize()
        tools = client.list_tools()
        mcp_metadata: Dict[str, Any] = {
            "protocol_version": initialization["protocolVersion"],
            "server_info": deepcopy(initialization.get("serverInfo", {})),
            "tools": tools,
            "transcript": client.transcript,
            "retry_policy": "none",
            "side_effect_boundary": "server_subprocess",
        }
        return record_run(
            adapter,
            request,
            McpToolExecutor(client),
            run_id=run_id,
            metadata={**dict(metadata or {}), "mcp": mcp_metadata},
            redaction_policy=redaction_policy,
        )


def record_mcp_http_run(
    adapter: AgentAdapter,
    request: Any,
    server_url: str,
    *,
    run_id: str,
    metadata: Mapping[str, Any] | None = None,
    timeout_seconds: float = 5.0,
    headers: Mapping[str, str] | None = None,
    client_capabilities: Mapping[str, Any] | None = None,
    server_request_handler: Callable[[Dict[str, Any]], Mapping[str, Any]] | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> AgentTrace:
    """Record one agent run through an MCP Streamable HTTP endpoint."""
    with StreamableHttpMcpClient(
        server_url,
        timeout_seconds=timeout_seconds,
        headers=headers,
        client_capabilities=client_capabilities,
        server_request_handler=server_request_handler,
    ) as client:
        initialization = client.initialize()
        tools = client.list_tools()
        mcp_metadata: Dict[str, Any] = {
            "protocol_version": initialization["protocolVersion"],
            "server_info": deepcopy(initialization.get("serverInfo", {})),
            "tools": tools,
            "transcript": client.transcript,
            "retry_policy": "none",
            "side_effect_boundary": "server_http",
            "transport": "streamable_http",
            "session_id": client.session_id,
        }
        return record_run(
            adapter,
            request,
            McpToolExecutor(client),
            run_id=run_id,
            metadata={**dict(metadata or {}), "mcp": mcp_metadata},
            redaction_policy=redaction_policy,
        )
