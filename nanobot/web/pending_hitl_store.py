from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import aiosqlite

TerminalStatus = Literal["pending", "consumed", "timeout", "cancelled"]


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class PendingHitlStore:
    db_path: Path

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_hitl_requests (
                    request_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    skill_run_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    resume_action TEXT NOT NULL,
                    on_cancel_action TEXT NULL,
                    expires_at_ms INTEGER NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    consumed_at_ms INTEGER NULL,
                    created_at_ms INTEGER NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_hitl_results (
                    request_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    action TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                )
                """
            )
            await db.commit()

    async def create_pending_request(self, envelope: dict[str, Any]) -> bool:
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            raise ValueError("invalid envelope payload")
        request_id = str(payload.get("requestId") or "").strip()
        if not request_id:
            raise ValueError("missing requestId")

        thread_id = str(envelope.get("threadId") or "").strip()
        skill_name = str(envelope.get("skillName") or payload.get("skillName") or "").strip()
        skill_run_id = str(envelope.get("skillRunId") or "").strip()
        event = str(envelope.get("event") or "").strip()
        resume_action = str(payload.get("resumeAction") or "").strip()
        on_cancel_action = str(payload.get("onCancelAction") or "").strip() or None
        expires_at_ms = payload.get("expiresAt")
        expires_at_ms_i = int(expires_at_ms) if isinstance(expires_at_ms, (int, float)) else None

        if not thread_id:
            raise ValueError("missing threadId")
        if not skill_name:
            raise ValueError("missing skillName")
        if not skill_run_id:
            raise ValueError("missing skillRunId")
        if not event:
            raise ValueError("missing event")
        if not resume_action:
            raise ValueError("missing resumeAction")

        created_at_ms = _now_ms()
        payload_json = json.dumps(payload, ensure_ascii=False)

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT OR IGNORE INTO pending_hitl_requests (
                    request_id, thread_id, skill_name, skill_run_id, event, payload_json,
                    resume_action, on_cancel_action, expires_at_ms, status, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    request_id,
                    thread_id,
                    skill_name,
                    skill_run_id,
                    event,
                    payload_json,
                    resume_action,
                    on_cancel_action,
                    expires_at_ms_i,
                    created_at_ms,
                ),
            )
            await db.commit()
            return cur.rowcount == 1

    async def get_pending_request(self, request_id: str) -> dict[str, Any] | None:
        rid = str(request_id or "").strip()
        if not rid:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT
                    request_id,
                    thread_id,
                    skill_name,
                    skill_run_id,
                    event,
                    payload_json,
                    resume_action,
                    on_cancel_action,
                    expires_at_ms,
                    status,
                    consumed_at_ms,
                    created_at_ms
                FROM pending_hitl_requests
                WHERE request_id = ?
                """,
                (rid,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            (
                request_id,
                thread_id,
                skill_name,
                skill_run_id,
                event,
                payload_json,
                resume_action,
                on_cancel_action,
                expires_at_ms,
                status,
                consumed_at_ms,
                created_at_ms,
            ) = row
            return {
                "request_id": request_id,
                "thread_id": thread_id,
                "skill_name": skill_name,
                "skill_run_id": skill_run_id,
                "event": event,
                "payload_json": payload_json,
                "resume_action": resume_action,
                "on_cancel_action": on_cancel_action,
                "expires_at_ms": expires_at_ms,
                "status": status,
                "consumed_at_ms": consumed_at_ms,
                "created_at_ms": created_at_ms,
            }

    async def consume_result(self, result_envelope: dict[str, Any]) -> dict[str, Any]:
        request_id = str(result_envelope.get("requestId") or "").strip()
        if not request_id:
            raise ValueError("missing requestId")
        thread_id = str(result_envelope.get("threadId") or "").strip()
        skill_name = str(result_envelope.get("skillName") or "").strip()
        if not thread_id:
            raise ValueError("missing threadId")
        if not skill_name:
            raise ValueError("missing skillName")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                """
                SELECT request_id, thread_id, skill_name, resume_action, on_cancel_action, status
                FROM pending_hitl_requests
                WHERE request_id = ?
                """,
                (request_id,),
            )
            row = await cur.fetchone()
            if row is None:
                await db.rollback()
                raise ValueError("requestId not found")

            _rid, t_id, s_name, resume_action, on_cancel_action, status = row
            if str(t_id) != thread_id:
                await db.rollback()
                raise ValueError("thread_id mismatch")
            if str(s_name) != skill_name:
                await db.rollback()
                raise ValueError("skill_name mismatch")

            terminal_status: TerminalStatus = str(status)
            if terminal_status != "pending":
                # Idempotent replay: do not resume twice.
                await db.commit()
                return {"ok": True, "duplicate": True, "terminal_status": terminal_status}

            # Mark consumed.
            now_ms = _now_ms()
            await db.execute(
                "UPDATE pending_hitl_requests SET status='consumed', consumed_at_ms=? WHERE request_id=?",
                (now_ms, request_id),
            )

            status_in = str(result_envelope.get("status") or "").strip() or "ok"
            # Hard Rule (Fallback Routing): on_cancel_action -> resume_action for cancel/timeout/error.
            # Never trust client-provided action for non-ok statuses.
            if status_in in {"cancel", "timeout", "error"}:
                action_in = str(on_cancel_action or "").strip() or str(resume_action)
            else:
                action_in = str(result_envelope.get("action") or "").strip() or str(resume_action)
            result_payload = result_envelope.get("result")
            result_json = json.dumps(
                {"status": status_in, "result": result_payload},
                ensure_ascii=False,
            )
            await db.execute(
                """
                INSERT OR REPLACE INTO pending_hitl_results (
                    request_id, status, action, result_json, created_at_ms
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (request_id, "consumed", action_in, result_json, now_ms),
            )
            await db.commit()
            return {"ok": True, "duplicate": False, "terminal_status": "consumed"}

    async def timeout_expired_requests(self, *, now_ms: int | None = None) -> dict[str, Any]:
        now = int(now_ms) if now_ms is not None else _now_ms()
        timed_out: list[str] = []

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                """
                SELECT request_id, resume_action, on_cancel_action
                FROM pending_hitl_requests
                WHERE status='pending' AND expires_at_ms IS NOT NULL AND expires_at_ms <= ?
                ORDER BY request_id ASC
                """,
                (now,),
            )
            rows = await cur.fetchall()
            for request_id, resume_action, on_cancel_action in rows or []:
                rid = str(request_id)
                # Transition to timeout terminal state.
                upd = await db.execute(
                    "UPDATE pending_hitl_requests SET status='timeout', consumed_at_ms=? WHERE request_id=? AND status='pending'",
                    (now, rid),
                )
                if (upd.rowcount or 0) <= 0:
                    continue
                timed_out.append(rid)

                # Fallback routing rule: on_cancel_action -> resume_action
                action = str(on_cancel_action or "").strip() or str(resume_action)
                result_json = json.dumps({"status": "timeout"}, ensure_ascii=False)
                await db.execute(
                    """
                    INSERT OR REPLACE INTO pending_hitl_results (
                        request_id, status, action, result_json, created_at_ms
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (rid, "timeout", action, result_json, now),
                )
            await db.commit()

        return {"timed_out_request_ids": timed_out}

    async def get_result_for_request(self, request_id: str) -> dict[str, Any] | None:
        rid = str(request_id or "").strip()
        if not rid:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT request_id, status, action, result_json, created_at_ms
                FROM pending_hitl_results
                WHERE request_id = ?
                """,
                (rid,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            request_id, status, action, result_json, created_at_ms = row
            return {
                "request_id": request_id,
                "status": status,
                "action": action,
                "result_json": result_json,
                "created_at_ms": created_at_ms,
            }

