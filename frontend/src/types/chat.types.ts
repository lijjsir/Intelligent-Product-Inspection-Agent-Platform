import type { RagSpace } from "./rag-space.types";

export interface ChatSession {
  id: string;
  org_id: string;
  user_id: string;
  title?: string | null;
  status: string;
  last_message_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export type ChatStreamPhase = "idle" | "connecting" | "streaming" | "closing";

export interface ChatAttachment {
  id: string;
  name: string;
  url: string;
  content_type?: string | null;
  size_bytes: number;
  kind: "image" | "file" | string;
}

export type ChatAgentName = "chat" | "inspection_task";

export type ChatSubRoute =
  | "general_chat"
  | "rag_qa"
  | "quality_qa"
  | "task_create"
  | "inspection_execute";

export type ChatUiSchema =
  | "chat_text_v1"
  | "rag_answer_v1"
  | "quality_answer_v1"
  | "task_action_v1"
  | "task_result_v1"
  | "paper_review_report_v1"
  | "error_v1";

export interface PaperReviewReportFile {
  format: "md" | "docx" | "pdf";
  file_name: string;
  bucket: string;
  object_key: string;
  url: string;
  content_type: string;
}

export interface PaperReviewIssueLocation {
  section?: string;
  section_title?: string;
  paragraph_index?: number;
  paragraph_no?: number;
  line?: number;
  template_id?: string;
  display_text?: string;
}

export interface PaperReviewIssue {
  code: string;
  title: string;
  severity: string;
  category: string;
  message: string;
  evidence: string;
  location: PaperReviewIssueLocation;
  suggestion: string;
  engine?: string;
  engine_rule_id?: string;
  confidence?: string;
}

export interface PaperReviewEngineStatus {
  name: string;
  ok: boolean;
  detail?: string;
}

export interface PaperReviewReport {
  score: number;
  issue_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  summary: string;
  chat_advice?: string;
  issues?: PaperReviewIssue[];
  limitations: string[];
  report_files: PaperReviewReportFile[];
  model_used?: boolean;
  document_type: string;
  template_id: string;
  template_errors: string[];
  engines_used?: string[];
  engine_status?: PaperReviewEngineStatus[];
  runtime_ready?: boolean;
}

export type ChatMode = "auto" | "chat" | "inspection";

export interface ChatTaskDraft {
  product_id?: string | null;
  spec_code?: string | null;
  image_urls?: string[];
  priority?: number | null;
  metadata?: Record<string, unknown>;
}

export interface ChatCreatedTask {
  id: string;
  result_id?: string | null;
  status: string;
  product_id: string;
  spec_code: string;
  priority: number;
  image_count: number;
}

export interface ChatExpectationCheck {
  expected_verdict: string;
  actual_verdict: string;
  matched: boolean;
}

export interface ChatRagSummary {
  rag_space_id?: string | null;
  rag_space_name?: string | null;
  rag_space_ids?: string[];
  rag_space_names?: string[];
  system_rag_space_ids?: string[];
  system_rag_space_names?: string[];
  standard_binding_name?: string | null;
  merged_rag_source_count?: number;
  hit_count: number;
  citation_coverage: number;
  top_sources: string[];
  source_graph?: string | null;
}

export interface ChatResultCard {
  product_id: string;
  product_family?: string | null;
  product_name?: string | null;
  spec_code: string;
  verdict: string;
  overall_score: number;
  risk_level: string;
  key_reasons: string[];
  failed_rules: string[];
  expectation_check?: ChatExpectationCheck | null;
  rag_summary?: ChatRagSummary | null;
}

export interface ChatInspectionTaskContext {
  task_id?: string | null;
  product_id?: string | null;
  spec_code?: string | null;
  status?: string | null;
  priority?: number | null;
  created_at?: string | null;
  finished_at?: string | null;
  verdict?: string | null;
  overall_score?: number | null;
  risk_level?: string | null;
  risk_score?: number | null;
  prompt_version?: string | null;
  model_key?: string | null;
  trace_id?: string | null;
  failed_rules?: string[];
  root_cause?: string | null;
}

export interface ChatInspectionContext {
  scope: "user_recent_tasks" | "org_recent_tasks" | "unavailable" | string;
  summary_window: number;
  stats: Record<string, number>;
  recent_tasks: ChatInspectionTaskContext[];
  recent_failures: ChatInspectionTaskContext[];
  latest_task?: ChatInspectionTaskContext | null;
  selected_tasks?: ChatInspectionTaskContext[];
  error?: string | null;
}

export interface ChatArtifact {
  artifact_id: string;
  type: string;
  source_agent: string;
  content?: Record<string, unknown>;
  citations?: Array<Record<string, unknown>>;
  confidence?: number | null;
  created_at?: string | null;
}

export interface ChatRouteTrace {
  iterations?: number;
  capabilities_used?: string[];
  satisfied?: boolean;
  score?: number;
  surface?: string;
  steps?: Array<Record<string, unknown>>;
  observations?: Array<Record<string, unknown>>;
  errors?: Array<Record<string, unknown>>;
}

export interface ChatMessagePayload {
  result_id?: string | null;
  result?: {
    id?: string;
    verdict?: string;
    overall_score?: number;
    risk_level?: string;
    risk_score?: number;
  } | null;
  answer?: string;
  citations?: Array<Record<string, unknown>>;
  quality?: {
    confidence?: number;
    evidence_coverage?: number;
    traceability?: number;
    faithfulness?: number;
    risk_level?: string;
    risk_score?: number;
    passed?: boolean;
    hallucination_flags?: string[];
  };
  trust_scoring?: {
    status?: "scored" | "rule_only" | "reviewing" | "failed" | string;
    trust_score?: number | null;
    risk_level?: string | null;
    hallucination_risk?: number | null;
    overconfidence?: number | null;
    has_citation?: boolean | null;
    trace_url?: string | null;
    review_model?: string | null;
    error?: string | null;
  } | null;
  result_card?: ChatResultCard | null;
  expectation_check?: ChatExpectationCheck | null;
  rag_summary?: ChatRagSummary | null;
  trace_id?: string | null;
  agent?: ChatAgentName | string | null;
  sub_route?: ChatSubRoute | string | null;
  ui_schema?: ChatUiSchema | string | null;
  trace_url?: string | null;
  workflow_version?: string;
  prompt_version?: string;
  retrieval_metrics?: Record<string, unknown>;
  summary?: string;
  intent?: "smalltalk" | "general_qa" | "quality_qa" | "task_create" | "task_followup" | string;
  intent_confidence?: number;
  action_state?: string;
  task_draft?: ChatTaskDraft | null;
  task_form_defaults?: ChatTaskDraft | null;
  task_submit_mode?: string | null;
  missing_slots?: string[];
  pending_action?: string | null;
  awaiting_confirmation?: boolean;
  created_task?: ChatCreatedTask | null;
  materialized_task?: ChatCreatedTask | null;
  materialization_status?: "synced" | "failed" | string;
  materialization_error?: string | null;
  route_decision?: Record<string, unknown> | null;
  artifacts?: ChatArtifact[];
  route_trace?: ChatRouteTrace | null;
  capabilities_used?: string[];
  satisfied?: boolean;
  selected_rag_space?: Pick<RagSpace, "id" | "name" | "description"> | null;
  attachment_echo?: ChatAttachment[];
  paper_format_report?: PaperReviewReport | null;
  message_type?: string;
  status?: string;
  workflow_run_id?: string;
  error?: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  seq_no: number;
  role: "user" | "assistant" | "system";
  message_type: string;
  content: string;
  payload?: ChatMessagePayload | null;
  created_at?: string | null;
  client_seq?: number;
  optimistic?: boolean;
}

export interface ChatMessageSendRequest {
  message: string;
  schema_version?: string;
  workspace?: string;
  metadata?: Record<string, unknown>;
  ext?: Record<string, unknown>;
}

export interface ChatSendResponse {
  session: ChatSession;
  user_message: ChatMessage;
  assistant_message_id: string;
  workflow_run_id: string;
}

export interface ChatStreamEvent {
  event: "run_started" | "message_delta" | "message_final" | "message_patch" | "quality_signal" | "run_failed";
  session_id: string;
  message_id?: string | null;
  workflow_run_id?: string | null;
  delta?: string | null;
  content?: string | null;
  quality?: ChatMessagePayload["quality"] | null;
  payload?: ChatMessagePayload | null;
  message_type?: string | null;
  ts?: string | null;
}
