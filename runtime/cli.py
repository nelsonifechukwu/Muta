"""Interactive multi-turn REPL — the quickest way to see the runtime work end to end.

    python -m runtime.cli            # or: make chat

Resolves the model (local folder, else Hugging Face), attaches to a running llama-server
or launches one, then holds a streaming conversation with persistent memory. Re-run with
`--conversation <id>` to resume a stored thread and prove persistence across processes.
"""

from __future__ import annotations

import argparse
import logging

import httpx

from runtime.chat import ChatEngine
from runtime.client import InferenceClient
from runtime.config import RuntimeConfig
from runtime.memory import ConversationStore
from runtime.server import LlamaServer


def main() -> int:
    p = argparse.ArgumentParser(description="Muta runtime chat REPL")
    p.add_argument("--student", default="cli-user")
    p.add_argument("--conversation", default=None, help="resume an existing conversation id")
    p.add_argument("--mode", default="socratic")
    p.add_argument("--no-stream", action="store_true")
    p.add_argument("--source", choices=["local", "hf"], help="override model source")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = RuntimeConfig()
    if args.source:
        cfg.model_source = args.source

    server = LlamaServer(cfg)
    # Engine logs go to a file so they don't clutter the conversation.
    _, managed = server.ensure(log_file="data/llama-server.log")
    store = ConversationStore(cfg.db_url)
    engine = ChatEngine(
        InferenceClient(cfg.base_url, model=cfg.model_alias, enable_thinking=cfg.enable_thinking),
        store,
        max_history_messages=cfg.max_history_messages,
    )

    conversation_id = args.conversation
    print(f"\nMuta · {cfg.model_alias} · mode={args.mode} · db={cfg.db_url}")
    print("Type your message; 'exit' or Ctrl-D to quit.\n")
    try:
        while True:
            try:
                message = input("you> ").strip()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                # Ctrl-C abandons the half-typed line, not the session.
                print("\n(use 'exit' or Ctrl-D to quit)")
                continue
            # A blank line re-prompts. It must never quit: a stray Enter pressed while a
            # reply streams is buffered by the tty and would otherwise end the session —
            # and take the engine down with it — on the next prompt.
            if not message:
                continue
            if message.lower() in {"exit", "quit"}:
                break

            print("tutor> ", end="", flush=True)
            try:
                if args.no_stream:
                    result = engine.chat(
                        args.student, message, conversation_id=conversation_id, mode=args.mode
                    )
                    conversation_id = result.conversation_id
                    print(result.reply)
                else:
                    conversation_id, tokens = engine.stream_chat(
                        args.student, message, conversation_id=conversation_id, mode=args.mode
                    )
                    for delta in tokens:
                        print(delta, end="", flush=True)
                    print()
            except KeyboardInterrupt:
                # Ctrl-C stops the reply being generated, not the session.
                print("\n(reply interrupted)")
            except httpx.HTTPError as e:
                # A transient engine failure must not end the session and lose the thread.
                print(f"\n[engine error: {type(e).__name__}] — conversation kept; try again.")
    finally:
        print(f"\nconversation id: {conversation_id}  (resume with --conversation {conversation_id})")
        store.close()
        if managed:
            server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
