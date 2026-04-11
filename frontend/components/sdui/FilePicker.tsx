"use client";

import { useRef, useState } from "react";
import { Upload, CheckCircle2, AlertTriangle, Check } from "lucide-react";
import type { SduiFilePickerNode } from "@/lib/sdui";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";

type Props = SduiFilePickerNode & { cardId?: string };

type UploadState =
  | { status: "idle" }
  | { status: "uploading"; progress: number; filename: string }
  | { status: "success_anim"; filename: string; fileId: string; logicalPath?: string }
  | { status: "success"; filename: string; fileId: string; logicalPath?: string }
  | { status: "error"; filename?: string; message: string };

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

export function SduiFilePicker({
  purpose,
  label = "上传文件",
  helpText,
  accept,
  multiple,
  moduleId,
  nextAction,
  cardId,
}: Props) {
  const { syncState, postToAgent } = useSkillUiRuntime();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [state, setState] = useState<UploadState>({ status: "idle" });

  const onPick = () => {
    if (state.status === "success" || state.status === "success_anim") return;
    inputRef.current?.click();
  };

  const uploadOne = (file: File) =>
    new Promise<{ fileId: string; logicalPath?: string }>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload", true);
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        setState({ status: "uploading", progress: clamp01(e.loaded / e.total), filename: file.name });
      };
      xhr.onerror = () => reject(new Error("upload failed"));
      xhr.onload = () => {
        const ok = xhr.status >= 200 && xhr.status < 300;
        const res = (xhr.response ?? {}) as { fileId?: unknown; logicalPath?: unknown; detail?: unknown };
        if (!ok) {
          reject(new Error(typeof res.detail === "string" ? res.detail : `HTTP ${xhr.status}`));
          return;
        }
        const fileId = typeof res.fileId === "string" ? res.fileId : "";
        const logicalPath = typeof res.logicalPath === "string" ? res.logicalPath : undefined;
        if (!fileId) {
          reject(new Error("missing fileId"));
          return;
        }
        resolve({ fileId, logicalPath });
      };
      const fd = new FormData();
      fd.append("purpose", purpose);
      fd.append("file", file, file.name);
      xhr.send(fd);
    });

  const onChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (!files.length) return;
    const first = files[0]!;
    try {
      setState({ status: "uploading", progress: 0, filename: first.name });
      const { fileId, logicalPath } = await uploadOne(first);
      setState({ status: "success_anim", filename: first.name, fileId, logicalPath });
      window.setTimeout(() => {
        setState({ status: "success", filename: first.name, fileId, logicalPath });
        syncState({
          key: `uploads.${purpose}`,
          value: { fileId, name: first.name, logicalPath },
          behavior: "immediate",
        });
        const mid = (moduleId ?? "").trim();
        const na = (nextAction ?? "").trim();
        const cid = (cardId ?? "").trim();
        if (mid && na && cid) {
          postToAgent(
            JSON.stringify({
              type: "chat_card_intent",
              verb: "module_action",
              cardId: cid,
              payload: {
                moduleId: mid,
                action: na,
                state: {
                  upload: { fileId, name: first.name, logicalPath },
                },
              },
            })
          );
        }
      }, 300);
    } catch (err) {
      setState({ status: "error", filename: first?.name, message: err instanceof Error ? err.message : String(err) });
    } finally {
      e.target.value = "";
    }
  };

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 h-9 w-9 rounded-lg flex items-center justify-center bg-[var(--surface-3)] border border-[var(--border-subtle)]">
          <Upload className="h-4 w-4 ui-text-secondary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold ui-text-primary">{label}</div>
          {helpText ? <div className="mt-1 text-xs ui-text-secondary leading-relaxed">{helpText}</div> : null}

          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={onPick}
              disabled={state.status === "success" || state.status === "success_anim"}
              className={[
                "rounded-lg px-3 py-1.5 text-sm font-medium ui-btn-accent inline-flex items-center gap-1.5",
                state.status === "success" || state.status === "success_anim" ? "opacity-70 cursor-not-allowed" : "",
              ].join(" ").trim()}
            >
              {state.status === "success" || state.status === "success_anim" ? (
                <Check className="h-4 w-4" aria-hidden />
              ) : null}
              {state.status === "success" || state.status === "success_anim" ? "已锁定" : "选择文件"}
            </button>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              accept={accept}
              multiple={Boolean(multiple)}
              onChange={onChange}
            />
            {state.status === "success" || state.status === "success_anim" ? (
              <span className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--success)" }}>
                <CheckCircle2 className="h-4 w-4" aria-hidden />
                已上传：{state.filename}
              </span>
            ) : state.status === "error" ? (
              <span className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--danger)" }}>
                <AlertTriangle className="h-4 w-4" aria-hidden />
                上传失败：{state.message}
              </span>
            ) : state.status === "uploading" ? (
              <span className="text-xs ui-text-secondary">上传中… {Math.round(state.progress * 100)}%</span>
            ) : null}
          </div>

          {state.status === "uploading" ? (
            <div className="mt-3 h-2 w-full rounded-full bg-[var(--surface-3)] overflow-hidden border border-[var(--border-subtle)]">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.round(state.progress * 100)}%`,
                  background: "var(--accent)",
                }}
              />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
