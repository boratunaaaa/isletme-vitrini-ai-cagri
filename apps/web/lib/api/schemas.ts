import { z } from "zod";

/**
 * Bu dosyadaki her şema `services/api/app/schemas/**` ve
 * `services/api/app/models/enums.py` dosyaları OKUNARAK elle çıkarıldı — hiçbir
 * alan adı veya enum değeri tahmin edilmedi. Backend şeması değişirse bu dosya
 * da güncellenmeli (tek gerçek kaynak backend'dir).
 */

// ─── Enum'lar (app/models/enums.py) ────────────────────────────────────────

export const leadStatusValues = [
  "new",
  "in_campaign",
  "contacted",
  "interested",
  "demo_requested",
  "callback_scheduled",
  "not_interested",
  "do_not_call",
  "wrong_number",
  "invalid_phone",
  "closed_won",
  "closed_lost",
] as const;
export const leadStatusSchema = z.enum(leadStatusValues);
export type LeadStatus = z.infer<typeof leadStatusSchema>;

export const leadPriorityValues = ["high", "normal", "low"] as const;
export const leadPrioritySchema = z.enum(leadPriorityValues);

export const campaignStatusValues = [
  "draft",
  "ready",
  "running",
  "paused",
  "completed",
  "cancelled",
] as const;
export const campaignStatusSchema = z.enum(campaignStatusValues);
export type CampaignStatus = z.infer<typeof campaignStatusSchema>;

export const campaignLeadStatusValues = [
  "pending",
  "scheduled",
  "calling",
  "retry_scheduled",
  "completed",
  "skipped",
  "suppressed",
  "exhausted",
] as const;

export const callStatusValues = [
  "queued",
  "preparing",
  "dialing",
  "ringing",
  "answered",
  "agent_active",
  "transferring",
  "completed",
  "no_answer",
  "busy",
  "voicemail",
  "rejected",
  "failed",
  "cancelled",
] as const;
export const callStatusSchema = z.enum(callStatusValues);
export type CallStatus = z.infer<typeof callStatusSchema>;

export const activeCallStatuses: readonly CallStatus[] = [
  "queued",
  "preparing",
  "dialing",
  "ringing",
  "answered",
  "agent_active",
  "transferring",
];

export const callOutcomeValues = [
  "interested",
  "demo_requested",
  "callback_requested",
  "decision_maker_unavailable",
  "not_interested",
  "do_not_call",
  "wrong_number",
  "business_closed",
  "no_answer",
  "voicemail",
  "technical_failure",
  "transferred_to_human",
  "follow_up_required",
] as const;
export const callOutcomeSchema = z.enum(callOutcomeValues);
export type CallOutcome = z.infer<typeof callOutcomeSchema>;

export const conversationEngineValues = ["openai_realtime", "local_pipeline", "test"] as const;

export const callbackStatusValues = ["pending", "scheduled", "done", "cancelled", "missed"] as const;
export const callbackStatusSchema = z.enum(callbackStatusValues);

export const demoRequestStatusValues = ["pending", "sent", "cancelled"] as const;

export const roleValues = ["owner", "admin", "sales_agent", "viewer"] as const;
export const roleSchema = z.enum(roleValues);
export type Role = z.infer<typeof roleSchema>;

// ─── Ortak ───────────────────────────────────────────────────────────────

export function pageSchema<T extends z.ZodTypeAny>(item: T) {
  return z.object({
    items: z.array(item),
    total: z.number(),
    page: z.number(),
    page_size: z.number(),
  });
}
export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export const okResponseSchema = z.object({
  ok: z.boolean(),
  detail: z.string().nullable().optional(),
});

// ─── Auth (app/schemas/auth.py) ────────────────────────────────────────────

export const userOutSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  role: z.string(),
  is_active: z.boolean(),
  last_login_at: z.string().nullable(),
  created_at: z.string(),
});
export type UserOut = z.infer<typeof userOutSchema>;

export const meResponseSchema = z.object({
  user: userOutSchema,
  permissions: z.array(z.string()),
  csrf_token: z.string(),
});
export type MeResponse = z.infer<typeof meResponseSchema>;

// ─── Leads (app/schemas/leads.py) ──────────────────────────────────────────

export const tagOutSchema = z.object({
  id: z.string(),
  name: z.string(),
  color: z.string(),
});
export type TagOut = z.infer<typeof tagOutSchema>;

export const leadNoteOutSchema = z.object({
  id: z.string(),
  user_id: z.string().nullable(),
  content: z.string(),
  created_at: z.string(),
});
export type LeadNoteOut = z.infer<typeof leadNoteOutSchema>;

