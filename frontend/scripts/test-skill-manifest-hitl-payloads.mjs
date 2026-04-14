import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const choiceCardPath = path.join(__dirname, "../components/sdui/ChoiceCard.tsx");
const filePickerPath = path.join(__dirname, "../components/sdui/FilePicker.tsx");
const sduiTypesPath = path.join(__dirname, "../lib/sdui.ts");

const choiceCardSource = fs.readFileSync(choiceCardPath, "utf8");
const filePickerSource = fs.readFileSync(filePickerPath, "utf8");
const sduiTypesSource = fs.readFileSync(sduiTypesPath, "utf8");

test("choice card forwards manifest metadata in choice_selected payload", () => {
  assert.match(choiceCardSource, /skillName\?: string;/);
  assert.match(choiceCardSource, /stateNamespace\?: string;/);
  assert.match(choiceCardSource, /stepId\?: string;/);
  assert.match(choiceCardSource, /verb: "choice_selected"/);
  assert.match(choiceCardSource, /skillName: skill/);
  assert.match(choiceCardSource, /stateNamespace: namespace/);
  assert.match(choiceCardSource, /stepId: sid/);
});

test("file picker resumes manifest flow after upload with skill_manifest_action", () => {
  assert.match(filePickerSource, /skillName,\s*stateNamespace,\s*stepId,/);
  assert.match(filePickerSource, /verb: "skill_manifest_action"/);
  assert.match(filePickerSource, /action: "resume"/);
  assert.match(filePickerSource, /skillName: skill/);
  assert.match(filePickerSource, /stateNamespace: namespace/);
  assert.match(filePickerSource, /stepId: sid/);
});

test("sdui node types expose manifest metadata fields", () => {
  assert.match(sduiTypesSource, /export type SduiChoiceCardNode = \{[\s\S]*skillName\?: string;/);
  assert.match(sduiTypesSource, /export type SduiChoiceCardNode = \{[\s\S]*stateNamespace\?: string;/);
  assert.match(sduiTypesSource, /export type SduiChoiceCardNode = \{[\s\S]*stepId\?: string;/);
  assert.match(sduiTypesSource, /export type SduiFilePickerNode = SduiOptionalId & \{[\s\S]*skillName\?: string;/);
  assert.match(sduiTypesSource, /export type SduiFilePickerNode = SduiOptionalId & \{[\s\S]*stateNamespace\?: string;/);
  assert.match(sduiTypesSource, /export type SduiFilePickerNode = SduiOptionalId & \{[\s\S]*stepId\?: string;/);
});
