import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
import { convertToLlm, getLatestCompactionEntry, serializeConversation } from '@earendil-works/pi-coding-agent';
import { registerStrataCompaction } from './adapter.ts';

export default function strataCompaction(pi: ExtensionAPI) {
  registerStrataCompaction(pi, { convertToLlm, serializeConversation, getLatestCompactionEntry });
}
