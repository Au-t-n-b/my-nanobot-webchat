"use strict";

/**
 * Build a child-process `env` for Next.js / Node tooling:
 * - Strip broken `--localstorage-file` flags from NODE_OPTIONS-like vars.
 * - On Node >= 25, append `--no-experimental-webstorage` to NODE_OPTIONS
 *   so the default experimental Web Storage does not expose a bad global.
 */

const ENV_KEYS_SANITIZE = [
  "NODE_OPTIONS",
  "npm_config_node_options",
  "NPM_CONFIG_NODE_OPTIONS",
];

/** Split a NODE_OPTIONS-style string into tokens (double-quoted segments supported). */
function parseQuotedArgv(s) {
  const result = [];
  let i = 0;
  const len = s.length;
  while (i < len) {
    while (i < len && /\s/.test(s[i])) i++;
    if (i >= len) break;
    if (s[i] === '"') {
      i++;
      let buf = "";
      while (i < len && s[i] !== '"') {
        if (s[i] === "\\" && i + 1 < len) buf += s[++i];
        else buf += s[i];
        i++;
      }
      if (i < len) i++;
      result.push(buf);
      continue;
    }
    const start = i;
    while (i < len && !/\s/.test(s[i])) i++;
    result.push(s.slice(start, i));
  }
  return result;
}

function stripLocalstorageTokens(tokens) {
  const out = [];
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === "--localstorage-file") {
      const next = tokens[i + 1];
      if (next !== undefined && !next.startsWith("-")) i++;
      continue;
    }
    if (t.startsWith("--localstorage-file=")) continue;
    out.push(t);
  }
  return out;
}

function joinArgv(tokens) {
  return tokens
    .map((t) => {
      if (/[\s"]/.test(t)) return `"${String(t).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
      return t;
    })
    .join(" ");
}

function sanitizeOptString(s) {
  if (s == null || typeof s !== "string") return "";
  const trimmed = s.trim();
  if (!trimmed) return "";
  const tokens = stripLocalstorageTokens(parseQuotedArgv(trimmed));
  return joinArgv(tokens);
}

function nodeMajor() {
  const m = /^v?(\d+)/.exec(process.versions.node);
  return m ? parseInt(m[1], 10) : 0;
}

function envForNextChild() {
  /** @type {NodeJS.ProcessEnv} */
  const env = { ...process.env };

  for (const key of ENV_KEYS_SANITIZE) {
    if (env[key] !== undefined && env[key] !== "") {
      env[key] = sanitizeOptString(env[key]);
    }
  }

  if (nodeMajor() >= 25) {
    const flag = "--no-experimental-webstorage";
    const cur = (env.NODE_OPTIONS || "").trim();
    const tokens = cur ? parseQuotedArgv(cur) : [];
    if (!tokens.includes(flag)) {
      env.NODE_OPTIONS = cur ? `${cur} ${flag}` : flag;
    }
  }

  return env;
}

module.exports = { envForNextChild };
