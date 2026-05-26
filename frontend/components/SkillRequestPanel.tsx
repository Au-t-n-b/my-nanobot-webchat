"use client";

import { CheckCircle2, XCircle, AlertTriangle, ChevronDown, ChevronUp, Clock, Eye, Zap, Shield, ShieldOff, RefreshCw, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

function apiPath(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
  }
  return path;
}

type SkillRequest = {
  id: string;
  action: "create" | "edit" | "patch" | "delete";
  skill_name: string;
  proposed_content: string | null;
  old_string: string | null;
  new_string: string | null;
  reason: string;
  trigger_session: string | null;
  trigger_conversation: string | null;
  status: "pending" | "approved" | "rejected" | "expired" | "blocked_by_blacklist" | "merged_with_existing" | "covered_by_existing";
  priority: number;
  conflict_ids: string | null;
  created_at: string;
  expires_at: string;
  reviewed_at: string | null;
  reviewer_note: string | null;
  duplicate_count: number;
  last_matched_at: string | null;
  similarity_key: string | null;
  maybe_duplicate_ids: string | null;
  related_existing_skill_ids: string | null;
  related_existing_skill_note: string | null;
  existing_coverage_status: string | null;
};

type BlacklistEntry = {
  id: string;
  skill_name: string;
  similarity_key: string;
  reason: string | null;
  reviewer_note: string | null;
  source_request_id: string | null;
  created_at: string;
  updated_at: string | null;
  expires_at: string | null;
  enabled: number;
};

type DuplicateEvent = {
  id: string;
  target_request_id: string;
  candidate_skill_name: string | null;
  candidate_reason: string | null;
  candidate_trigger_conversation: string | null;
  candidate_content_excerpt: string | null;
  judge_confidence: number | null;
  judge_reason_zh: string | null;
  created_at: string;
};

const ACTION_COLORS: Record<string, { bg: string; text: string }> = {
  create: { bg: "rgba(16,185,129,0.15)", text: "rgb(110,231,183)" },
  edit: { bg: "rgba(59,130,246,0.15)", text: "rgb(147,197,253)" },
  patch: { bg: "rgba(234,179,8,0.15)", text: "rgb(250,204,21)" },
  delete: { bg: "rgba(239,68,68,0.15)", text: "rgb(248,113,113)" },
};

function ActionBadge({ action }: { action: string }) {
  const colors = ACTION_COLORS[action] ?? ACTION_COLORS.edit;
  return (
    <span
      className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase"
      style={{ background: colors.bg, color: colors.text }}
    >
      {action}
    </span>
  );
}

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

const REJECT_QUICK_REASONS = [
  { label: "太具体/一次性", value: "Too specific" },
  { label: "已有重复", value: "Duplicate" },
  { label: "判断错误", value: "Wrong" },
  { label: "没有价值", value: "Not useful" },
  { label: "时机不合适", value: "Bad timing" },
  { label: "其他", value: "Other" },
];

