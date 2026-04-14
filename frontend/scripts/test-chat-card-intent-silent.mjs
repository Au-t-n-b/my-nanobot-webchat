import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pagePath = path.join(__dirname, "../app/page.tsx");
const pageSource = fs.readFileSync(pagePath, "utf8");

test("page routes chat-card and dashboard intents through sendSilentMessage", () => {
  assert.match(
    pageSource,
    /chatCardPostToAgent=\{\(text\) => void sendSilentMessage\(text, selectedModel\)\}/,
  );
  assert.match(
    pageSource,
    /postToAgent=\{\(text\) => void sendSilentMessage\(text, selectedModel\)\}\s*postToAgentSilently=\{\(text\) => void sendSilentMessage\(text, selectedModel\)\}/,
  );
  assert.match(
    pageSource,
    /<PreviewPanel[\s\S]*?postToAgent=\{\(text\) => void sendSilentMessage\(text, selectedModel\)\}/,
  );
});
