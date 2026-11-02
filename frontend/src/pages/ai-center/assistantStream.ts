import { readAuthToken } from '@/pages/auth/authSession';

export type AssistantSource = { url: string; title: string };
export type StreamSignal =
  | { type: 'thinking' }
  | { type: 'searching' }
  | { type: 'delta'; text: string }
  | { type: 'done'; data: {
    chat_id: string;
    response: string;
    input_tokens: number;
    output_tokens: number;
    searched: boolean;
    sources: AssistantSource[];
  } }
  | { type: 'error'; code: string };

export type AssistantRequest = {
  chat_id: string | null;
  message: string;
  attachments: Array<{ name: string; content_base64: string }>;
};

/** Read a POST SSE response without exposing bearer tokens in URLs. */
export async function requestAssistantStream(
  body: AssistantRequest,
  onSignal: (signal: StreamSignal) => void,
): Promise<void> {
  const token = readAuthToken();
  const response = await fetch('/api/ai-runtime/assistant/stream', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    throw new Error(`AI_STREAM_HTTP_${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let gotDone = false;
  const readBlock = (block: string) => {
    const raw = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (!raw) return;
    const value: StreamSignal = JSON.parse(raw);
    if (value.type === 'done') gotDone = true;
    if (value.type === 'error') throw new Error(value.code || 'AI_STREAM_ERROR');
    onSignal(value);
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        readBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) readBlock(buffer);
    if (!gotDone) throw new Error('AI_STREAM_INTERRUPTED');
  } finally {
    reader.releaseLock();
  }
}
