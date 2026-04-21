import { randomUUID } from "node:crypto";

export function createMessageId(): string {
  return `msg_${randomUUID()}`;
}

export function createPartId(): string {
  return `part_${randomUUID()}`;
}
