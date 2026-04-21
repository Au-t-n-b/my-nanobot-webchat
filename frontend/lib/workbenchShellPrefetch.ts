/**
 * 工作台壳层分包预加载与路由预热（登录页、落地页调用；与业务逻辑解耦）。
 */

export function scheduleIdlePrefetch(run: () => void): void {
  if (typeof requestIdleCallback !== "undefined") {
    requestIdleCallback(() => run(), { timeout: 1800 });
  } else {
    setTimeout(run, 0);
  }
}

type PrefetchRouter = {
  prefetch: (href: string) => void | Promise<void>;
};

/** 动态加载工作台页面模块 + 预热 /workbench 路由 */
export function prefetchWorkbenchShell(router: PrefetchRouter): void {
  router.prefetch("/workbench");
  void import("@/app/workbench/WorkbenchContent");
}

export function schedulePrefetchWorkbenchShell(router: PrefetchRouter): void {
  scheduleIdlePrefetch(() => prefetchWorkbenchShell(router));
}
