/**
 * Tek doğrulama kaynağı `services/api/app/models/enums.py`dır. Buradaki
 * etiket/renk eşlemeleri yalnız SUNUM amaçlıdır — asıl değerler backend'den
 * aynen gelir. Bilinmeyen/yeni bir enum değeri gelirse (backend güncellenip
 * panel güncellenmezse) UI ÇÖKMEZ: ham değeri nötr bir rozet olarak gösterir.
 */

export type BadgeTone = "neutral" | "brand" | "success" | "warning" | "danger" | "info";

function fallback(value: string): { label: string; tone: BadgeTone } {
  return { label: value, tone: "neutral" };
}

const LEAD_STATUS_MAP: Record<string, { label: string; tone: BadgeTone }> = {
  new: { label: "Yeni", tone: "info" },
  in_campaign: { label: "Kampanyada", tone: "brand" },
  contacted: { label: "Arandı", tone: "neutral" },
  interested: { label: "İlgileniyor", tone: "success" },
  demo_requested: { label: "Demo İstedi", tone: "success" },
  callback_scheduled: { label: "Geri Arama Planlandı", tone: "warning" },
  not_interested: { label: "İlgilenmiyor", tone: "neutral" },
  do_not_call: { label: "Aranmasın", tone: "danger" },
  wrong_number: { label: "Yanlış Numara", tone: "danger" },
  invalid_phone: { label: "Geçersiz Telefon", tone: "danger" },
  closed_won: { label: "Kazanıldı", tone: "success" },
  closed_lost: { label: "Kaybedildi", tone: "neutral" },
};

const LEAD_PRIORITY_MAP: Record<string, { label: string; tone: BadgeTone }> = {
  high: { label: "Yüksek", tone: "danger" },
  normal: { label: "Normal", tone: "neutral" },
  low: { label: "Düşük", tone: "info" },
};

const CAMPAIGN_STATUS_MAP: Record<string, { label: string; tone: BadgeTone }> = {
  draft: { label: "Taslak", tone: "neutral" },
  ready: { label: "Hazır", tone: "info" },
  running: { label: "Çalışıyor", tone: "success" },
  paused: { label: "Duraklatıldı", tone: "warning" },
  completed: { label: "Tamamlandı", tone: "neutral" },
  cancelled: { label: "İptal Edildi", tone: "danger" },
};

const CALL_STATUS_MAP: Record<string, { label: string; tone: BadgeTone }> = {
  queued: { label: "Sırada", tone: "neutral" },
  preparing: { label: "Hazırlanıyor", tone: "neutral" },
  dialing: { label: "Aranıyor", tone: "info" },
  ringing: { label: "Çalıyor", tone: "info" },
  answered: { label: "Cevaplandı", tone: "brand" },
  agent_active: { label: "Görüşme Sürüyor", tone: "brand" },
  transferring: { label: "Aktarılıyor", tone: "warning" },
  completed: { label: "Tamamlandı", tone: "success" },
  no_answer: { label: "Cevapsız", tone: "warning" },
  busy: { label: "Meşgul", tone: "warning" },
  voicemail: { label: "Telesekreter", tone: "warning" },
  rejected: { label: "Reddedildi", tone: "danger" },
  failed: { label: "Başarısız", tone: "danger" },
  cancelled: { label: "İptal Edildi", tone: "neutral" },
};

const CALL_OUTCOME_MAP: Record<string, { label: string; tone: BadgeTone }> = {
  interested: { label: "İlgileniyor", tone: "success" },
  demo_requested: { label: "Demo İstedi", tone: "success" },
  callback_requested: { label: "Geri Arama İstedi", tone: "warning" },
  decision_maker_unavailable: { label: "Yetkili Yok", tone: "neutral" },
  not_interested: { label: "İlgilenmiyor", tone: "neutral" },
  do_not_call: { label: "Aranmasın", tone: "danger" },
  wrong_number: { label: "Yanlış Numara", tone: "danger" },
  business_closed: { label: "İşyeri Kapalı", tone: "neutral" },
  no_answer: { label: "Cevapsız", tone: "warning" },
  voicemail: { label: "Telesekreter", tone: "warning" },
  technical_failure: { label: "Teknik Hata", tone: "danger" },
  transferred_to_human: { label: "İnsana Aktarıldı", tone: "brand" },
  follow_up_required: { label: "Takip Gerekli", tone: "warning" },
};

const CALLBACK_STATUS_MAP: Record<string, { label: string; tone: BadgeTone }> = {
  pending: { label: "Bekliyor", tone: "warning" },
  scheduled: { label: "Planlandı", tone: "info" },
  done: { label: "Tamamlandı", tone: "success" },
  cancelled: { label: "İptal Edildi", tone: "neutral" },
  missed: { label: "Kaçırıldı", tone: "danger" },
};

const DEMO_STATUS_MAP: Record<string, { label: string; tone: BadgeTone }> = {
  pending: { label: "Bekliyor", tone: "warning" },
  sent: { label: "Gönderildi", tone: "success" },
  cancelled: { label: "İptal Edildi", tone: "neutral" },
};

const ROLE_MAP: Record<string, { label: string; tone: BadgeTone }> = {
  owner: { label: "Sahip", tone: "brand" },
  admin: { label: "Yönetici", tone: "brand" },
  sales_agent: { label: "Satış Temsilcisi", tone: "info" },
  viewer: { label: "İzleyici", tone: "neutral" },
};

function lookup(map: Record<string, { label: string; tone: BadgeTone }>) {
  return (value: string) => map[value] ?? fallback(value);
}

export const leadStatusMeta = lookup(LEAD_STATUS_MAP);
export const leadPriorityMeta = lookup(LEAD_PRIORITY_MAP);
export const campaignStatusMeta = lookup(CAMPAIGN_STATUS_MAP);
export const callStatusMeta = lookup(CALL_STATUS_MAP);
export const callOutcomeMeta = lookup(CALL_OUTCOME_MAP);
export const callbackStatusMeta = lookup(CALLBACK_STATUS_MAP);
export const demoStatusMeta = lookup(DEMO_STATUS_MAP);
export const roleMeta = lookup(ROLE_MAP);

export const ACTIVE_CALL_STATUSES = [
  "queued",
  "preparing",
  "dialing",
  "ringing",
  "answered",
  "agent_active",
  "transferring",
] as const;

export const CAMPAIGN_STATUS_ACTIONS: Record<string, { action: string; label: string }[]> = {
  draft: [{ action: "ready", label: "Hazıra Al" }],
  ready: [{ action: "start", label: "Başlat" }],
  running: [{ action: "pause", label: "Duraklat" }, { action: "stop", label: "Bitir" }],
  paused: [{ action: "resume", label: "Devam Et" }, { action: "cancel", label: "İptal Et" }],
  completed: [],
  cancelled: [],
};
