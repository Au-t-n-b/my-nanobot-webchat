/**
 * 外部嵌入页通过 `/sdk/claw-bridge.js` 注入的全局对象（仅类型提示）。
 */
export {};

declare global {
  interface Window {
    claw?: {
      configure(opts: { embedId?: string }): void;
      onUpdate(callback: (payload: unknown) => void): () => void;
      emit(eventName: string, payload?: unknown): void;
    };
  }
}
