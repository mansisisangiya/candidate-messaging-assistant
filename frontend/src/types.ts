// All API types live here. They mirror backend/app/models.py (keep them in sync by hand).

export type RunStatus = "running" | "awaiting_approval" | "approved" | "rejected" | "failed";
export type StepType = "tool_call" | "tool_result" | "llm_message" | "error";
export type CandidateStage = "applied" | "screening" | "interview" | "offer";

export interface Candidate {
  id: string;
  name: string;
  email: string;
  job_id: string;
  stage: CandidateStage;
}

export interface Job {
  id: string;
  title: string;
  team: string;
  location: string;
}

export interface Message {
  sender: "candidate" | "recruiter";
  text: string;
  sent_at: string; // ISO 8601
}

export interface Conversation {
  id: string;
  candidate_id: string;
  messages: Message[];
}

export interface AgentStep {
  index: number;
  type: StepType;
  name: string | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error: string | null;
  duration_ms: number;
  ts: string;
}

export interface AgentRun {
  id: string;
  conversation_id: string;
  status: RunStatus;
  instructions: string | null;
  steps: AgentStep[];
  draft_text: string | null;
  final_text: string | null;
  rejection_reason: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

/** A run without its steps, as returned by the list endpoint. */
export interface RunSummary extends Omit<AgentRun, "steps"> {
  step_count: number;
}

export interface ConversationSummary {
  id: string;
  candidate_name: string;
  job_title: string;
  last_message_preview: string;
  latest_run_status: RunStatus | null;
}

export interface ConversationDetail {
  conversation: Conversation;
  candidate: Candidate;
  job: Job;
  latest_run: AgentRun | null;
}

// Request bodies
export interface DraftRequest {
  instructions?: string; // max 500
}
export interface ApproveRequest {
  edited_text?: string; // 1-2000
}
export interface RejectRequest {
  reason: string; // 3-500
}

/** The backend's error envelope: {"error": {"code", "message"}}. */
export interface ApiErrorBody {
  error: { code: string; message: string };
}

/** Thrown by every api.ts call that fails. `status` is 0 when the server was unreachable. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}
