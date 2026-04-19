import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const hookPath = path.join(__dirname, "../hooks/useAgentChat.ts");
const hookSource = fs.readFileSync(hookPath, "utf8");

test("silent card intents do not append RunFinished.message to transcript", () => {
  assert.match(
    hookSource,
    /options\?: \{ showInTranscript\?: boolean,\s*showCompletionMessage\?: boolean \}/,
  );
  assert.match(
    hookSource,
    /const showCompletionMessage = options\?\.showCompletionMessage === true;/,
  );
  assert.match(
    hookSource,
    /const allowSilentCompletionMessage = !showCompletionMessage \|\| !\/\^已进入下一步\[:：\]\/\.test\(finishMsg\);/,
  );
  assert.match(
    hookSource,
    /if \(showInTranscript && finishMsg && allowSilentCompletionMessage\)/,
  );
  assert.match(
    hookSource,
    /showInTranscript && finishMsg && allowSilentCompletionMessage[\s\S]*?prev\.map\(\(m\) =>/,
  );
  assert.match(
    hookSource,
    /await sendChatRequest\(text, modelName, \{ showInTranscript: false,\s*showCompletionMessage: true \}\);/,
  );
});