export const leadOutSchema = z.object({
  id: z.string(),
  external_place_id: z.string().nullable(),
  source: z.string(),
  business_name: z.string(),
  sector: z.string().nullable(),
  category: z.string().nullable(),
  city: z.string().nullable(),
  district: z.string().nullable(),
  address: z.string().nullable(),
  website: z.string().nullable(),
  rating: z.number().nullable(),
  review_count: z.number().nullable(),
  phone_masked: z.string().nullable(),
  phone_last_four: z.string().nullable(),
  phone_country_code: z.string().nullable(),
  has_phone: z.boolean(),
  status: z.string(),
  priority: z.string(),
  assigned_user_id: z.string().nullable(),
  demo_link: z.string().nullable(),
  last_contacted_at: z.string().nullable(),
  next_action_at: z.string().nullable(),
  created_at: z.string(),
  tags: z.array(tagOutSchema),
});
export type LeadOut = z.infer<typeof leadOutSchema>;

export const leadFacetsSchema = z.object({
  sectors: z.array(z.string()),
  cities: z.array(z.string()),
  districts: z.array(z.string()),
});

export const phoneRevealResponseSchema = z.object({ phone_e164: z.string() });

export const importPreviewResponseSchema = z.object({
  headers: z.array(z.string()),
  sheet_names: z.array(z.string()),
  guessed_mapping: z.record(z.string(), z.string()),
  preview_rows: z.array(z.record(z.string(), z.unknown())),
  total_rows: z.number(),
});
export type ImportPreviewResponse = z.infer<typeof importPreviewResponseSchema>;

export const importResultOutSchema = z.object({
  job_id: z.string(),
  total_rows: z.number(),
  imported: z.number(),
  duplicates: z.number(),
  invalid: z.number(),
  errors: z.array(z.record(z.string(), z.unknown())),
});
export type ImportResultOut = z.infer<typeof importResultOutSchema>;

export const importJobOutSchema = z.object({
  id: z.string(),
  filename: z.string(),
  source_format: z.string(),
  status: z.string(),
  total_rows: z.number(),
  imported_count: z.number(),
  duplicate_count: z.number(),
  invalid_count: z.number(),
  created_at: z.string(),
});
export type ImportJobOut = z.infer<typeof importJobOutSchema>;

// ─── Campaigns (app/schemas/campaigns.py) ──────────────────────────────────

export const campaignOutSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  status: z.string(),
  conversation_engine: z.string(),
  realtime_model: z.string(),
  realtime_voice: z.string(),
  agent_prompt_version_id: z.string().nullable(),
  daily_limit: z.number(),
  concurrent_call_limit: z.number(),
  call_start_hour: z.number(),
  call_end_hour: z.number(),
  max_call_duration_seconds: z.number(),
  max_retry_count: z.number(),
  retry_delay_minutes: z.number(),
  region_filter: z.array(z.string()).nullable(),
  sector_filter: z.array(z.string()).nullable(),
  created_at: z.string(),
});
export type CampaignOut = z.infer<typeof campaignOutSchema>;

export const campaignStatsSchema = z.object({
  total_leads: z.number(),
  pending: z.number(),
  calling: z.number(),
  retry_scheduled: z.number(),
  completed: z.number(),
  suppressed: z.number(),
  exhausted: z.number(),
  calls_today: z.number(),
  outcomes: z.record(z.string(), z.number()),
  total_cost_usd: z.string(),
});
export type CampaignStats = z.infer<typeof campaignStatsSchema>;

// ─── Calls (app/schemas/calls.py) ──────────────────────────────────────────

export const callOutSchema = z.object({
  id: z.string(),
  lead_id: z.string(),
  campaign_id: z.string().nullable(),
  initiated_by: z.string().nullable(),
  telephony_provider: z.string(),
  conversation_provider: z.string(),
  model: z.string(),
  voice: z.string(),
  status: z.string(),
  outcome: z.string().nullable(),
  phone_last_four: z.string().nullable(),
  started_at: z.string().nullable(),
  answered_at: z.string().nullable(),
  ended_at: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  disconnect_reason: z.string().nullable(),
  error_code: z.string().nullable(),
  safe_summary: z.string().nullable(),
  callback_at: z.string().nullable(),
  demo_requested: z.boolean(),
  transfer_requested: z.boolean(),
  created_at: z.string(),
  business_name: z.string().nullable().optional(),
});
export type CallOut = z.infer<typeof callOutSchema>;

export const callEventOutSchema = z.object({
  id: z.string(),
  event_type: z.string(),
  safe_payload: z.record(z.string(), z.unknown()).nullable(),
  event_timestamp: z.string(),
});
export type CallEventOut = z.infer<typeof callEventOutSchema>;