export function SkillRequestPanel() {
  const [requests, setRequests] = useState<SkillRequest[]>([]);
  const [blacklist, setBlacklist] = useState<BlacklistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [detailModal, setDetailModal] = useState<SkillRequest | null>(null);
  const [actionBusy, setActionBusy] = useState<Set<string>>(new Set());
  const [rejectModal, setRejectModal] = useState<{ id: string; busy: boolean } | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectCustom, setRejectCustom] = useState("");
  const [rejectBlacklist, setRejectBlacklist] = useState(false);
  const rejectTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [showBlacklist, setShowBlacklist] = useState(false);
  // Duplicate events state (per-request)
  const [dupEvents, setDupEvents] = useState<Map<string, DuplicateEvent[]>>(new Map());
  const [dupEventsLoaded, setDupEventsLoaded] = useState<Set<string>>(new Set());
  const [dupSectionOpen, setDupSectionOpen] = useState<Set<string>>(new Set());
  const [selectedEvts, setSelectedEvts] = useState<Map<string, Set<string>>>(new Map());
  const [otherExtra, setOtherExtra] = useState<Map<string, string>>(new Map());
  const [generating, setGenerating] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [reqRes, blRes] = await Promise.all([
        fetch(apiPath("/api/skill-requests")),
        fetch(apiPath("/api/skill-blacklist")),
      ]);
      if (!reqRes.ok) throw new Error(`HTTP ${reqRes.status}`);
      const reqData = await reqRes.json();
      setRequests(reqData.items ?? []);
      if (blRes.ok) {
        const blData = await blRes.json();
        setBlacklist(blData.items ?? []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDupEvents = useCallback(async (reqId: string) => {
    try {
      const res = await fetch(apiPath(`/api/skill-requests/${reqId}/duplicate-events`));
      if (!res.ok) return;
      const data = await res.json();
      setDupEvents((prev) => new Map(prev).set(reqId, data.items ?? []));
      setDupEventsLoaded((prev) => new Set(prev).add(reqId));
    } catch { /* events are supplementary */ }
  }, []);

  const generateEnhanced = async (reqId: string) => {
    setGenerating((prev) => new Set(prev).add(reqId));
    setError("");
    const selected = Array.from(selectedEvts.get(reqId) ?? []);
    const extra = otherExtra.get(reqId) ?? "";
    try {
      const res = await fetch(apiPath(`/api/skill-requests/${reqId}/generate-enhanced`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected_duplicate_event_ids: selected, other_extra: extra }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.error?.message ?? body.message ?? `HTTP ${res.status}`);
      }
      if (body.status === "error" || body.status === "needs_human_resolution") {
        setError(body.message ?? body.conflicts?.[0]?.topic_zh ?? "生成失败");
      } else {
        await load();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成增强版失败");
    } finally {
      setGenerating((prev) => { const n = new Set(prev); n.delete(reqId); return n; });
    }
  };

  useEffect(() => {
    void load();
  }, [load]);

  const approve = async (id: string) => {
    setActionBusy((prev) => new Set(prev).add(id));
    try {
      const res = await fetch(apiPath(`/api/skill-requests/${id}/approve`), { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        if (res.status === 409) {
          setError(`文件冲突：${body.error?.message ?? "目标文件已变化，请检查后重新提交。"}`);
        } else {
          throw new Error(body.error?.message ?? `HTTP ${res.status}`);
        }
        return;
      }
      setRequests((prev) => prev.map((r) => (r.id === id ? { ...r, status: "approved" as const } : r)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "审批失败");
    } finally {
      setActionBusy((prev) => { const n = new Set(prev); n.delete(id); return n; });
    }
  };

  const submitReject = async (id: string, note: string, blacklist: boolean) => {
    setRejectModal((prev) => prev ? { ...prev, busy: true } : null);
    setActionBusy((prev) => new Set(prev).add(id));
    try {
      const res = await fetch(apiPath(`/api/skill-requests/${id}/reject`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note, blacklist }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error?.message ?? `HTTP ${res.status}`);
      }
      setRequests((prev) => prev.map((r) => (r.id === id ? { ...r, status: "rejected" as const } : r)));
      if (blacklist) {
        // Reload blacklist entries
        void load();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "拒绝失败");
    } finally {
      setActionBusy((prev) => { const n = new Set(prev); n.delete(id); return n; });
      setRejectModal(null);
      setRejectReason("");
      setRejectCustom("");
      setRejectBlacklist(false);
    }
  };

  const openRejectModal = (id: string) => {
    setRejectReason("");
    setRejectCustom("");
    setRejectBlacklist(false);
    setRejectModal({ id, busy: false });
    setTimeout(() => rejectTextareaRef.current?.focus(), 50);
  };

  const confirmReject = () => {
    if (!rejectModal) return;
    const detail = rejectCustom.trim();
    const note = detail ? `${rejectReason}: ${detail}` : rejectReason || "Other";
    void submitReject(rejectModal.id, note, rejectBlacklist);
  };

  const disableBlacklist = async (id: string) => {
    try {
      const res = await fetch(apiPath(`/api/skill-blacklist/${id}/disable`), { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setBlacklist((prev) => prev.map((e) => (e.id === id ? { ...e, enabled: 0 } : e)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "解除黑名单失败");
    }
  };

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const pending = requests.filter((r) => r.status === "pending");
  const others = requests.filter((r) => r.status !== "pending");
  const conflictIds = new Set<string>();
  for (const r of pending) {
    if (r.conflict_ids) {
      try {
        const ids: string[] = JSON.parse(r.conflict_ids);
        for (const id of ids) conflictIds.add(id);
      } catch { /* ignore */ }
    }
  }

  const enabledBlacklist = blacklist.filter((e) => e.enabled === 1);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto px-4 py-4">
      <div className="flex flex-col gap-4 pb-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
            Skill 变更审核
          </h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowBlacklist(!showBlacklist)}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium"
              style={{
                background: showBlacklist ? "rgba(239,68,68,0.15)" : "var(--surface-3)",
                color: showBlacklist ? "rgb(248,113,113)" : "var(--text-secondary)",
              }}
            >
              {showBlacklist ? <ShieldOff size={12} /> : <Shield size={12} />}
              黑名单 {enabledBlacklist.length > 0 ? `(${enabledBlacklist.length})` : ""}
            </button>
            <span
              className="rounded-full px-2 py-0.5 text-[11px] font-bold"
              style={{ background: pending.length > 0 ? "rgba(234,179,8,0.15)" : "var(--surface-3)", color: pending.length > 0 ? "rgb(250,204,21)" : "var(--text-tertiary)" }}
            >
              {pending.length} 待审核
            </span>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "rgb(248,113,113)" }}>
            {error}
          </div>
        )}

        {loading && requests.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>加载中...</p>
        ) : pending.length === 0 && others.length === 0 && !showBlacklist ? (
          <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>暂无变更请求。</p>
        ) : null}

        {/* Blacklist management panel */}
        {showBlacklist && (
          <section className="rounded-xl p-4" style={{ background: "var(--surface-2)", border: "1px solid var(--border-subtle)" }}>
            <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
              Hermes 黑名单
            </h3>
            <p className="text-[11px] mb-3" style={{ color: "var(--text-tertiary)" }}>
              命中黑名单后，Hermes 将不再生成类似建议。
            </p>
            {blacklist.length === 0 ? (
              <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>暂无黑名单条目。</p>
            ) : (
              <div className="flex flex-col gap-2">
                {blacklist.map((entry) => (
                  <div
                    key={entry.id}
                    className="flex items-center gap-2 rounded-lg px-3 py-2"
                    style={{
                      background: "var(--surface-3)",
                      opacity: entry.enabled ? 1 : 0.5,
                    }}
                  >
                    {entry.enabled ? <Shield size={12} style={{ color: "rgb(248,113,113)" }} /> : <ShieldOff size={12} style={{ color: "var(--text-tertiary)" }} />}
                    <span className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                      {entry.skill_name}
                    </span>
                    {entry.reviewer_note && (
                      <span className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>
                        — {entry.reviewer_note.slice(0, 60)}
                      </span>
                    )}
                    <span className="text-[10px] ml-auto" style={{ color: "var(--text-tertiary)" }}>
                      {formatDate(entry.created_at)}
                    </span>
                    {entry.enabled ? (
                      <button
                        type="button"
                        onClick={() => void disableBlacklist(entry.id)}
                        className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                        style={{ color: "rgb(147,197,253)" }}
                      >
                        解除
                      </button>
                    ) : (
                      <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>已解除</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Pending requests */}
        {pending.map((req) => {
          const hasConflict = conflictIds.has(req.id);
          const isExpanded = expanded.has(req.id);
          const busy = actionBusy.has(req.id);
          const hasDuplicate = (req.duplicate_count ?? 0) > 0;
          const maybeRelated = req.maybe_duplicate_ids ? (() => {
            try { return (JSON.parse(req.maybe_duplicate_ids) as string[]).length > 0; } catch { return false; }
          })() : false;

          return (
            <section
              key={req.id}
              className="rounded-xl p-4 flex flex-col gap-2"
              style={{
                background: "var(--surface-2)",
                border: `1px solid ${hasConflict ? "rgba(239,68,68,0.3)" : hasDuplicate ? "rgba(234,179,8,0.3)" : maybeRelated ? "rgba(147,197,253,0.2)" : "var(--border-subtle)"}`,
              }}
            >
              <div className="flex items-center gap-2 flex-wrap">
                {(req.priority ?? 0) > 0 && !hasDuplicate && (
                  <span className="inline-flex items-center gap-0.5 text-[10px] font-bold" style={{ color: "rgb(250,204,21)" }}>
                    <Zap size={12} /> 高优先级
                  </span>
                )}
                {hasDuplicate && (
                  <span className="inline-flex items-center gap-0.5 text-[10px] font-bold rounded-full px-1.5 py-0.5" style={{ background: "rgba(234,179,8,0.15)", color: "rgb(250,204,21)" }}>
                    <RefreshCw size={10} /> 已有 {req.duplicate_count} 次相似萃取，已合并并延长审核宽限期
                  </span>
                )}
                {!hasDuplicate && maybeRelated && (
                  <span className="inline-flex items-center gap-0.5 text-[10px] font-medium rounded-full px-1.5 py-0.5" style={{ background: "rgba(147,197,253,0.15)", color: "rgb(147,197,253)" }}>
                    发现可能相关建议，但语义不同，未自动合并
                  </span>
                )}
                <ActionBadge action={req.action} />
                <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                  {req.skill_name}
                </span>
                {hasConflict && (
                  <span className="inline-flex items-center gap-0.5 text-[10px] font-bold" style={{ color: "rgb(248,113,113)" }}>
                    <AlertTriangle size={12} /> 冲突
                  </span>
                )}
                <span className="ml-auto text-[11px]" style={{ color: "var(--text-tertiary)" }}>
                  {formatDate(req.created_at)}
                </span>
              </div>

              <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                {req.reason}
              </p>

              {req.trigger_session && (
                <p className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>
                  来源: {req.trigger_session}
                </p>
              )}

              {hasDuplicate && (
                <p className="text-[11px]" style={{ color: "rgb(250,204,21)" }}>
                  该建议被 Hermes 多次独立提出，可能代表一个稳定可复用模式。
                </p>
              )}

              {/* Expandable evidence summary */}
              {req.trigger_conversation && (
                <button
                  type="button"
                  onClick={() => toggleExpand(req.id)}
                  className="flex items-center gap-1 text-[11px] font-medium"
                  style={{ color: "var(--accent)" }}
                >
                  {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  {isExpanded ? "收起证据摘要" : "为什么 Hermes 提出这个建议"}
                </button>
              )}
              {isExpanded && req.trigger_conversation && (
                <pre
                  className="rounded-lg p-2 text-[11px] overflow-auto max-h-40 whitespace-pre-wrap"
                  style={{ background: "var(--surface-3)", color: "var(--text-secondary)" }}
                >
                  {req.trigger_conversation}
                </pre>
              )}

              {/* Duplicate events / extra reference section */}
              {hasDuplicate && (() => {
                const events = dupEvents.get(req.id) ?? [];
                const sectionOpen = dupSectionOpen.has(req.id);
                const selSet = selectedEvts.get(req.id) ?? new Set<string>();
                const extra = otherExtra.get(req.id) ?? "";
                const isGenerating = generating.has(req.id);
                const canGenerate = selSet.size > 0 || extra.trim().length > 0;
                const toggleSection = () => {
                  setDupSectionOpen((prev) => {
                    const n = new Set(prev);
                    if (n.has(req.id)) n.delete(req.id); else n.add(req.id);
                    return n;
                  });
                  if (!dupEventsLoaded.has(req.id)) void loadDupEvents(req.id);
                };
                const toggleEvt = (evId: string) => {
                  setSelectedEvts((prev) => {
                    const m = new Map(prev);
                    const s = new Set(m.get(req.id) ?? []);
                    if (s.has(evId)) s.delete(evId); else if (s.size < 3) s.add(evId);
                    m.set(req.id, s);
                    return m;
                  });
                };
                return (
                  <div className="mt-1">
                    <button
                      type="button"
                      onClick={toggleSection}
                      className="inline-flex items-center gap-1 text-[11px] font-medium rounded px-1.5 py-0.5"
                      style={{ color: "rgb(250,204,21)" }}
                    >
                      {sectionOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      相似萃取 / 额外参考 ({events.length || req.duplicate_count} 条)
                    </button>
                    {sectionOpen && (
                      <div className="rounded-lg p-2.5 mt-1 space-y-1.5" style={{ background: "var(--surface-3)" }}>
                        <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                          已有 {events.length || req.duplicate_count} 次相似萃取。选择最多 3 条作为生成增强版候选的额外参考。
                        </p>
                        {events.map((ev) => (
                          <label key={ev.id} className="flex items-start gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              className="mt-0.5 rounded"
                              checked={selSet.has(ev.id)}
                              disabled={!selSet.has(ev.id) && selSet.size >= 3}
                              onChange={() => toggleEvt(ev.id)}
                            />
                            <div className="flex-1 min-w-0">
                              <p className="text-[11px] truncate" style={{ color: "var(--text-primary)" }}>
                                {ev.candidate_reason ?? "(无原因)"}
                              </p>
                              <div className="flex items-center gap-2 text-[10px]" style={{ color: "var(--text-muted)" }}>
                                {ev.judge_confidence != null && <span>置信度: {(ev.judge_confidence * 100).toFixed(0)}%</span>}
                                <span>{new Date(ev.created_at).toLocaleDateString()}</span>
                              </div>
                              {ev.judge_reason_zh && (
                                <p className="text-[10px] mt-0.5" style={{ color: "var(--text-secondary)" }}>
                                  {ev.judge_reason_zh}
                                </p>
                              )}
                            </div>
                          </label>
                        ))}
                        {events.length === 0 && dupEventsLoaded.has(req.id) && (
                          <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>暂无详细记录。</p>
                        )}
                        <textarea
                          value={extra}
                          onChange={(e) => {
                            const v = e.target.value.slice(0, 1000);
                            setOtherExtra((prev) => new Map(prev).set(req.id, v));
                          }}
                          placeholder="其他补充信息（最多 1000 字）"
                          rows={2}
                          className="w-full rounded p-1.5 text-[11px] resize-none mt-1 border-0"
                          style={{ background: "var(--surface-2)", color: "var(--text-primary)" }}
                        />
                        <button
                          type="button"
                          disabled={isGenerating || !canGenerate}
                          onClick={() => void generateEnhanced(req.id)}
                          className="mt-1 rounded-lg px-3 py-1.5 text-[11px] font-medium text-white disabled:opacity-50 inline-flex items-center gap-1"
                          style={{ background: "rgba(59,130,246,0.8)" }}
                        >
                          {isGenerating ? <><Loader2 size={12} className="animate-spin" /> 生成中...</> : "生成增强版候选"}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Actions */}
              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setDetailModal(req)}
                  className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium"
                  style={{ background: "var(--surface-3)", color: "var(--text-secondary)" }}
                >
                  <Eye size={12} /> 查看内容
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void approve(req.id)}
                  className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-white disabled:opacity-50"
                  style={{ background: "rgba(16,185,129,0.8)" }}
                >
                  <CheckCircle2 size={12} /> 批准
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => openRejectModal(req.id)}
                  className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium disabled:opacity-50"
                  style={{ background: "rgba(239,68,68,0.15)", color: "rgb(248,113,113)" }}
                >
                  <XCircle size={12} /> 拒绝
                </button>
              </div>
            </section>
          );
        })}

        {/* Non-pending (approved, rejected, expired) */}
        {others.length > 0 && (
          <>
            <div className="flex items-center gap-2 pt-2">
              <div className="h-px flex-1" style={{ background: "var(--border-subtle)" }} />
              <span className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>已处理 / 已过期</span>
              <div className="h-px flex-1" style={{ background: "var(--border-subtle)" }} />
            </div>
            {others.map((req) => (
              <div
                key={req.id}
                className="flex items-center gap-2 rounded-lg px-3 py-2 opacity-50"
                style={{ background: "var(--surface-2)" }}
              >
                <ActionBadge action={req.action} />
                <span className="text-xs" style={{ color: "var(--text-secondary)" }}>{req.skill_name}</span>
                <span className="text-[11px] ml-auto" style={{ color: "var(--text-tertiary)" }}>
                  {req.status === "expired" ? (
                    <span className="inline-flex items-center gap-1"><Clock size={10} /> 已过期</span>
                  ) : (
                    formatDate(req.reviewed_at ?? req.created_at)
                  )}
                </span>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Detail modal */}
      {detailModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.5)" }}
          onClick={() => setDetailModal(null)}
        >
          <div
            className="relative max-h-[80vh] w-full max-w-2xl overflow-auto rounded-2xl p-6"
            style={{ background: "var(--surface-1)", border: "1px solid var(--border-subtle)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 mb-4">
              <ActionBadge action={detailModal.action} />
              <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                {detailModal.skill_name}
              </span>
              <button
                type="button"
                onClick={() => setDetailModal(null)}
                className="ml-auto text-xs"
                style={{ color: "var(--text-tertiary)" }}
              >
                关闭
              </button>
            </div>

            <div className="mb-3">
              <span className="text-[11px] font-medium" style={{ color: "var(--text-tertiary)" }}>原因</span>
              <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>{detailModal.reason}</p>
            </div>

            {/* Evidence summary in detail modal */}
            {detailModal.trigger_conversation && (
              <div className="mb-3">
                <span className="text-[11px] font-medium" style={{ color: "var(--text-tertiary)" }}>
                  为什么 Hermes 提出这个建议
                </span>
                <pre
                  className="mt-1 rounded-lg p-3 text-xs overflow-auto max-h-40 whitespace-pre-wrap"
                  style={{ background: "var(--surface-3)", color: "var(--text-secondary)" }}
                >
                  {detailModal.trigger_conversation}
                </pre>
              </div>
            )}

            {/* Related existing skill warning */}
            {detailModal.related_existing_skill_ids && (() => {
              let existingNames: string[] = [];
              try { existingNames = JSON.parse(detailModal.related_existing_skill_ids); } catch { /* ignore */ }
              if (existingNames.length > 0) {
                return (
                  <div className="mb-3 rounded-lg p-3" style={{ background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.3)" }}>
                    <div className="flex items-start gap-2">
                      <AlertTriangle size={14} className="mt-0.5 shrink-0" style={{ color: "rgb(250,204,21)" }} />
                      <div>
                        <span className="text-xs font-medium" style={{ color: "rgb(250,204,21)" }}>
                          可能相关已有技能：{existingNames.join("、")}
                        </span>
                        {detailModal.related_existing_skill_note && (
                          <p className="text-[11px] mt-1" style={{ color: "var(--text-secondary)" }}>
                            {detailModal.related_existing_skill_note}请审核是否真的需要新技能。
                          </p>
                        )}
                        {!detailModal.related_existing_skill_note && (
                          <p className="text-[11px] mt-1" style={{ color: "var(--text-secondary)" }}>
                            Hermes 判断它相关但不完全覆盖，请审核是否真的需要新技能。
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              }
              return null;
            })()}

            {detailModal.action === "patch" ? (
              <div className="flex flex-col gap-2">
                <div>
                  <span className="text-[11px] font-medium" style={{ color: "var(--text-tertiary)" }}>替换前</span>
                  <pre className="mt-1 rounded-lg p-3 text-xs overflow-auto max-h-40 whitespace-pre-wrap" style={{ background: "rgba(239,68,68,0.08)", color: "rgb(248,113,113)" }}>
                    {detailModal.old_string || "(空)"}
                  </pre>
                </div>
                <div>
                  <span className="text-[11px] font-medium" style={{ color: "var(--text-tertiary)" }}>替换后</span>
                  <pre className="mt-1 rounded-lg p-3 text-xs overflow-auto max-h-40 whitespace-pre-wrap" style={{ background: "rgba(16,185,129,0.08)", color: "rgb(110,231,183)" }}>
                    {detailModal.new_string || "(空)"}
                  </pre>
                </div>
              </div>
            ) : (
              <div>
                <span className="text-[11px] font-medium" style={{ color: "var(--text-tertiary)" }}>SKILL.md 内容</span>
                <pre className="mt-1 rounded-lg p-3 text-xs overflow-auto max-h-96 whitespace-pre-wrap" style={{ background: "var(--surface-3)", color: "var(--text-secondary)" }}>
                  {detailModal.proposed_content || "(空)"}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Reject reason modal */}
      {rejectModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.5)" }}
          onClick={() => { if (!rejectModal.busy) setRejectModal(null); }}
        >
          <div
            className="relative w-full max-w-sm rounded-2xl p-5"
            style={{ background: "var(--surface-1)", border: "1px solid var(--border-subtle)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
              拒绝原因
            </h3>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {REJECT_QUICK_REASONS.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => { setRejectReason(r.value); setRejectCustom(""); }}
                  className="rounded-md px-2 py-1 text-[11px] font-medium transition-colors"
                  style={{
                    background: rejectReason === r.value ? "rgba(239,68,68,0.2)" : "var(--surface-3)",
                    color: rejectReason === r.value ? "rgb(248,113,113)" : "var(--text-secondary)",
                    border: rejectReason === r.value ? "1px solid rgba(239,68,68,0.4)" : "1px solid transparent",
                  }}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <textarea
              ref={rejectTextareaRef}
              value={rejectCustom}
              onChange={(e) => setRejectCustom(e.target.value)}
              placeholder={rejectReason ? `${rejectReason}: 补充说明（可选）` : "输入拒绝原因..."}
              rows={2}
              className="w-full rounded-lg p-2 text-xs resize-none"
              style={{ background: "var(--surface-3)", color: "var(--text-primary)", border: "1px solid var(--border-subtle)" }}
            />
            {/* Blacklist toggle */}
            <label className="flex items-center gap-2 mt-3 cursor-pointer">
              <input
                type="checkbox"
                checked={rejectBlacklist}
                onChange={(e) => setRejectBlacklist(e.target.checked)}
                className="rounded"
              />
              <span className="text-[11px] font-medium" style={{ color: "rgb(248,113,113)" }}>
                加入黑名单，下次不再生成类似建议
              </span>
            </label>
            <div className="flex items-center justify-end gap-2 mt-3">
              <button
                type="button"
                disabled={rejectModal.busy}
                onClick={() => setRejectModal(null)}
                className="rounded-lg px-3 py-1.5 text-[11px] font-medium disabled:opacity-50"
                style={{ background: "var(--surface-3)", color: "var(--text-secondary)" }}
              >
                取消
              </button>
              <button
                type="button"
                disabled={rejectModal.busy}
                onClick={confirmReject}
                className="rounded-lg px-3 py-1.5 text-[11px] font-medium text-white disabled:opacity-50"
                style={{ background: rejectBlacklist ? "rgba(239,68,68,0.9)" : "rgba(239,68,68,0.8)" }}
              >
                {rejectBlacklist ? "拒绝并加入黑名单" : "确认拒绝"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
