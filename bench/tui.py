"""Muta terminal TUI — chat with a live scored-metrics panel.

    make tui                 # against a running app (./run.sh --serve)
    ./run.sh --tui           # boots the app, then launches this

Type at the bottom, the reply streams into the transcript, and the right-hand panel shows
tokens/sec, RAM, and the two scored terms (S_perf, S_eff) updating live.

Two design choices carried over from the rest of bench/, for the same reasons:

- **It is a `/v1` client, not an embedded engine.** It talks to the gateway over HTTP, so the
  RAM it reports is the real deployed tree (gateway + llama-server), not this process. The
  TUI's own memory — Textual included — never pollutes the scored number.
- **It samples the tree externally, by PID**, exactly like `bench/monitor.py`. Streaming uses
  an internal, non-schema route (`/v1/chat/stream`); the frozen contract is untouched.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
from pathlib import Path

import httpx
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Input, Static

from bench.monitor import MonitorError, resolve_engine_pid, resolve_pid
from bench.sampler import ThermalSampler, TreeSampler
from bench.score import PROVISIONAL_TPS_MAX, RAM_BUDGET_GB, score

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

DEFAULT_IMAGE_QUESTION = "Here is a photo of my work — help me with it."


def parse_image_command(line: str) -> tuple[str, str | None] | None:
    """Parse `/img <path> [question]`. Returns (path, question|None), or None if not /img.

    Pure so it is unit-testable without a Textual app. `shlex` handles a quoted path that
    contains spaces; the rest of the tokens (if any) become the tutoring question.
    """
    stripped = line.strip()
    if not (stripped == "/img" or stripped.startswith("/img ")):
        return None
    rest = stripped[len("/img"):].strip()
    if not rest:
        return None
    try:
        parts = shlex.split(rest)
    except ValueError:
        parts = rest.split()
    if not parts:
        return None
    return parts[0], (" ".join(parts[1:]) or None)


class MetricsPanel(Static):
    """The live right-hand panel. Values are pushed in by the app's sampler tick."""


