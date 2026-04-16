/**
 * Local demo auth: accounts live in localStorage only (no server verification).
 * Suitable for gating the SPA; not a security boundary.
 */
const ACCOUNTS_KEY = "nanobot_local_accounts_v1";
const SESSION_KEY = "nanobot_session_v1";

type StoredAccount = { username: string; password: string };

function readAccounts(): StoredAccount[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(ACCOUNTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((x) => ({
        username: typeof (x as StoredAccount).username === "string" ? (x as StoredAccount).username.trim() : "",
        password: typeof (x as StoredAccount).password === "string" ? (x as StoredAccount).password : "",
      }))
      .filter((x) => x.username.length > 0);
  } catch {
    return [];
  }
}

function writeAccounts(accounts: StoredAccount[]) {
  window.localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts));
}

export function getCurrentLocalUser(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const u = window.localStorage.getItem(SESSION_KEY);
    return u && u.trim() ? u.trim() : null;
  } catch {
    return null;
  }
}

export function isLoggedIn(): boolean {
  return getCurrentLocalUser() !== null;
}

export function logoutLocal(): void {
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function loginLocalUser(username: string, password: string): { ok: true } | { ok: false; error: string } {
  const u = username.trim();
  if (!u) return { ok: false, error: "请输入用户名。" };
  if (!password) return { ok: false, error: "请输入密码。" };
  const accounts = readAccounts();
  const found = accounts.find((a) => a.username === u);
  if (!found || found.password !== password) {
    return { ok: false, error: "用户名或密码不正确。" };
  }
  try {
    window.localStorage.setItem(SESSION_KEY, u);
  } catch {
    return { ok: false, error: "无法写入登录状态。" };
  }
  return { ok: true };
}

export function registerLocalUser(
  username: string,
  password: string,
  password2: string,
): { ok: true } | { ok: false; error: string } {
  const u = username.trim();
  if (!u) return { ok: false, error: "请输入用户名。" };
  if (!password) return { ok: false, error: "请输入密码。" };
  if (password !== password2) return { ok: false, error: "两次输入的密码不一致。" };
  if (password.length < 4) return { ok: false, error: "密码至少 4 位（演示环境）。" };
  const accounts = readAccounts();
  if (accounts.some((a) => a.username === u)) {
    return { ok: false, error: "该用户名已被注册。" };
  }
  accounts.push({ username: u, password });
  try {
    writeAccounts(accounts);
    window.localStorage.setItem(SESSION_KEY, u);
  } catch {
    return { ok: false, error: "无法保存账号。" };
  }
  return { ok: true };
}
