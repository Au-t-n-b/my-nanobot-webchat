"use client";

import type { MouseEvent } from "react";
import type { SduiAction } from "@/lib/sdui";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";

type Props = {
  label?: string | null;
  href?: string;
  action?: SduiAction;
};

export function SduiLink({ label, href, action }: Props) {
  const { postToAgent, openPreview } = useSkillUiRuntime();

  if (href) {
    return (
      <a href={href} className="ui-link text-sm underline-offset-2" target="_blank" rel="noreferrer">
        {label ?? ""}
      </a>
    );
  }

  const onClick = (e: MouseEvent) => {
    e.preventDefault();
    if (!action) return;
    if (action.kind === "post_user_message") postToAgent(action.text);
    else if (action.kind === "open_preview") openPreview(action.path);
  };

  return (
    <button type="button" className="ui-link text-sm text-left underline-offset-2 bg-transparent border-0 cursor-pointer p-0" onClick={onClick}>
      {label ?? ""}
    </button>
  );
}