export const callUsageOutSchema = z.object({
  provider: z.string(),
  model: z.string(),
  input_audio_tokens: z.number(),
  cached_input_audio_tokens: z.number(),
  output_audio_tokens: z.number(),
  input_text_tokens: z.number(),
  cached_input_text_tokens: z.number(),
  output_text_tokens: z.number(),
  reasoning_tokens: z.number().nullable(),
  usage_source: z.string(),
  estimated_ai_cost: z.string(),
  estimated_telephony_cost: z.string(),
  estimated_total_cost: z.string(),
  currency: z.string(),
});
export type CallUsageOut = z.infer<typeof callUsageOutSchema>;

export const callDetailOutSchema = z.object({
  call: callOutSchema,
  events: z.array(callEventOutSchema),
  usage: callUsageOutSchema.nullable(),
  transcript: z.array(z.record(z.string(), z.unknown())).nullable(),
});
export type CallDetailOut = z.infer<typeof callDetailOutSchema>;

// ─── Ops: callbacks / demo-requests / suppression (app/schemas/ops.py) ────

export const callbackOutSchema = z.object({
  id: z.string(),
  lead_id: z.string(),
  call_id: z.string().nullable(),
  requested_at: z.string(),
  callback_at: z.string(),
  assigned_user_id: z.string().nullable(),
  status: z.string(),
  notes: z.string().nullable(),
  business_name: z.string().nullable().optional(),
});
export type CallbackOut = z.infer<typeof callbackOutSchema>;

export const demoRequestOutSchema = z.object({
  id: z.string(),
  lead_id: z.string(),
  call_id: z.string().nullable(),
  requested_channel: z.string(),
  status: z.string(),
  assigned_user_id: z.string().nullable(),
  sent_at: z.string().nullable(),
  created_at: z.string(),
  business_name: z.string().nullable().optional(),
  demo_link: z.string().nullable().optional(),
});
export type DemoRequestOut = z.infer<typeof demoRequestOutSchema>;

export const waLinkResponseSchema = z.object({ wa_link: z.string() });

export const suppressionOutSchema = z.object({
  id: z.string(),
  phone_last_four: z.string(),
  lead_id: z.string().nullable(),
  reason: z.string(),
  source: z.string(),
  added_by: z.string().nullable(),
  created_at: z.string(),
  business_name: z.string().nullable().optional(),
});
export type SuppressionOut = z.infer<typeof suppressionOutSchema>;

// ─── Content: knowledge base / prompts (app/schemas/content.py) ───────────

