import { sanitizeStorageSegment } from "@/lib/workbenchStorageKeys";

export type OfflineOutboxItem = { text: string; model: string; at: number };

const k = (scope: string) => `offline_outbox::${sanitizeStorageSegment(scope)}`;

const IDB = "nanobot-offline";
const V = 1;
const OS = "pending";
type Row = { k: string; scope: string; text: string; model: string; at: number };

let dbP: Promise<IDBDatabase> | null = null;

function idb() {
  if (typeof indexedDB === "undefined") return null;
  if (!dbP) {
    dbP = new Promise((resolve, reject) => {
      const r = indexedDB.open(IDB, V);
      r.onupgradeneeded = () => {
        const d = r.result;
        if (!d.objectStoreNames.contains(OS)) {
          const s = d.createObjectStore(OS, { keyPath: "k" });
          s.createIndex("byScope", "scope", { unique: false });
        }
      };
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
  }
  return dbP;
}

const sKey = (scope: string) => `s::${sanitizeStorageSegment(scope)}`;

export function enqueueOfflineUserSend(scope: string, item: OfflineOutboxItem) {
  if (typeof window === "undefined") return;
  const db0 = idb();
  if (!db0) {
    const prev = _read(scope);
    _write(scope, [...prev, item].slice(-20));
    return;
  }
  void (async () => {
    const d = await db0;
    const s = sKey(scope);
    const id = item.at + "-" + Math.random().toString(36).slice(2, 8);
    await new Promise<void>((res, rej) => {
      const t = d.transaction(OS, "readwrite");
      t.oncomplete = () => {
        if (typeof localStorage !== "undefined") localStorage.removeItem(k(scope));
        res();
      };
      t.onerror = () => rej(t.error);
      t.objectStore(OS).put({ k: s + id, scope: s, text: item.text, model: item.model, at: item.at } satisfies Row);
    });
  })();
}

function _read(scope: string): OfflineOutboxItem[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const r = localStorage.getItem(k(scope));
    if (!r) return [];
    const a = JSON.parse(r) as unknown;
    if (!Array.isArray(a)) return [];
    return a
      .filter((x) => x && typeof x === "object")
      .map((e) => ({
        text: String((e as { text?: string }).text ?? ""),
        model: String((e as { model?: string }).model ?? ""),
        at: Number((e as { at?: number }).at) || 0,
      }));
  } catch {
    return [];
  }
}

function _write(scope: string, items: OfflineOutboxItem[]) {
  if (typeof localStorage === "undefined") return;
  try {
    if (items.length === 0) localStorage.removeItem(k(scope));
    else localStorage.setItem(k(scope), JSON.stringify(items));
  } catch {
    /* */
  }
}

export async function readOfflineOutbox(scope: string): Promise<OfflineOutboxItem[]> {
  if (typeof window === "undefined") return [];
  const d0 = idb();
  if (!d0) {
    return _read(scope);
  }
  const d = await d0;
  const s = sKey(scope);
  return new Promise((resolve, reject) => {
    const t = d.transaction(OS, "readonly");
    const st = t.objectStore(OS).index("byScope");
    const cur = st.openCursor(IDBKeyRange.only(s));
    const r: OfflineOutboxItem[] = [];
    cur.onsuccess = (e) => {
      const c = (e.target as IDBRequest).result as IDBCursorWithValue | null;
      if (!c) {
        r.sort((a, b) => a.at - b.at);
        resolve(r.length > 0 ? r : _read(scope));
        return;
      }
      const v = c.value as Row;
      r.push({ text: v.text, model: v.model, at: v.at });
      c.continue();
    };
    cur.onerror = () => reject(cur.error);
  });
}

export async function clearOfflineOutboxForScope(scope: string) {
  _write(scope, []);
  const d0 = idb();
  if (!d0) return;
  const d = await d0;
  const s = sKey(scope);
  return new Promise<void>((resolve, reject) => {
    const t = d.transaction(OS, "readwrite");
    const st = t.objectStore(OS);
    const q = t.objectStore(OS).index("byScope").openCursor(IDBKeyRange.only(s));
    q.onsuccess = (e) => {
      const c = (e.target as IDBRequest).result as IDBCursorWithValue | null;
      if (!c) {
        return;
      }
      st.delete((c.value as Row).k);
      c.continue();
    };
    t.oncomplete = () => resolve();
    q.onerror = () => reject(q.error);
    t.onerror = () => reject(t.error);
  });
}
