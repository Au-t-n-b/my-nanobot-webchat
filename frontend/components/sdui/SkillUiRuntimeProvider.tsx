"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { expandInputPlaceholders } from "@/lib/sdui";

export type SkillUiRuntimeContextValue = {
  /** 已展开 {{input:id}} 后发给 Agent */
  postToAgent: (text: string) => void;
  getInputValue: (id: string) => string;
  setInputValue: (id: string, value: string) => void;
  openPreview: (path: string) => void;
};

const SkillUiRuntimeContext = createContext<SkillUiRuntimeContextValue | null>(null);

type Props = {
  children: ReactNode;
  /** 原始发送（通常封装自 sendMessage） */
  postToAgentRaw: (text: string) => void;
  /** 打开预览路径（文件或 synthetic path） */
  onOpenPreview?: (path: string) => void;
};

export function SkillUiRuntimeProvider({ children, postToAgentRaw, onOpenPreview }: Props) {
  const inputsRef = useRef<Record<string, string>>({});
  const [, force] = useState(0);

  const getInputValue = useCallback((id: string) => inputsRef.current[id] ?? "", []);

  const setInputValue = useCallback((id: string, value: string) => {
    inputsRef.current[id] = value;
    force((x) => x + 1);
  }, []);

  const postToAgent = useCallback(
    (text: string) => {
      const expanded = expandInputPlaceholders(text, getInputValue);
      postToAgentRaw(expanded);
    },
    [postToAgentRaw, getInputValue],
  );

  const openPreview = useCallback(
    (path: string) => {
      const p = path.trim();
      if (!p) return;
      onOpenPreview?.(p);
    },
    [onOpenPreview],
  );

  const value = useMemo<SkillUiRuntimeContextValue>(
    () => ({
      postToAgent,
      getInputValue,
      setInputValue,
      openPreview,
    }),
    [postToAgent, getInputValue, setInputValue, openPreview],
  );

  return <SkillUiRuntimeContext.Provider value={value}>{children}</SkillUiRuntimeContext.Provider>;
}

export function useSkillUiRuntime(): SkillUiRuntimeContextValue {
  const ctx = useContext(SkillUiRuntimeContext);
  if (!ctx) {
    throw new Error("useSkillUiRuntime must be used within SkillUiRuntimeProvider");
  }
  return ctx;
}
