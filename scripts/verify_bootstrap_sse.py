from __future__ import annotations

import http.client
import json
import time
import uuid


def read_sse_events(resp, *, timeout_s: float = 30.0):
    """Yield (event, data_dict) pairs (best-effort)."""
    event = None
    data_lines: list[str] = []
    start = time.time()
    while time.time() - start < timeout_s:
        raw = resp.readline()
        if not raw:
            break
        line = raw.decode("utf-8", "ignore").rstrip("\n")
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
            data_lines = []
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
        elif line.strip() == "":
            if event and data_lines:
                data_str = "\n".join(data_lines)
                try:
                    data = json.loads(data_str)
                except Exception:
                    data = {"_raw": data_str}
                yield event, data
            event = None
            data_lines = []


def main() -> None:
    host = "127.0.0.1"
    port = 8765

    def run_case(label: str, user_content: str):
        print("\n===", label, "===")
        thread_id = f"verify-bootstrap-{uuid.uuid4()}"
        body = {
            "threadId": thread_id,
            "runId": str(uuid.uuid4()),
            "messages": [{"role": "user", "content": user_content}],
            "humanInTheLoop": False,
        }

        conn = http.client.HTTPConnection(host, port, timeout=30)
        conn.request(
            "POST",
            "/api/chat",
            body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        print("status", resp.status)
        if resp.status != 200:
            print(resp.read().decode("utf-8", "ignore"))
            raise SystemExit(1)

        first_relevant = None
        seen = {"SkillUiBootstrap": 0, "SkillUiDataPatch": 0}
        patch_doc_ids: list[str] = []
        bootstrap_doc_ids: list[str] = []

        for ev, data in read_sse_events(resp, timeout_s=30.0):
            if ev == "SkillUiBootstrap":
                seen[ev] += 1
                if first_relevant is None:
                    first_relevant = ev
                meta = (data.get("document") or {}).get("meta") if isinstance(data, dict) else None
                doc_id = meta.get("docId") if isinstance(meta, dict) else None
                if isinstance(doc_id, str):
                    bootstrap_doc_ids.append(doc_id)
                print("event SkillUiBootstrap", "docId", doc_id)
            elif ev == "SkillUiDataPatch":
                seen[ev] += 1
                if first_relevant is None:
                    first_relevant = ev
                patch = data.get("patch") if isinstance(data, dict) else None
                doc_id = patch.get("docId") if isinstance(patch, dict) else None
                if isinstance(doc_id, str):
                    patch_doc_ids.append(doc_id)
                print("event SkillUiDataPatch", "docId", doc_id)
            if seen["SkillUiBootstrap"] >= 1 and seen["SkillUiDataPatch"] >= 1:
                break

        print("first_relevant_event", first_relevant)
        print("seen", seen)
        if bootstrap_doc_ids:
            print("bootstrap_docIds", bootstrap_doc_ids[:3])
        if patch_doc_ids:
            print("patch_docIds", patch_doc_ids[:3])

    # Case 1: test_sdui_v3 / run_asset_scan (docId=test:scan)
    run_case(
        "test_sdui_v3 (run_asset_scan)",
        "请直接调用工具 run_asset_scan，delay_seconds=0.2。并在右侧渲染 skill-ui://SduiView?dataFile=test-scan.json。",
    )

    # Case 2: 工勘大盘 pusher (AnalyzeSiteArtifactsTool uses default docId=dashboard:gc)
    run_case(
        "gc dashboard pusher (analyze_site_artifacts)",
        "请直接调用工具 analyze_site_artifacts，artifact_paths=[\"test-scan.json\"]。并在右侧渲染 skill-ui://SduiView?dataFile=workspace/dashboard.json。",
    )


if __name__ == "__main__":
    main()

