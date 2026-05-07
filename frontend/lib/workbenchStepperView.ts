import { getLocalStorage, safeSetItem } from "@/lib/browserStorage";

/** localStorage 键，与 /api 无关，纯前端布局偏好 */
export const WORKBENCH_STEPPER_VIEW_STORAGE_KEY = "nanobot_workbench_stepper_view_v1" as const;

export type WorkbenchStepperView = "compact" | "docked";

export const DEFAULT_WORKBENCH_STEPPER_VIEW: WorkbenchStepperView = "compact";

function normalize(raw: string | null): WorkbenchStepperView {
  if (raw === "docked") return "docked";
  return "compact";
}

export function readWorkbenchStepperView(): WorkbenchStepperView {
  const ls = getLocalStorage();
  if (!ls) return DEFAULT_WORKBENCH_STEPPER_VIEW;
  try {
    return normalize(ls.getItem(WORKBENCH_STEPPER_VIEW_STORAGE_KEY));
  } catch {
    return DEFAULT_WORKBENCH_STEPPER_VIEW;
  }
}

export const WORKBENCH_STEPPER_VIEW_EVENT = "nanobot:workbench-stepper-view" as const;

/** 持久化并广播，供同页多组件与多标签（storage）同步 */
export function writeWorkbenchStepperView(v: WorkbenchStepperView): void {
  const ls = getLocalStorage();
  if (!ls) return;
  if (!safeSetItem(ls, WORKBENCH_STEPPER_VIEW_STORAGE_KEY, v)) return;
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent(WORKBENCH_STEPPER_VIEW_EVENT, { detail: v }),
    );
  }
}
