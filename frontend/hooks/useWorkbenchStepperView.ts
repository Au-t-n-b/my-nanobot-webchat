"use client";

import { useCallback, useLayoutEffect, useState } from "react";
import {
  readWorkbenchStepperView,
  writeWorkbenchStepperView,
  WORKBENCH_STEPPER_VIEW_EVENT,
  WORKBENCH_STEPPER_VIEW_STORAGE_KEY,
  type WorkbenchStepperView,
} from "@/lib/workbenchStepperView";

/**
 * 工作台主区「流程进度」展示：紧凑胶囊 / 顶栏全宽。持久化在 localStorage。
 * 多实例（如侧栏 + 控制中心的设置项）通过 CustomEvent + storage 与 Workbench 同步。
 */
export function useWorkbenchStepperView() {
  const [view, setView] = useState<WorkbenchStepperView>(() => readWorkbenchStepperView());

  const pullFromStorage = useCallback(() => {
    setView(readWorkbenchStepperView());
  }, []);

  useLayoutEffect(() => {
    setView(readWorkbenchStepperView());
  }, []);

  useLayoutEffect(() => {
    const onCustom = () => pullFromStorage();
    const onStorage = (e: StorageEvent) => {
      if (e.key === WORKBENCH_STEPPER_VIEW_STORAGE_KEY) pullFromStorage();
    };
    window.addEventListener(WORKBENCH_STEPPER_VIEW_EVENT, onCustom);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(WORKBENCH_STEPPER_VIEW_EVENT, onCustom);
      window.removeEventListener("storage", onStorage);
    };
  }, [pullFromStorage]);

  const setViewPersist = useCallback((v: WorkbenchStepperView) => {
    writeWorkbenchStepperView(v);
    setView(v);
  }, []);

  return { view, setView: setViewPersist };
}
