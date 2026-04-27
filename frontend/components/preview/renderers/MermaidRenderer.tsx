"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { BaseRendererProps } from "../previewTypes";

type TooltipState = {
  visible: boolean;
  x: number;
  y: number;
  label: string;
  detail: string;
};

function GanttView({ svg, source }: { svg: string; source: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false, x: 0, y: 0, label: "", detail: "",
  });
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [copied, setCopied] = useState(false);

  const copySource = () => {
    void navigator.clipboard.writeText(source).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const taskEls = container.querySelectorAll<SVGElement>(
      "rect[class*='task'], .task"
    );

    let debounce: ReturnType<typeof setTimeout> | null = null;

    const onEnter = (e: Event) => {
      const ev = e as MouseEvent;
      const el = ev.target as SVGElement;

      if (debounce) clearTimeout(debounce);
      debounce = setTimeout(() => {
        let label = "";
        let detail = "";

        const title = el.querySelector("title");
        if (title) label = title.textContent ?? "";

        if (!label) {
          const parentG = el.closest("g");
          if (parentG) {
            const texts = parentG.querySelectorAll("text");
            texts.forEach((t) => {
              const txt = t.textContent?.trim() ?? "";
              if (txt && !label) label = txt;
              else if (txt && txt !== label) detail = txt;
            });
          }
        }

        if (!label) {
          const cls = el.getAttribute("class") ?? "";
          const match = cls.match(/task\d+/);
          if (match) label = match[0];
        }

        if (!label) label = "任务";

        setTooltip({ visible: true, x: ev.clientX, y: ev.clientY, label, detail });
      }, 80);
    };

    const onLeave = () => {
      if (debounce) clearTimeout(debounce);
      if (hideTimer.current) clearTimeout(hideTimer.current);
      hideTimer.current = setTimeout(() => setTooltip((t) => ({ ...t, visible: false })), 100);
    };

    const onMove = (e: Event) => {
      const ev = e as MouseEvent;
      setTooltip((t) => (t.visible ? { ...t, x: ev.clientX, y: ev.clientY } : t));
    };

    taskEls.forEach((el) => {
      el.addEventListener("mouseenter", onEnter);
      el.addEventListener("mouseleave", onLeave);
      el.addEventListener("mousemove", onMove);
    });

    return () => {
      if (debounce) clearTimeout(debounce);
      taskEls.forEach((el) => {
        el.removeEventListener("mouseenter", onEnter);
        el.removeEventListener("mouseleave", onLeave);
        el.removeEventListener("mousemove", onMove);
      });
    };
  }, [svg]);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-end mb-1">
        <button
          type="button"
          onClick={copySource}
          aria-label="复制源码"
          className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] px-2 py-0.5 text-[11px] ui-text-secondary hover:bg-[var(--surface-3)] transition-colors"
        >
          {copied ? <Check size={10} /> : <Copy size={10} />}
          {copied ? "已复制" : "复制源码"}
        </button>
      </div>

      <div
        ref={containerRef}
        className="overflow-auto p-2 [&_svg]:max-w-full [&_svg]:h-auto [&_.task]:cursor-pointer [&_.task]:transition-opacity [&_.task:hover]:opacity-80"
        dangerouslySetInnerHTML={{ __html: svg }}
      />

      {tooltip.visible && (
        <div
          className="fixed z-50 pointer-events-none"
          style={{ left: tooltip.x + 14, top: tooltip.y - 10 }}
        >
          <div className="rounded-lg border border-white/10 bg-[var(--surface-elevated)]/90 backdrop-blur-md p-3 shadow-[var(--shadow-float)] text-xs text-[var(--text-primary)] max-w-[200px]">
            <p className="font-semibold leading-snug">{tooltip.label}</p>
            {tooltip.detail && (
              <p className="mt-1 ui-text-secondary leading-snug">{tooltip.detail}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function MermaidRenderer(props: BaseRendererProps & { svg: string; source: string }) {
  return <GanttView svg={props.svg} source={props.source} />;
}

