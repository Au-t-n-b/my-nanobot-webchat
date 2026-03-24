"use client";

import { useState } from "react";
import { ChatArea } from "@/components/ChatArea";
import { ChoicesModal } from "@/components/ChoicesModal";
import { PreviewPanel } from "@/components/PreviewPanel";
import { Sidebar } from "@/components/Sidebar";
import { useAgentChat } from "@/hooks/useAgentChat";

export default function Home() {
  const {
    threadId,
    messages,
    stepLogs,
    isLoading,
    error,
    pendingTool,
    pendingChoices,
    sendMessage,
    approveTool,
    clearPendingChoices,
    clearChat,
  } = useAgentChat();
  const [input, setInput] = useState("");
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [previewPath, setPreviewPath] = useState<string | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765";

  const openFilePreview = (path: string) => {
    setPreviewPath(path);
    setIsPreviewOpen(true);
  };

  return (
    <main className="h-screen bg-zinc-950 text-zinc-100 p-4">
      <ChoicesModal
        choices={pendingChoices}
        onSelect={(choice) => {
          clearPendingChoices();
          void sendMessage(choice.value);
        }}
        onClose={clearPendingChoices}
      />
      <div className="h-full grid grid-cols-12 gap-4">
        <div className="col-span-12 md:col-span-3">
          <Sidebar
            threadId={threadId}
            apiBase={apiBase}
            onClear={clearChat}
            onPreviewPath={openFilePreview}
            messages={messages}
          />
        </div>

        <div className={isPreviewOpen ? "col-span-12 md:col-span-6" : "col-span-12 md:col-span-9"}>
          <ChatArea
            messages={messages}
            stepLogs={stepLogs}
            isLoading={isLoading}
            error={error}
            pendingTool={pendingTool}
            pendingChoices={pendingChoices}
            input={input}
            setInput={setInput}
            onSend={() => {
              const v = input;
              setInput("");
              void sendMessage(v);
            }}
            onApproveTool={(approved) => {
              void approveTool(approved);
            }}
            onFileLinkClick={openFilePreview}
            previewPanelOpen={isPreviewOpen}
            onOpenPreviewPanel={() => setIsPreviewOpen(true)}
            disabled={isLoading || !threadId}
          />
        </div>

        {isPreviewOpen && (
          <div className="col-span-12 md:col-span-3">
            <PreviewPanel
              onClose={() => setIsPreviewOpen(false)}
              filePath={previewPath}
              onClearFile={() => setPreviewPath(null)}
              onOpenPath={openFilePreview}
            />
          </div>
        )}
      </div>
    </main>
  );
}