export const kbEntryOutSchema = z.object({
  id: z.string(),
  category: z.string(),
  title: z.string(),
  content: z.string(),
  is_active: z.boolean(),
  version: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type KbEntryOut = z.infer<typeof kbEntryOutSchema>;

export const promptVersionOutSchema = z.object({
  id: z.string(),
  name: z.string(),
  system_prompt: z.string(),
  opening_script: z.string(),
  objective: z.string(),
  objection_rules: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
});
export type PromptVersionOut = z.infer<typeof promptVersionOutSchema>;

// ─── System: dashboard / pricing / settings / audit (app/schemas/system.py) ─

export const integrationStatusSchema = z.object({
  provider: z.string(),
  configured: z.boolean(),
  detail: z.string(),
});
export type IntegrationStatus = z.infer<typeof integrationStatusSchema>;

export const dashboardStatsSchema = z.object({
  calls_today: z.number(),
  answered_today: z.number(),
  avg_duration_seconds: z.number(),
  interested_count: z.number(),
  demo_requested_count: z.number(),
  callback_count: z.number(),
  do_not_call_count: z.number(),
  success_rate: z.number(),
  ai_cost_today_usd: z.string(),
  telephony_cost_today_usd: z.string(),
  total_cost_today_usd: z.string(),
  active_campaigns: z.number(),
  live_calls: z.number(),
  integrations: z.array(integrationStatusSchema),
  gates: z.record(z.string(), z.boolean()),
});
export type DashboardStats = z.infer<typeof dashboardStatsSchema>;

export const pricingOutSchema = z.object({
  id: z.string(),
  provider: z.string(),
  model: z.string(),
  input_audio_price_per_million: z.string(),
  cached_audio_price_per_million: z.string(),
  output_audio_price_per_million: z.string(),
  input_text_price_per_million: z.string(),
  cached_text_price_per_million: z.string(),
  output_text_price_per_million: z.string(),
  currency: z.string(),
  effective_from: z.string(),
  is_active: z.boolean(),
});
export type PricingOut = z.infer<typeof pricingOutSchema>;

export const settingItemSchema = z.object({
  provider: z.string(),
  setting_key: z.string(),
  safe_value: z.string().nullable(),
  is_configured: z.boolean(),
  updated_at: z.string().nullable(),
});
export type SettingItem = z.infer<typeof settingItemSchema>;

export const auditLogOutSchema = z.object({
  id: z.string(),
  user_id: z.string().nullable(),
  action: z.string(),
  resource_type: z.string().nullable(),
  resource_id: z.string().nullable(),
  safe_metadata: z.record(z.string(), z.unknown()).nullable(),
  ip_address: z.string().nullable(),
  created_at: z.string(),
});
export type AuditLogOut = z.infer<typeof auditLogOutSchema>;

// ─── SSE canlı olay zarfı ───────────────────────────────────────────────────
// `app/services/event_bus.py` + gerçek `publish_event(...)` çağrı yerleri
// (app/services/call_service.py, app/providers/notification.py,
// app/api/routes/internal/calls.py) okunarak çıkarıldı. Yayınlanan gerçek
// olay şekilleri:
//   {type:"call_event", event_type, call_id, lead_id, campaign_id, status, payload, ts}
//   {type:"call_completed", call_id, status}
//   {type:"internal_call_event", call_id, event_type}
//   {type:"notification", kind, title, body, resource_type, resource_id, ts}
// Olay HİÇBİR ZAMAN tam bir `call` nesnesi taşımaz — yalnız call_id/status
// sinyali verir. Panel bunu "ilgili listeyi yeniden çek" tetikleyicisi olarak
// kullanır; bilinmeyen/eksik alanlar sayfayı kırmaz (hepsi opsiyonel).
export const liveEventEnvelopeSchema = z.object({
  type: z.string(),
  call_id: z.string().optional(),
  event_type: z.string().optional(),
  status: z.string().optional(),
  lead_id: z.string().optional(),
  campaign_id: z.string().nullable().optional(),
  kind: z.string().optional(),
  title: z.string().optional(),
  body: z.string().optional(),
  ts: z.string().optional(),
});
export type LiveEventEnvelope = z.infer<typeof liveEventEnvelopeSchema>;

// ─── Mutasyon girdi şemaları (RHF + zodResolver için backend Field() kısıtlarıyla) ─

export const loginRequestSchema = z.object({
  email: z.string().min(3).max(255).email("Geçerli bir e-posta adresi girin"),
  password: z.string().min(8).max(200),
});
export type LoginRequestInput = z.infer<typeof loginRequestSchema>;

export const leadUpdateSchema = z.object({
  business_name: z.string().min(1).max(500).optional(),
  sector: z.string().optional().nullable(),
  city: z.string().optional().nullable(),
  district: z.string().optional().nullable(),
  address: z.string().optional().nullable(),
  website: z.string().optional().nullable(),
  demo_link: z.string().optional().nullable(),
  status: leadStatusSchema.optional(),
  priority: leadPrioritySchema.optional(),
  assigned_user_id: z.string().optional().nullable(),
  phone: z.string().optional().nullable(),
});
export type LeadUpdateInput = z.infer<typeof leadUpdateSchema>;

export const leadNoteCreateSchema = z.object({
  content: z.string().min(1).max(5000),
});
export type LeadNoteCreateInput = z.infer<typeof leadNoteCreateSchema>;

export const tagCreateSchema = z.object({
  name: z.string().min(1).max(80),
  color: z
    .string()
    .regex(/^#[0-9a-fA-F]{6}$/, "Geçerli bir hex renk girin")
    .default("#64748b"),
});

export const campaignBaseSchema = z.object({
  name: z.string().min(2).max(255),
  description: z.string().max(4000).optional().nullable(),
  conversation_engine: z.string().default("openai_realtime"),
  realtime_model: z.string().optional().nullable(),
  realtime_voice: z.string().optional().nullable(),
  agent_prompt_version_id: z.string().optional().nullable(),
  daily_limit: z.number().int().min(1).max(500).default(10),
  concurrent_call_limit: z.number().int().min(1).max(10).default(1),
  call_start_hour: z.number().int().min(0).max(23).default(10),
  call_end_hour: z.number().int().min(1).max(24).default(17),
  max_call_duration_seconds: z.number().int().min(60).max(1800).default(300),
  max_retry_count: z.number().int().min(0).max(5).default(2),
  retry_delay_minutes: z.number().int().min(15).max(2880).default(120),
  region_filter: z.array(z.string()).optional().nullable(),
  sector_filter: z.array(z.string()).optional().nullable(),
});
export type CampaignCreateInput = z.infer<typeof campaignBaseSchema>;

export const campaignUpdateSchema = campaignBaseSchema.partial().omit({ conversation_engine: true });
export type CampaignUpdateInput = z.infer<typeof campaignUpdateSchema>;

export const campaignLeadsAddSchema = z.object({
  lead_ids: z.array(z.string()).optional().nullable(),
  sector: z.string().optional().nullable(),
  city: z.string().optional().nullable(),
  district: z.string().optional().nullable(),
  status: z.string().optional().nullable(),
  limit: z.number().int().min(1).max(5000).default(100),
});

export const campaignStatusActionValues = [
  "ready",
  "start",
  "pause",
  "resume",
  "stop",
  "cancel",
  "draft",
] as const;
export const campaignStatusChangeSchema = z.object({
  action: z.enum(campaignStatusActionValues),
});

export const callInitiateRequestSchema = z.object({
  lead_id: z.string(),
  engine: z.string().optional().nullable(),
  model: z.string().optional().nullable(),
  voice: z.string().optional().nullable(),
  idempotency_key: z.string().max(80).optional().nullable(),
});
export type CallInitiateInput = z.infer<typeof callInitiateRequestSchema>;

export const qualityMetricsInSchema = z.object({
  user_quality_score: z.number().int().min(1).max(10).optional().nullable(),
  tr_naturalness_score: z.number().int().min(1).max(10).optional().nullable(),
  understanding_score: z.number().int().min(1).max(10).optional().nullable(),
  sales_flow_score: z.number().int().min(1).max(10).optional().nullable(),
  notes: z.string().max(4000).optional().nullable(),
});
export type QualityMetricsInput = z.infer<typeof qualityMetricsInSchema>;

export const callbackUpdateSchema = z.object({
  status: callbackStatusSchema.optional(),
  callback_at: z.string().optional().nullable(),
  assigned_user_id: z.string().optional().nullable(),
  notes: z.string().max(4000).optional().nullable(),
});
export type CallbackUpdateInput = z.infer<typeof callbackUpdateSchema>;

export const suppressionCreateSchema = z
  .object({
    lead_id: z.string().optional().nullable(),
    phone: z.string().optional().nullable(),
    reason: z.string().min(2).max(255),
  })
  .refine((v) => v.lead_id || v.phone, {
    message: "lead_id veya phone zorunlu",
    path: ["phone"],
  });
export type SuppressionCreateInput = z.infer<typeof suppressionCreateSchema>;

export const kbEntryCreateSchema = z.object({
  category: z.string().min(2).max(60),
  title: z.string().min(2).max(255),
  content: z.string().min(2).max(8000),
  is_active: z.boolean().default(true),
});
export type KbEntryCreateInput = z.infer<typeof kbEntryCreateSchema>;

export const kbEntryUpdateSchema = kbEntryCreateSchema.partial();
export type KbEntryUpdateInput = z.infer<typeof kbEntryUpdateSchema>;

export const promptVersionCreateSchema = z.object({
  name: z.string().min(2).max(120),
  system_prompt: z.string().min(10),
  opening_script: z.string().min(10),
  objective: z.string().min(10),
  objection_rules: z.string().min(10),
});
export type PromptVersionCreateInput = z.infer<typeof promptVersionCreateSchema>;

export const userCreateSchema = z.object({
  email: z.string().min(3).max(255).email(),
  full_name: z.string().min(2).max(255),
  password: z.string().min(10).max(200),
  role: roleSchema,
});
export type UserCreateInput = z.infer<typeof userCreateSchema>;

export const userUpdateSchema = z.object({
  full_name: z.string().min(2).max(255).optional(),
  role: roleSchema.optional(),
  is_active: z.boolean().optional(),
  password: z.string().min(10).max(200).optional().or(z.literal("")),
});
export type UserUpdateInput = z.infer<typeof userUpdateSchema>;

export const settingUpdateSchema = z.object({
  provider: z.string(),
  setting_key: z.string(),
  value: z.string().max(500).optional().nullable(),
});
export type SettingUpdateInput = z.infer<typeof settingUpdateSchema>;

export const pricingUpdateSchema = z.object({
  input_audio_price_per_million: z.string().optional(),
  cached_audio_price_per_million: z.string().optional(),
  output_audio_price_per_million: z.string().optional(),
  input_text_price_per_million: z.string().optional(),
  cached_text_price_per_million: z.string().optional(),
  output_text_price_per_million: z.string().optional(),
  is_active: z.boolean().optional(),
});
export type PricingUpdateInput = z.infer<typeof pricingUpdateSchema>;
