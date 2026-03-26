from __future__ import annotations

import json
import logging
import re
import socket
import time

log = logging.getLogger(__name__)


class QMPError(Exception):
    pass


def _sanitize_snapshot_name(name: str) -> str:
    """Allow only safe characters in snapshot names to prevent monitor injection."""
    sanitized = re.sub(r'[^a-zA-Z0-9_\-.]', '', name)
    if not sanitized:
        raise QMPError("Invalid snapshot name: must contain alphanumeric characters, hyphens, dots, or underscores")
    return sanitized


class QMPConnection:
    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path
        self._sock: socket.socket | None = None

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self, timeout: float = 2.0, retries: int = 10) -> None:
        log.info("QMP connecting to socket: %s", self.socket_path)
        delay = timeout / retries
        last_err: Exception | None = None

        for _ in range(retries):
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect(self.socket_path)
                self._sock = sock
                self._negotiate()
                return
            except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
                last_err = exc
                try:
                    sock.close()
                except Exception:
                    pass
                time.sleep(delay)

        raise QMPError(f"Failed to connect to QMP socket after {timeout}s: {last_err}")

    def disconnect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()
            self._sock = None

    def _negotiate(self) -> None:
        greeting = self._recv()
        if "QMP" not in greeting:
            raise QMPError(f"Unexpected QMP greeting: {greeting}")
        self._send({"execute": "qmp_capabilities"})
        resp = self._recv()
        if "return" not in resp:
            raise QMPError(f"Capabilities negotiation failed: {resp}")

    def _close_on_error(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _send(self, cmd: dict) -> None:
        if self._sock is None:
            raise QMPError("Not connected")
        data = json.dumps(cmd).encode() + b"\n"
        try:
            self._sock.sendall(data)
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            self._close_on_error()
            raise QMPError(f"Send failed (connection lost): {exc}") from exc

    def _recv(self) -> dict:
        if self._sock is None:
            raise QMPError("Not connected")
        buf = b""
        while True:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                raise QMPError("Receive timeout")
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                self._close_on_error()
                raise QMPError(f"Recv failed (connection lost): {exc}") from exc
            if not chunk:
                self._close_on_error()
                raise QMPError("Connection closed by remote")
            buf += chunk
            try:
                return json.loads(buf.decode())
            except json.JSONDecodeError:
                continue

    def execute(self, command: str, arguments: dict | None = None) -> dict:
        cmd: dict = {"execute": command}
        if arguments:
            cmd["arguments"] = arguments
        self._send(cmd)

        while True:
            resp = self._recv()
            if "event" in resp:
                continue
            return resp

    def execute_cont(self) -> dict:
        return self.execute("cont")

    def execute_stop(self) -> dict:
        return self.execute("stop")

    def query_status(self) -> dict:
        return self.execute("query-status")

    def quit(self) -> dict:
        return self.execute("quit")

    # -- Performance queries --

    def query_cpus_fast(self) -> dict:
        return self.execute("query-cpus-fast")

    def query_balloon(self) -> dict:
        return self.execute("query-balloon")

    # -- USB hot-plug --

    def device_add(self, driver: str, device_id: str, **props: str | int) -> dict:
        args = {"driver": driver, "id": device_id}
        args.update(props)
        return self.execute("device_add", args)

    def device_del(self, device_id: str) -> dict:
        return self.execute("device_del", {"id": device_id})

    # -- Snapshots --

    def snapshot_create(self, name: str) -> dict:
        safe_name = _sanitize_snapshot_name(name)
        return self.execute(
            "human-monitor-command",
            {"command-line": f"savevm {safe_name}"},
        )

    def snapshot_restore(self, name: str) -> dict:
        safe_name = _sanitize_snapshot_name(name)
        return self.execute(
            "human-monitor-command",
            {"command-line": f"loadvm {safe_name}"},
        )

    def snapshot_delete(self, name: str) -> dict:
        safe_name = _sanitize_snapshot_name(name)
        return self.execute(
            "human-monitor-command",
            {"command-line": f"delvm {safe_name}"},
        )

    def snapshot_list(self) -> list[str]:
        resp = self.execute(
            "human-monitor-command",
            {"command-line": "info snapshots"},
        )
        output = resp.get("return", "")
        if not output or "No snapshots" in output or "There is no" in output:
            return []
        names = []
        for line in output.strip().splitlines():
            parts = line.split()
            if not parts or parts[0] in ("List", "ID", "--"):
                continue
            if len(parts) >= 2:
                names.append(parts[1])
        return names
