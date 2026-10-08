#!/usr/bin/env python3
"""Idempotently prepare the small, local-only state used in the ADTC pitch demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orchestrator.gateway.sharing import SharingService
from orchestrator.pedagogy.twin import TwinStore
from runtime.paths import data_root as configured_data_root
from runtime.sqlite_memory import SQLiteConversationStore

COURSE_NAME = "SS2 Mathematics"
QUESTION = "Why must I subtract 4 from both sides of x/3 + 4 = 10?"
REPLIES = (
    "Think of both sides as a balanced scale: the same 4 must leave both pans.",
    "After removing 4 from both sides, what expression remains on the left?",
)


def _ensure_user(service: SharingService, username: str, password: str) -> dict:
    user = next((row for row in service.users() if row["username"].casefold() == username.casefold()), None)
    if user is None:
        service.signup(username, password, throttle_key=f"pitch-seed:{username.casefold()}")
        user = next(row for row in service.users() if row["username"].casefold() == username.casefold())
    if user["status"] == "pending":
        user = service.approve(user["id"])
    if user["status"] != "approved":
        raise RuntimeError(f"demo learner {username!r} is not available")
    return user


def seed_demo(root: Path, *, password: str) -> dict:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    service = SharingService(root / "muta-share.sqlite3")
    conversations = SQLiteConversationStore(f"sqlite:///{root / 'muta.sqlite3'}")
    try:
        current = service.settings()
        service.update_settings(enabled=True, memory_mode=current["memory_mode"])
        ada = _ensure_user(service, "Ada", password)
        kwame = _ensure_user(service, "Kwame", password)

        course = next((row for row in service.courses() if row["name"] == COURSE_NAME), None)
        course_values = {
            "name": COURSE_NAME,
            "teaching_style": "hints",
            "lock_style": True,
            "withhold_final_answers": True,
            "teacher_note": "Explain why each balance step is valid; let the learner finish.",
        }
        course = (
            service.update_course(course["id"], **course_values)
            if course
            else service.create_course(**course_values)
        )

        post = next((row for row in service.class_posts(limit=100) if row["body"] == QUESTION), None)
        if post is None:
            post = service.create_class_post(ada["id"], body=QUESTION, addressed_to_teacher=True)
        thread = service.class_thread(post["id"])
        existing = {row["body"]: row for row in thread["replies"]}
        reply_rows = []
        for index, body in enumerate(REPLIES):
            row = existing.get(body)
            if row is None:
                row = service.create_class_reply(
                    post["id"], kwame["id"] if index == 0 else ada["id"], body=body
                )
            reply_rows.append(row)
        if not reply_rows[0]["teacher_verified"]:
            reply_rows[0] = service.verify_class_reply(reply_rows[0]["id"], verified=True)

        conversations.patch_settings(
            ada["id"],
            {
                "allow_parallel_chats": True,
                "power_optimization_enabled": True,
                "preferred_style": "analogy",
                "study_country": "NG",
            },
        )
        twins = TwinStore(root / "twins")
        twin = twins.load(ada["id"])
        twin.record_preference("teaching_style", "everyday examples")
        twin.record_preference("explanation", "wants the why, not rules")
        twin.record_preference("study_country", "Nigeria")
        twins.save(twin)

        return {
            "data_root": str(root),
            "learners": {"Ada": ada["id"], "Kwame": kwame["id"]},
            "course_id": course["id"],
            "class_post_id": post["id"],
            "verified_reply_id": reply_rows[0]["id"],
        }
    finally:
        conversations.close()
        service.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=configured_data_root())
    parser.add_argument(
        "--password",
        default="MutaDemo2026!",
        help="Demo-only learner password. Override it for any non-disposable environment.",
    )
    args = parser.parse_args()
    print(json.dumps(seed_demo(args.data_root, password=args.password), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