class MutaTUI(App):
    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; }
    #transcript { width: 3fr; padding: 0 1; }
    MetricsPanel {
        width: 30;
        border: round $accent;
        padding: 1;
    }
    #prompt { dock: bottom; }
    """
    BINDINGS = [("ctrl+c", "quit", "quit"), ("ctrl+d", "quit", "quit")]

    def __init__(self, base_url: str, gateway_pid: int, engine_pid: int | None) -> None:
        super().__init__()
        self.base_url = base_url
        self.gateway_pid = gateway_pid
        self.engine_pid = engine_pid
        self.conversation_id: str | None = None
        self.messages: list[tuple[str, str]] = []
        self.streaming = ""
        self.thinking = ""  # Qwen3 chain of thought for the in-flight reply (ephemeral)
        self.live_tps = 0.0
        # Live decode-rate state, updated as tokens arrive so the panel climbs during
        # generation rather than sitting at 0 until the reply finishes.
        self._stream_t0 = 0.0
        self._stream_tokens = 0
        self._busy = False
        self._mem = TreeSampler()
        self._therm = ThermalSampler()

    # --- layout ---------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with VerticalScroll(id="transcript"):
                yield Static(self._render_transcript(), id="log")
            yield MetricsPanel(self._render_metrics(), id="metrics")
        yield Input(placeholder="ask a question…  (Ctrl-D to quit)", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Muta"
        pids = [self.gateway_pid] + ([self.engine_pid] if self.engine_pid else [])
        self._mem.start(pids)
        self._therm.start()
        self.set_interval(0.5, self._tick)
        self.query_one("#prompt", Input).focus()
        if self.engine_pid is None:
            self.sub_title = "no engine on :8080 — RAM understated"

    # --- rendering ------------------------------------------------------------------------
    def _render_transcript(self) -> Text:
        text = Text()
        for role, body in self.messages:
            if role == "you":
                text.append("you  ", style="bold cyan")
                text.append(body + "\n\n")
            else:
                text.append("muta ", style="bold green")
                text.append(body + "\n\n")
        if self.streaming:
            text.append("muta ", style="bold green")
            text.append(self.streaming + "▍\n")
        elif self.thinking:
            # Still reasoning, no answer yet — show the thinking dimmed. It collapses the moment
            # the answer starts, so the model never looks frozen during a long think phase.
            text.append("muta ", style="bold green")
            text.append("thinking… ", style="dim italic")
            text.append(self.thinking + "▍\n", style="dim italic")
        return text

    def _render_metrics(self) -> Text:
        mem = self._mem.report()
        therm = self._therm.report()
        current_gb = self._mem.latest_rss_mb() / 1024.0
        result = score(
            accuracy=0.0,
            tps_actual=self.live_tps,
            peak_rss_gb=mem.peak_rss_gb,
            max_temp_c=therm.core_temp_c_peak,
            throttled=therm.throttled,
            label="tui",
        )
        temp = f"{therm.core_temp_c_peak:.0f} °C" if therm.core_temp_c_peak is not None else "—"

        t = Text()
        t.append("live\n\n", style="bold")
        t.append("RAM now  ", style="dim")
        t.append(f"{current_gb:5.2f} GB\n")
        t.append("RAM peak ", style="dim")
        peak_style = "red" if result.over_budget else "white"
        t.append(f"{mem.peak_rss_gb:5.2f} GB\n", style=peak_style)
        t.append("budget   ", style="dim")
        t.append(f"{RAM_BUDGET_GB:5.2f} GB\n\n")
        t.append("TPS      ", style="dim")
        t.append(f"{self.live_tps:5.1f} t/s\n")
        t.append("tps_max  ", style="dim")
        t.append(f"{PROVISIONAL_TPS_MAX:5.0f}  prov\n\n")
        t.append("S_perf   ", style="dim")
        t.append(f"{result.s_perf:5.1f}\n", style="green")
        t.append("S_eff    ", style="dim")
        t.append(f"{result.s_eff:5.1f}\n", style="green")
        t.append("temp     ", style="dim")
        t.append(f"{temp}\n")
        t.append("cpu p99  ", style="dim")
        t.append(f"{therm.cpu_percent_p99:.0f}%\n")
        if result.over_budget:
            t.append("\nOVER BUDGET\n", style="bold red")
        if result.p_thermal:
            t.append("\n−10 THERMAL\n", style="bold red")
        return t

    def _tick(self) -> None:
        self.query_one("#metrics", MetricsPanel).update(self._render_metrics())

    def _refresh_transcript(self) -> None:
        self.query_one("#log", Static).update(self._render_transcript())
        self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)

    def _begin_stream(self) -> None:
        self._stream_t0 = 0.0
        self._stream_tokens = 0
        self.thinking = ""

    def _record_token(self, now: float) -> None:
        """Update the live decode rate as one token arrives.

        Rate is over the decode window (first token to now), so it excludes time-to-first-token
        and reads close to the engine's own generation rate. Stays 0 until the second token —
        a rate needs an interval — which is why the panel shows 0 during prefill, not a lie.
        """
        if self._stream_tokens == 0:
            self._stream_t0 = now
        self._stream_tokens += 1
        elapsed = now - self._stream_t0
        if self._stream_tokens > 1 and elapsed > 0:
            self.live_tps = (self._stream_tokens - 1) / elapsed

    # --- interaction ----------------------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message or self._busy:
            return
        if message.lower() in {"exit", "quit"}:
            self.exit()
            return
        event.input.value = ""
        attach = parse_image_command(message)
        if attach is not None:
            path, question = attach
            self._attach_image(path, question)
            return
        self.messages.append(("you", message))
        self.streaming = ""
        self._refresh_transcript()
        self._stream_reply(message)

    @work(exclusive=True)
    async def _stream_reply(self, message: str) -> None:
        self._busy = True
        self._begin_stream()
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = True
        payload = {"student_id": "tui", "message": message}
        if self.conversation_id:
            payload["conversation_id"] = self.conversation_id

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/v1/chat/stream", json=payload
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        if "reasoning" in event:
                            # Thinking tokens are decoded too, so they count toward the live
                            # rate — otherwise TPS reads 0 through the whole think phase.
                            self._record_token(time.monotonic())
                            self.thinking += event["reasoning"]
                            self._refresh_transcript()
                        elif "delta" in event:
                            # Update the live rate per token so the panel climbs during
                            # generation instead of sitting at 0 until the reply finishes.
                            self._record_token(time.monotonic())
                            self.streaming += event["delta"]
                            self._refresh_transcript()
                        elif event.get("error"):
                            self.streaming += f"\n[engine error: {event['error']}]"
                            self._refresh_transcript()
                        elif event.get("done"):
                            self.conversation_id = event.get("conversation_id")
                            final = float(event.get("tokens_per_second") or 0.0)
                            if final > 0:
                                self.live_tps = final
        except httpx.HTTPError as e:
            self.streaming += f"\n[connection error: {type(e).__name__} — is the app running?]"

        # Persist the answer only; the chain of thought is ephemeral and collapses now.
        self.messages.append(("muta", self.streaming or "(no answer returned)"))
        self.streaming = ""
        self.thinking = ""
        self._refresh_transcript()
        self._busy = False
        prompt.disabled = False
        prompt.focus()

    @work(exclusive=True)
    async def _attach_image(self, path: str, question: str | None) -> None:
        """Send an image to /tutor/vision, show the transcription, then tutor from it."""
        self._busy = True
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = True
        transcription = ""
        try:
            file_path = Path(path).expanduser()
            self.messages.append(("you", f"[image: {file_path.name}]"))
            self._refresh_transcript()
            try:
                raw = file_path.read_bytes()
            except OSError as e:
                self.messages.append(
                    ("muta", f"couldn't read that file ({e.strerror or e}). "
                             "check the path and try again.")
                )
                self._refresh_transcript()
                return

            suffix = file_path.suffix.lower()
            mime = (
                "image/jpeg" if suffix in {".jpg", ".jpeg"}
                else "image/webp" if suffix == ".webp"
                else "image/png"
            )
            try:
                async with httpx.AsyncClient(timeout=300.0) as vclient:
                    resp = await vclient.post(
                        f"{self.base_url}/v1/tutor/vision",
                        data={"session_id": "tui"},
                        files={"image": (file_path.name, raw, mime)},
                    )
                    resp.raise_for_status()
                    reply = resp.json()
            except httpx.HTTPError as e:
                self.messages.append(
                    ("muta", f"[vision error: {type(e).__name__} — is the app running?]")
                )
                self._refresh_transcript()
                return

            if not reply.get("accepted", False):
                self.messages.append(("muta", reply.get("detail") or "that image couldn't be used."))
                self._refresh_transcript()
                return

            transcription = reply.get("transcription", "")
            self.messages.append(("muta", f"read:\n{transcription}"))
            self._refresh_transcript()
        finally:
            self._busy = False
            prompt.disabled = False
            prompt.focus()

        # Now tutor from the transcription as an ordinary text turn (transcribe -> tutor).
        follow_up = question or DEFAULT_IMAGE_QUESTION
        combined = f"{transcription}\n\n{follow_up}" if transcription else follow_up
        self.messages.append(("you", follow_up))
        self.streaming = ""
        self._refresh_transcript()
        self._stream_reply(combined)

    def on_unmount(self) -> None:
        self._mem.stop()
        self._therm.stop()


def build_app(base_url: str = DEFAULT_BASE_URL, *, port: int = 8000, engine_port: int = 8080):
    """Resolve the running app's PIDs and construct the TUI, or raise MonitorError."""
    gateway_pid = resolve_pid(None, port=port)
    engine_pid = resolve_engine_pid(engine_port)
    return MutaTUI(base_url, gateway_pid, engine_pid)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="muta-tui", description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--port", type=int, default=8000, help="gateway port")
    parser.add_argument("--engine-port", type=int, default=8080, help="llama-server port")
    args = parser.parse_args(argv)

    try:
        app = build_app(args.base_url, port=args.port, engine_port=args.engine_port)
    except MonitorError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
