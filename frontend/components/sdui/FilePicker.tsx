"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Upload, CheckCircle2, AlertTriangle, Check } from "lucide-react";
import type { SduiFilePickerNode } from "@/lib/sdui";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import { SduiArtifactGrid } from "@/components/sdui/SduiArtifactGrid";
import { formatLegacyModuleActionBlockedMessage, useLegacyModuleActionAllowed } from "@/lib/legacyModuleGate";

type Props = SduiFilePickerNode & { cardId?: string };

type UploadedFileRecord = {
  fileId: string;
  name: string;
  logicalPath?: string;
  savedDir?: string;
  uploadedAt: number;
};

type UploadState =
  | { status: "idle" }
  | { status: "uploading"; progress: number; filename: string }
  | { status: "success"; filename: string; count: number }
  | { status: "error"; filename?: string; message: string };

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function aguiRequestPath(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
  }
  return path.startsWith("/") ? path : `/${path}`;
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
  saveRelativeDir,
  skillName,
  stateNamespace,
  stepId,
  hitlRequestId,
}: Props) {
  const { syncState, postToAgent } = useSkillUiRuntime();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const submitAnchorRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<UploadState>({ status: "idle" });
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFileRecord[]>([]);
  const [hitlSubmitted, setHitlSubmitted] = useState(false);
  const legacyGate = useLegacyModuleActionAllowed(moduleId);

  const pendingRequestId = useMemo(
    () => (hitlRequestId ?? "").trim() || (cardId ?? "").trim(),
    [hitlRequestId, cardId],
  );
  const isSkillHitl = Boolean((skillName ?? "").trim() && pendingRequestId);

  // 下一轮 HITL（新 hitlRequestId）或同卡被 SSE replace 时，必须清空「已提交」与本地文件列表，
  // 否则会卡在已提交且无法再次点击继续；用户只能重启技能才能再走 start。
  const skillHitlWaveKey = useMemo(
    () =>
      [
        (hitlRequestId ?? "").trim(),
        (cardId ?? "").trim(),
        String(purpose ?? ""),
        String(nextAction ?? ""),
        String(stepId ?? ""),
      ].join("|"),
    [hitlRequestId, cardId, purpose, nextAction, stepId],
  );

  const prevSkillHitlWaveKey = useRef<string | null>(null);
  useEffect(() => {
    if (!isSkillHitl) return;
    if (prevSkillHitlWaveKey.current === null) {
      prevSkillHitlWaveKey.current = skillHitlWaveKey;
      return;
    }
    if (prevSkillHitlWaveKey.current === skillHitlWaveKey) return;
    prevSkillHitlWaveKey.current = skillHitlWaveKey;
    setHitlSubmitted(false);
    setUploadedFiles([]);
    setState({ status: "idle" });
    setDragOver(false);
  }, [skillHitlWaveKey, isSkillHitl]);

  const uploadOne = useCallback(
    (file: File) =>
      new Promise<{ fileId: string; logicalPath?: string }>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", aguiRequestPath("/api/upload"), true);
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
        const dir = (saveRelativeDir ?? "").trim();
        if (dir) {
          fd.append("targetDir", dir);
        }
        xhr.send(fd);
      }),
    [purpose, saveRelativeDir],
  );

  const submitSkillHitlResult = useCallback(() => {
    if (hitlSubmitted || !isSkillHitl) return;
    const skill = (skillName ?? "").trim();
    const namespace = (stateNamespace ?? "").trim();
    const sid = (stepId ?? "").trim();
    if (uploadedFiles.length === 0) return;
    const latest = uploadedFiles[uploadedFiles.length - 1]!;
    postToAgent(
      JSON.stringify({
        type: "chat_card_intent",
        verb: "skill_runtime_result",
        payload: {
          type: "skill_runtime_result",
          skillName: skill,
          requestId: pendingRequestId,
          status: "ok",
          ...(namespace ? { stateNamespace: namespace } : {}),
          ...(sid ? { stepId: sid } : {}),
          result: {
            upload: latest,
            uploads: uploadedFiles,
          },
        },
      }),
    );
    setHitlSubmitted(true);
  }, [
    hitlSubmitted,
    isSkillHitl,
    skillName,
    pendingRequestId,
    stateNamespace,
    stepId,
    uploadedFiles,
    postToAgent,
  ]);

  const finishUpload = useCallback(
    async (files: File[]) => {
      try {
        if (isSkillHitl && hitlSubmitted) return;
        const chosen = multiple ? files : files.slice(0, 1);
        if (!chosen.length) return;
        const baseUploads = multiple ? uploadedFiles : [];
        const nextUploads: UploadedFileRecord[] = [...baseUploads];

        for (const file of chosen) {
          setState({ status: "uploading", progress: 0, filename: file.name });
          const { fileId, logicalPath } = await uploadOne(file);
          nextUploads.push({
            fileId,
            name: file.name,
            logicalPath,
            savedDir: saveRelativeDir,
            uploadedAt: Date.now(),
          });
        }

        setUploadedFiles(nextUploads);
        const latest = nextUploads[nextUploads.length - 1];
        setState({
          status: "success",
          filename: latest?.name ?? chosen[chosen.length - 1]!.name,
          count: nextUploads.length,
        });
        syncState({
          key: `uploads.${purpose}`,
          value: nextUploads,
          behavior: "immediate",
        });
        const mid = (moduleId ?? "").trim();
        const na = (nextAction ?? "").trim();
        const cid = (cardId ?? "").trim();
        if (latest) {
          if (isSkillHitl) {
            // Skill-first: 仅落盘 + 本地累积；由用户点击「完成上传并继续」一次性 resume。
            queueMicrotask(() => {
              requestAnimationFrame(() => {
                submitAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
              });
            });
            return;
          }

          // Legacy fallback: keep module_action only when no skill context is provided.
          if (mid && na && cid) {
            if (!legacyGate.allowed) {
              setState({
                status: "error",
                filename: latest?.name,
                message: formatLegacyModuleActionBlockedMessage(mid, legacyGate.reason),
              });
              return;
            }
            postToAgent(
              JSON.stringify({
                type: "chat_card_intent",
                verb: "module_action",
                cardId: cid,
                payload: {
                  moduleId: mid,
                  action: na,
                  state: {
                    upload: latest,
                    uploads: nextUploads,
                  },
                },
              }),
            );
            return;
          }
        }
      } catch (err) {
        setState({
          status: "error",
          filename: files[0]?.name,
          message: err instanceof Error ? err.message : String(err),
        });
      }
    },
    [
      uploadOne,
      syncState,
      purpose,
      moduleId,
      nextAction,
      cardId,
      postToAgent,
      multiple,
      saveRelativeDir,
      uploadedFiles,
      isSkillHitl,
      hitlSubmitted,
      legacyGate.allowed,
      legacyGate.reason,
    ],
  );

  const skillLocked = isSkillHitl && hitlSubmitted;

  const onPick = () => {
    if (state.status === "uploading" || skillLocked) return;
    inputRef.current?.click();
  };

  const onChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (!files.length) return;
    await finishUpload(files);
    e.target.value = "";
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (state.status === "uploading" || skillLocked) return;
    setDragOver(true);
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  };

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (state.status === "uploading" || skillLocked) return;
    const files = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
    if (!files.length) return;
    await finishUpload(files);
  };

  return (
    <div
      className={[
        "rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] p-4",
        skillLocked ? "pointer-events-none opacity-70" : "",
      ].join(" ")}
      data-testid="sdui-file-picker"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 h-9 w-9 rounded-lg flex items-center justify-center bg-[var(--surface-3)] border border-[var(--border-subtle)]">
          <Upload className="h-4 w-4 ui-text-secondary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold ui-text-primary">{label}</div>
          {helpText ? <div className="mt-1 text-xs ui-text-secondary leading-relaxed">{helpText}</div> : null}
          {(saveRelativeDir ?? "").trim() ? (
            <div className="mt-1 font-mono text-[10px] ui-text-muted opacity-90">
              保存目录（workspace 相对）：{(saveRelativeDir ?? "").trim().replace(/\\/g, "/").replace(/\/$/, "")}/
            </div>
          ) : null}

          <div
            role="button"
            aria-label="点击选择或将文件拖拽至此上传"
            tabIndex={skillLocked ? -1 : 0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onPick();
              }
            }}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={onPick}
            className={[
              "mt-3 min-h-[120px] rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors cursor-pointer select-none flex flex-col items-center justify-center gap-2",
              dragOver
                ? "border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_12%,var(--surface-2))]"
                : "border-[var(--border-subtle)] bg-[var(--surface-3)]/40 hover:border-[var(--accent)]/50",
              state.status === "uploading" ? "pointer-events-none opacity-80" : "",
              skillLocked ? "pointer-events-none opacity-60" : "",
            ].join(" ")}
          >
            <Upload className="h-8 w-8 ui-text-muted opacity-60" aria-hidden />
            <p className="text-sm font-medium ui-text-primary">点击选择，或将文件拖拽至此</p>
          </div>

          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onPick();
              }}
              disabled={state.status === "uploading" || skillLocked}
              className={[
                "rounded-lg px-3 py-1.5 text-sm font-medium ui-btn-accent inline-flex items-center gap-1.5",
                state.status === "uploading" || skillLocked ? "opacity-70 cursor-not-allowed" : "",
              ].join(" ").trim()}
            >
              {uploadedFiles.length > 0 ? (
                <Check className="h-4 w-4" aria-hidden />
              ) : null}
              {state.status === "uploading"
                ? "上传中…"
                : uploadedFiles.length > 0
                  ? multiple
                    ? "继续添加文件"
                    : "重新选择文件"
                  : "选择文件"}
            </button>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              accept={accept}
              multiple={Boolean(multiple)}
              onChange={onChange}
              disabled={skillLocked}
            />
            {state.status === "success" ? (
              <span className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--success)" }}>
                <CheckCircle2 className="h-4 w-4" aria-hidden />
                已上传 {state.count} 个文件，最近一个：{state.filename}
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

          {uploadedFiles.length > 0 ? (
            <div className="mt-4">
              <SduiArtifactGrid
                title="已选择文件"
                mode="input"
                artifacts={uploadedFiles.map((item) => ({
                  id: item.fileId,
                  label: item.name,
                  path: item.logicalPath ?? "",
                  kind: "other",
                  status: "ready",
                }))}
              />
            </div>
          ) : null}

          {isSkillHitl && !hitlSubmitted ? (
            <div ref={submitAnchorRef} className="mt-5">
              <button
                type="button"
                disabled={uploadedFiles.length === 0 || state.status === "uploading"}
                onClick={(e) => {
                  e.stopPropagation();
                  submitSkillHitlResult();
                }}
                className={[
                  "w-full min-h-[44px] rounded-lg px-4 py-3 text-sm font-semibold ui-btn-accent",
                  "shadow-sm border border-[color-mix(in_oklab,var(--accent)_35%,transparent)]",
                  "disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none",
                ].join(" ")}
              >
                完成上传并继续
              </button>
              <p className="mt-2 text-center text-xs ui-text-secondary">
                上传完成后请点击「完成上传并继续」，以继续流程
              </p>
            </div>
          ) : null}

          {isSkillHitl && hitlSubmitted ? (
            <div className="mt-5 flex items-center justify-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-3)] py-3 text-sm font-semibold text-[var(--success)]">
              <CheckCircle2 className="h-5 w-5 shrink-0" aria-hidden />
              已提交
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
