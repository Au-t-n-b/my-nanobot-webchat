"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Filter, Plus, Save, Users, X } from "lucide-react";
import { authFetch } from "@/lib/authFetch";
import { useAuthState } from "@/lib/authStore";
import { CenteredModal } from "@/components/CenteredModal";

const STAGES = ["作业管理", "智慧工勘", "建模仿真", "系统设计", "设备安装", "软件部署与调测"] as const;
type Stage = (typeof STAGES)[number];
type CreateMode = "member" | "pd";

type ProjectRow = { projectId: string; name: string; ownerUserId?: string; status?: string };

type MemberRow = {
  userId: string;
  workId: string;
  realName: string;
  roleCode: string;
  status: number;
  lastLoginAt: string | null;
  stages: Stage[];
  projectId?: string | null;
};

function StagePill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "rounded-full border px-3 py-1 text-xs font-medium transition " +
        (active
          ? "border-[color-mix(in_oklab,var(--accent)_45%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--accent)_14%,var(--surface-1))] ui-text-primary"
          : "border-[var(--border-subtle)] bg-[var(--surface-1)] ui-text-secondary hover:bg-[var(--surface-3)] hover:ui-text-primary")
      }
    >
      {label}
    </button>
  );
}

export function AdminMembersPanel({ onBack, embedded = false }: { onBack?: () => void; embedded?: boolean }) {
  const { user } = useAuthState();
  const canManage = user?.accountRole === "admin" || user?.accountRole === "pd";
  const role = user?.accountRole ?? "";
  const isAdmin = role === "admin";
  const isPd = role === "pd";

  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string>("");
  const [projectFilter, setProjectFilter] = useState<string>("all");
  const [projectCreateOpen, setProjectCreateOpen] = useState(false);
  const [projectCreateBusy, setProjectCreateBusy] = useState(false);
  const [projectCreateErr, setProjectCreateErr] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");

  const [rows, setRows] = useState<MemberRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [addErr, setAddErr] = useState<string | null>(null);
  const [createMode, setCreateMode] = useState<CreateMode>("member");
  const [workId, setWorkId] = useState("");
  const [realName, setRealName] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [stageSel, setStageSel] = useState<Stage[]>([]);

  const loadProjects = useCallback(async () => {
    if (!canManage) return;
    setProjectsLoading(true);
    setProjectsError(null);
    setLoading(true);
    try {
      const r = await authFetch("/api/projects", { cache: "no-store" });
      const j = (await r.json().catch(() => ({}))) as { projects?: ProjectRow[]; detail?: string };
      if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
      const list = Array.isArray(j.projects) ? j.projects : [];
      setProjects(list);
      if (isPd) {
        // PD defaults to first project
        if (!projectId && list.length > 0) setProjectId(String(list[0]?.projectId ?? ""));
      }
    } catch (e) {
      setProjectsError(e instanceof Error ? e.message : String(e));
    } finally {
      setProjectsLoading(false);
    }
  }, [canManage, isPd, projectId]);

  // keep eslint happy and allow simple UI hooks later
  void projectsLoading;

  const loadMembers = useCallback(async () => {
    if (!canManage) return;
    // PD must have an active project selected.
    const effectiveProjectId = isPd ? projectId : projectFilter === "all" ? "" : projectFilter;
    if (isPd && !effectiveProjectId) return;
    setLoading(true);
    setError(null);
    try {
      const path = effectiveProjectId ? `/api/admin/members?projectId=${encodeURIComponent(effectiveProjectId)}` : "/api/admin/members";
      const r = await authFetch(path, { cache: "no-store" });
      const j = (await r.json().catch(() => ({}))) as { members?: MemberRow[]; detail?: string };
      if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
      setRows(Array.isArray(j.members) ? j.members : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [canManage, isPd, projectFilter, projectId]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    void loadMembers();
  }, [loadMembers]);

  const canCreateMember = isPd || isAdmin;
  const canCreatePd = isAdmin;
  const canCreateProject = isPd || isAdmin;

  const submitCreateProject = useCallback(async () => {
    const name = projectName.trim();
    if (!name) {
      setProjectCreateErr("项目名称为必填项。");
      return;
    }
    setProjectCreateBusy(true);
    setProjectCreateErr(null);
    try {
      const r = await authFetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const j = (await r.json().catch(() => ({}))) as { project?: ProjectRow; detail?: string };
      if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
      setProjectCreateOpen(false);
      setProjectName("");
      await loadProjects();
      // If PD had no selection, pick the new project as current.
      if (isPd && j.project?.projectId) setProjectId(String(j.project.projectId));
      await loadMembers();
    } catch (e) {
      setProjectCreateErr(e instanceof Error ? e.message : String(e));
    } finally {
      setProjectCreateBusy(false);
    }
  }, [isPd, loadMembers, loadProjects, projectName]);

  const resetAdd = useCallback(() => {
    setCreateMode("member");
    setWorkId("");
    setRealName("");
    setPassword("");
    setPassword2("");
    setStageSel([]);
    setAddErr(null);
  }, []);

  const submitAdd = useCallback(async () => {
    const w = workId.trim();
    const rn = realName.trim();
    if (!w || !rn) {
      setAddErr("工号与姓名为必填项。");
      return;
    }
    if (!password || password.length < 8) {
      setAddErr("密码至少 8 位。");
      return;
    }
    if (password !== password2) {
      setAddErr("两次输入的密码不一致。");
      return;
    }
    if (createMode === "member") {
      if (!projectId) {
        setAddErr("缺少 projectId。");
        return;
      }
      if (stageSel.length === 0) {
        setAddErr("请至少选择 1 个阶段。");
        return;
      }
    }
    setAddBusy(true);
    setAddErr(null);
    try {
      const r = await authFetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workId: w,
          realName: rn,
          password,
          passwordConfirm: password2,
          ...(createMode === "pd"
            ? { roleCode: "PD" }
            : {
                projectId,
                stages: stageSel,
              }),
        }),
      });
      const j = (await r.json().catch(() => ({}))) as { detail?: string };
      if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
      setAddOpen(false);
      resetAdd();
      void loadMembers();
    } catch (e) {
      setAddErr(e instanceof Error ? e.message : String(e));
    } finally {
      setAddBusy(false);
    }
  }, [createMode, loadMembers, password, password2, projectId, realName, resetAdd, stageSel, workId]);

  const headerRight = useMemo(() => {
    return (
      <div className="flex items-center gap-2">
        {isAdmin ? (
          <>
            <div className="text-xs ui-text-muted">项目</div>
            <div className="relative">
              <select
                className="h-9 w-44 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 text-xs ui-text-primary outline-none"
                value={projectFilter}
                onChange={(e) => setProjectFilter(e.target.value)}
              >
                <option value="all">全部项目</option>
                {projects.map((p) => (
                  <option key={p.projectId} value={p.projectId}>
                    {p.name}
                  </option>
                ))}
              </select>
              <Filter size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 ui-text-muted" aria-hidden />
            </div>
          </>
        ) : (
          <>
            <div className="text-xs ui-text-muted">我的项目</div>
            <select
              className="h-9 w-44 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 text-xs ui-text-primary outline-none"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            >
              {projects.length === 0 ? <option value="">暂无项目</option> : null}
              {projects.map((p) => (
                <option key={p.projectId} value={p.projectId}>
                  {p.name}
                </option>
              ))}
            </select>
          </>
        )}

        <button
          type="button"
          onClick={() => {
            void loadProjects();
            void loadMembers();
          }}
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-xs ui-text-secondary hover:bg-[var(--surface-3)]"
        >
          刷新
        </button>
        {canCreateProject ? (
          <button
            type="button"
            onClick={() => {
              setProjectCreateErr(null);
              setProjectName("");
              setProjectCreateOpen(true);
            }}
            className="rounded-lg border border-[color-mix(in_oklab,var(--accent)_45%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--accent)_14%,var(--surface-1))] px-3 py-2 text-xs ui-text-primary hover:opacity-90"
          >
            新建项目
          </button>
        ) : null}
        {canCreateMember ? (
          <button
            type="button"
            onClick={() => {
              resetAdd();
              setAddOpen(true);
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-[color-mix(in_oklab,var(--accent)_45%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--accent)_14%,var(--surface-1))] px-3 py-2 text-xs ui-text-primary hover:opacity-90"
          >
            <Plus size={14} aria-hidden />
            新增账号
          </button>
        ) : null}
      </div>
    );
  }, [canCreateMember, canCreateProject, isAdmin, loadMembers, loadProjects, projectFilter, projectId, projects, resetAdd]);

  if (!canManage) {
    return (
      <div className="p-4">
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 text-sm ui-text-secondary">
          你没有成员管理权限（需要 ADMIN 或 PD）。
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {!embedded ? (
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
          <div className="inline-flex items-center gap-2">
            <Users size={18} aria-hidden />
            <h2 className="text-sm font-semibold ui-text-primary">成员管理</h2>
          </div>
          <div className="flex items-center gap-2">
            {onBack ? (
              <button
                type="button"
                onClick={onBack}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-xs ui-text-secondary hover:bg-[var(--surface-3)]"
              >
                返回
              </button>
            ) : null}
            {headerRight}
          </div>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto p-4">
        <CenteredModal
          open={projectCreateOpen}
          onClose={() => {
            if (projectCreateBusy) return;
            setProjectCreateOpen(false);
          }}
          title="新建项目"
          disableDismiss={projectCreateBusy}
          panelClassName="w-full max-w-lg"
          footer={
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="ui-btn-ghost rounded-lg px-3 py-1.5 text-xs font-medium"
                disabled={projectCreateBusy}
                onClick={() => setProjectCreateOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                style={{ background: "var(--accent)" }}
                disabled={projectCreateBusy}
                onClick={() => void submitCreateProject()}
              >
                {projectCreateBusy ? "创建中…" : "创建"}
              </button>
            </div>
          }
        >
          <div className="space-y-3">
            <div>
              <div className="text-xs font-semibold ui-text-primary">项目名称</div>
              <input
                className="mt-2 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm ui-text-primary outline-none"
                placeholder="例如：某某局作业交付"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                disabled={projectCreateBusy}
              />
            </div>
            {projectCreateErr ? <div className="text-xs text-[var(--danger)]">{projectCreateErr}</div> : null}
            {projectsError ? <div className="text-xs text-[var(--danger)]">{projectsError}</div> : null}
          </div>
        </CenteredModal>

        {error ? (
          <div className="mb-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>
        ) : null}
        <div className="overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-0)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-[var(--surface-1)]">
              <tr className="text-left ui-text-muted">
                {isAdmin && projectFilter === "all" ? <th className="px-4 py-3">项目</th> : null}
                <th className="px-4 py-3">工号</th>
                <th className="px-4 py-3">姓名</th>
                <th className="px-4 py-3">角色</th>
                <th className="px-4 py-3">阶段</th>
                <th className="px-4 py-3">最近登录</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={isAdmin && projectFilter === "all" ? 6 : 5} className="px-4 py-6 ui-text-secondary">
                    加载中…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={isAdmin && projectFilter === "all" ? 6 : 5} className="px-4 py-6 ui-text-secondary">
                    暂无成员
                  </td>
                </tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.userId} className="border-t border-[var(--border-subtle)]">
                    {isAdmin && projectFilter === "all" ? (
                      <td className="px-4 py-3 ui-text-secondary">
                        {projects.find((p) => p.projectId === (r.projectId ?? ""))?.name ?? (r.projectId || "—")}
                      </td>
                    ) : null}
                    <td className="px-4 py-3 ui-text-primary">{r.workId}</td>
                    <td className="px-4 py-3 ui-text-primary">{r.realName}</td>
                    <td className="px-4 py-3 ui-text-secondary">{r.roleCode}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        {(r.stages ?? []).map((s) => (
                          <span key={s} className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2.5 py-1 text-xs ui-text-secondary">
                            {s}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 ui-text-secondary">{r.lastLoginAt ? new Date(r.lastLoginAt).toLocaleString() : "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {addOpen ? (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/55 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-lg overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-0)] shadow-2xl">
            <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
              <div className="text-sm font-semibold ui-text-primary">新增账号</div>
              <button type="button" onClick={() => setAddOpen(false)} className="rounded-lg p-2 ui-text-secondary hover:ui-text-primary" aria-label="关闭">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3 p-4">
              {canCreatePd ? (
                <div className="flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-2">
                  <button
                    type="button"
                    className={
                      "flex-1 rounded-lg px-3 py-2 text-sm font-medium " +
                      (createMode === "member" ? "bg-[var(--surface-3)] ui-text-primary" : "ui-text-secondary hover:ui-text-primary")
                    }
                    onClick={() => setCreateMode("member")}
                  >
                    项目成员（EMPLOYEE）
                  </button>
                  <button
                    type="button"
                    className={
                      "flex-1 rounded-lg px-3 py-2 text-sm font-medium " +
                      (createMode === "pd" ? "bg-[var(--surface-3)] ui-text-primary" : "ui-text-secondary hover:ui-text-primary")
                    }
                    onClick={() => setCreateMode("pd")}
                  >
                    二级管理员（PD）
                  </button>
                </div>
              ) : null}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="mb-1 text-xs ui-text-muted">工号</div>
                  <input className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm ui-text-primary outline-none" value={workId} onChange={(e) => setWorkId(e.target.value)} />
                </div>
                <div>
                  <div className="mb-1 text-xs ui-text-muted">姓名</div>
                  <input className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm ui-text-primary outline-none" value={realName} onChange={(e) => setRealName(e.target.value)} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="mb-1 text-xs ui-text-muted">密码</div>
                  <input type="password" className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm ui-text-primary outline-none" value={password} onChange={(e) => setPassword(e.target.value)} />
                </div>
                <div>
                  <div className="mb-1 text-xs ui-text-muted">确认密码</div>
                  <input type="password" className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm ui-text-primary outline-none" value={password2} onChange={(e) => setPassword2(e.target.value)} />
                </div>
              </div>
              {createMode === "member" ? (
                <div>
                  <div className="mb-2 text-xs ui-text-muted">任务阶段（多选）</div>
                  <div className="flex flex-wrap gap-2">
                    {STAGES.map((s) => (
                      <StagePill
                        key={s}
                        label={s}
                        active={stageSel.includes(s)}
                        onClick={() => {
                          setStageSel((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
                        }}
                      />
                    ))}
                  </div>
                </div>
              ) : null}
              {addErr ? <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{addErr}</div> : null}
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setAddOpen(false)} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm ui-text-secondary hover:bg-[var(--surface-3)]">
                  取消
                </button>
                <button
                  type="button"
                  disabled={addBusy}
                  onClick={() => void submitAdd()}
                  className="inline-flex items-center gap-2 rounded-lg border border-[color-mix(in_oklab,var(--accent)_45%,var(--border-subtle))] bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  <Save size={16} aria-hidden />
                  {addBusy ? "创建中…" : "创建"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

