"""HTTPS LAN listener, address discovery and offline QR material for Host mode."""

from __future__ import annotations

import hashlib
import io
import ipaddress
import os
import socket
import ssl
import subprocess
import threading
import time
from pathlib import Path

import psutil
import qrcode
import uvicorn


class LanServerError(RuntimeError):
    pass


def _default_route_address(ipv6: bool) -> str | None:
    """Return the source address the kernel chooses for the default route, without sending."""
    family = socket.AF_INET6 if ipv6 else socket.AF_INET
    target = ("2001:db8::1", 9) if ipv6 else ("192.0.2.1", 9)
    sock = socket.socket(family, socket.SOCK_DGRAM)
    try:
        sock.connect(target)
        return str(sock.getsockname()[0]).split("%", 1)[0]
    except OSError:
        return None
    finally:
        sock.close()


def lan_addresses() -> list[str]:
    bind = os.environ.get("MUTA_SHARE_BIND", "0.0.0.0")
    bind_is_ipv6 = ":" in bind

    def usable(value: str) -> str | None:
        try:
            parsed = ipaddress.ip_address(value.strip("[]").split("%", 1)[0])
        except ValueError:
            return None
        # Uvicorn owns one socket family. Never print an IPv6 QR for the default IPv4 bind
        # (or vice versa); an unreachable address is worse than a clear Host-mode error.
        if (parsed.version == 6) != bind_is_ipv6:
            return None
        if parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified:
            return None
        return f"[{parsed.compressed}]" if parsed.version == 6 else parsed.compressed

    override = os.environ.get("MUTA_SHARE_HOST", "").strip()
    if override:
        address = usable(override)
        return [address] if address else []
    # Cloud VMs have a perfectly valid-looking private address that belongs to their VPC, not
    # the classroom LAN. Native launchers set this guard on known cloud hosts so Host mode fails
    # clearly until a relay supplies the laptop address through MUTA_SHARE_HOST.
    if os.environ.get("MUTA_SHARE_REQUIRE_HOST") == "1":
        return []
    # A container only sees its private bridge address. Advertising that in the QR creates
    # a plausible-looking but unreachable classroom URL; run.sh injects the host address.
    if os.environ.get("MUTA_CONTAINERIZED") == "1":
        return []
    candidates: list[tuple[str, bool]] = []
    virtual_prefixes = (
        "br-",
        "bridge",
        "docker",
        "veth",
        "virbr",
        "utun",
        "tun",
        "tap",
        "wg",
        "tailscale",
        "vmenet",
    )
    for interface, addresses in psutil.net_if_addrs().items():
        virtual = interface.lower().startswith(virtual_prefixes)
        for address in addresses:
            if address.family not in {socket.AF_INET, socket.AF_INET6}:
                continue
            candidate = usable(address.address)
            if candidate:
                candidates.append((candidate, virtual))
    default = _default_route_address(bind_is_ipv6)
    if default and bind_is_ipv6:
        default = f"[{ipaddress.ip_address(default).compressed}]"
    # Prefer the physical default-route interface for the QR. Keep bridge/VPN addresses in
    # the list as manual alternatives, but never let their lexical order steal primary.
    return [
        item
        for item, _virtual in sorted(
            set(candidates),
            key=lambda pair: (
                pair[1],
                pair[0] != default,
                pair[0].startswith("["),
                pair[0],
            ),
        )
    ]


class LanServerManager:
    def __init__(self) -> None:
        self.host = os.environ.get("MUTA_SHARE_BIND", "0.0.0.0")
        self.port = int(os.environ.get("MUTA_SHARE_PORT", "8443"))
        root = Path(os.environ.get("TUTOR_ROOT", ".")).resolve()
        self.cert_dir = Path(os.environ.get("MUTA_SHARE_CERT_DIR", str(root / "data/share-certs")))
        self._root = root
        self._lock = threading.RLock()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._certified_addresses: tuple[str, ...] = ()
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive() and self._server)

    def urls(self) -> list[str]:
        # Never advertise a DHCP/VPN address that is absent from the currently-serving
        # certificate. The next explicit Host restart reissues for the then-current LAN.
        addresses = self._certified_addresses or tuple(lan_addresses())
        return [f"https://{address}:{self.port}/chat/" for address in addresses]

    def primary_url(self) -> str | None:
        urls = self.urls()
        return urls[0] if urls else None

    def certificate_fingerprint(self) -> str | None:
        # Devices trust the root CA, so this is the value the host and learner compare.
        cert = self.cert_dir / "rootCA.pem"
        try:
            der = ssl.PEM_cert_to_DER_cert(cert.read_text())
        except (OSError, ValueError):
            return None
        digest = hashlib.sha256(der).hexdigest().upper()
        return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))

    def _ensure_certificate(self) -> None:
        addresses = [item.strip("[]") for item in lan_addresses()]
        if not addresses:
            raise LanServerError("no usable LAN address was found")
        script = self._root / "scripts/gen_local_tls.sh"
        if not script.is_file():
            script = Path(__file__).resolve().parents[2] / "scripts/gen_local_tls.sh"
        try:
            result = subprocess.run(
                [str(script), "--out", str(self.cert_dir), *addresses],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LanServerError("could not create the offline LAN certificate") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "certificate generation failed").strip()
            raise LanServerError(detail.splitlines()[-1][:240])
        self._certified_addresses = tuple(
            f"[{address}]" if ":" in address else address for address in addresses
        )

    def start(self, app) -> None:
        with self._lock:
            if self.running:
                return
            self._ensure_certificate()
            config = uvicorn.Config(
                app,
                host=self.host,
                port=self.port,
                ssl_certfile=str(self.cert_dir / "fullchain.pem"),
                ssl_keyfile=str(self.cert_dir / "privkey.pem"),
                lifespan="off",
                access_log=False,
                log_level="warning",
            )
            server = uvicorn.Server(config)
            thread = threading.Thread(
                target=server.run,
                name="muta-share-lan",
                daemon=True,
            )
            self._server = server
            self._thread = thread
            self.last_error = None
            thread.start()
        deadline = time.monotonic() + 5.0
        probe_host = self.host
        if probe_host == "0.0.0.0":
            probe_host = "127.0.0.1"
        elif probe_host == "::":
            probe_host = "::1"
        probe_host = probe_host.strip("[]")
        while time.monotonic() < deadline:
            if not thread.is_alive():
                break
            if not server.started:
                time.sleep(0.05)
                continue
            try:
                with socket.create_connection((probe_host, self.port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        self.stop()
        self.last_error = f"HTTPS listener could not bind port {self.port}"
        raise LanServerError(self.last_error)

    def stop(self) -> None:
        with self._lock:
            server, thread = self._server, self._thread
            self._server = None
            self._thread = None
            if server is not None:
                server.should_exit = True
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3.0)

    def qr_png(self, url: str | None = None) -> bytes:
        target = url or self.primary_url()
        if not target:
            raise LanServerError("no usable LAN URL is available")
        code = qrcode.QRCode(version=None, box_size=7, border=3)
        code.add_data(target)
        code.make(fit=True)
        image = code.make_image(fill_color="#302d24", back_color="#fffefb")
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()

    def ca_bytes(self) -> bytes:
        try:
            return (self.cert_dir / "rootCA.pem").read_bytes()
        except OSError as exc:
            raise LanServerError("the Host-mode CA has not been generated yet") from exc


_LAN = LanServerManager()


def get_lan_manager() -> LanServerManager:
    return _LAN
