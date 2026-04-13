const COMPLETED_REPLAY_MODULES = new Set(["modeling_simulation_workbench"]);

export function shouldSuppressAutoGuide(moduleId, status) {
  if (status === "running") return true;
  if (status === "completed") {
    return !COMPLETED_REPLAY_MODULES.has(String(moduleId || "").trim());
  }
  return false;
}
