import {
  ApiError,
  type AgentRun,
  type ApproveRequest,
  type ConversationDetail,
  type ConversationSummary,
  type DraftRequest,
  type RejectRequest,
  type RunSummary,
} from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Turn a failed response into an ApiError, using the error envelope when the body has one. */
async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null; // not JSON (for example a proxy error page)
  }
  const error = isRecord(body) ? body.error : undefined;
  if (isRecord(error) && typeof error.code === "string" && typeof error.message === "string") {
    return new ApiError(error.code, error.message, response.status);
  }
  return new ApiError("http_error", `Request failed with status ${response.status}`, response.status);
}

async function request<T>(path: string, method: "GET" | "POST", body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("network_error", "Could not reach the server", 0);
  }
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

const enc = encodeURIComponent;

export const listConversations = (): Promise<ConversationSummary[]> =>
  request("/api/conversations", "GET");

export const getConversation = (id: string): Promise<ConversationDetail> =>
  request(`/api/conversations/${enc(id)}`, "GET");

export const createDraft = (conversationId: string, instructions?: string): Promise<AgentRun> => {
  const body: DraftRequest = instructions ? { instructions } : {};
  return request(`/api/conversations/${enc(conversationId)}/drafts`, "POST", body);
};

export const listRuns = (conversationId?: string): Promise<RunSummary[]> =>
  request(
    conversationId === undefined ? "/api/runs" : `/api/runs?conversation_id=${enc(conversationId)}`,
    "GET",
  );

export const getRun = (runId: string): Promise<AgentRun> => request(`/api/runs/${enc(runId)}`, "GET");

export const approveRun = (runId: string, editedText?: string): Promise<AgentRun> => {
  const body: ApproveRequest = editedText ? { edited_text: editedText } : {};
  return request(`/api/runs/${enc(runId)}/approve`, "POST", body);
};

export const rejectRun = (runId: string, reason: string): Promise<AgentRun> => {
  const body: RejectRequest = { reason };
  return request(`/api/runs/${enc(runId)}/reject`, "POST", body);
};

/** Text safe to show a user for any thrown value. */
export function describeError(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}
