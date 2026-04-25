"use client";

import dynamic from "next/dynamic";
import { useLayoutEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { hasWorkspaceAccess } from "@/lib/globalProjectContext";
import { hydrateAuthFromStorage, isAuthed } from "@/lib/authStore";

function WorkbenchShellLoading() {
  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center bg-[var(--surface-0)]"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div
        className="h-9 w-9 animate-spin rounded-full border-2 border-[var(--border-subtle)] border-t-[var(--accent)]"
        aria-hidden
      />
      <p className="mt-4 text-sm ui-text-secondary">正在加载工作台…</p>
    </div>
  );
}

const WorkbenchContent = dynamic(() => import("./WorkbenchContent"), {
  ssr: false,
  loading: () => <WorkbenchShellLoading />,
});

export default function WorkbenchPage() {
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);

  useLayoutEffect(() => {
    setHydrated(true);
    hydrateAuthFromStorage();
    if (!hasWorkspaceAccess()) {
      router.replace("/");
      return;
    }
    if (!isAuthed()) {
      router.replace("/");
    }
  }, [router]);

  if (!hydrated) {
    return <WorkbenchShellLoading />;
  }

  if (!hasWorkspaceAccess()) {
    return <WorkbenchShellLoading />;
  }

  if (!isAuthed()) {
    return <WorkbenchShellLoading />;
  }

  return <WorkbenchContent />;
}
