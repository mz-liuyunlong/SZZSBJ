import { backendRequest } from "@/api/backendApi";

export type Condition = { field: string; op: string; value: string | number | boolean | string[] | number[] };
export type ConditionGroup = { logic: "and" | "or"; conditions: Condition[] };
export type Expression = { logic: "and" | "or"; groups: ConditionGroup[] };
export type RecipientSet = { group_ids: string[]; people_ids: string[]; dynamic_roles: string[]; group_mention: boolean };
export type NotificationPolicy = {
  mode: "immediate" | "daily" | "aggregate";
  daily_time: string; timezone: "Asia/Shanghai" | "America/New_York" | "UTC";
  aggregate_minutes: number; quiet_from: string | null; quiet_until: string | null;
  cooldown_minutes: number; daily_limit: number; trigger: "on_enter" | "repeat";
  send_recovery: boolean; debounce_samples: number; escalation_minutes: number;
  escalation_recipients: RecipientSet;
};
export type Branch = {
  label: string; when: Expression; recipients: RecipientSet;
  group_template: string; personal_template: string;
};
export interface NotificationRule {
  name: string; event_key: string; enabled: boolean; scope: Record<string, string[]>;
  condition: Expression; recovery_condition: Expression | null; branches: Branch[]; recipients: RecipientSet;
  group_template: string; personal_template: string; policy: NotificationPolicy;
}
export type StoredNotificationRule = {
  id: string; name: string; event_key: string; enabled: boolean;
  spec: NotificationRule; version: number; updated_at: string;
};
export type NotificationTarget = {
  groups: Array<{ id: string; name: string; enabled: boolean }>;
  people: Array<{ id: string; name: string; employee_key: string; enabled: boolean; mapped: boolean }>;
};
export type NotificationDelivery = {
  id: string; rule_id: string; event_id: string; kind: "group" | "person";
  target_id: string; status: string; attempts: number; error_code: string | null;
  created_at: string; last_attempt_at: string | null;
};
export type Simulation = { total: number; matches: number; unknowns: number; no_matches: number;
  results: Array<{ object_key: string; result: string; trace: unknown; branches: string[] }>;
};

const base = "/api/business-rules/notification-rules";
export async function getNotificationRules(): Promise<StoredNotificationRule[]> {
  return (await backendRequest<StoredNotificationRule[]>(base)).data;
}
export async function getNotificationFields(): Promise<Record<string, Record<string, string>>> {
  return (await backendRequest<Record<string, Record<string, string>>>(base + "/fields")).data;
}
export async function getNotificationTargets(): Promise<NotificationTarget> {
  return (await backendRequest<NotificationTarget>(base + "/targets")).data;
}
export async function putNotificationRule(spec: NotificationRule, id?: string): Promise<StoredNotificationRule> {
  return (await backendRequest<StoredNotificationRule>(id ? `${base}/${id}` : base, {
    method: id ? "PUT" : "POST", body: JSON.stringify(spec),
  })).data;
}
export async function simulateNotificationRule(spec: NotificationRule, samples: Array<{ object_key: string; facts: Record<string, string | number | boolean> }>): Promise<Simulation> {
  return (await backendRequest<Simulation>(`${base}/simulate`, { method: "POST", body: JSON.stringify({ rule: spec, samples }) })).data;
}
export async function getNotificationDeliveries(): Promise<NotificationDelivery[]> {
  return (await backendRequest<NotificationDelivery[]>(`${base}/deliveries`)).data;
}
export async function saveNotificationPerson(person: { name: string; employee_key: string; feishu_open_id: string }): Promise<void> {
  await backendRequest(`${base}/people`, { method: "POST", body: JSON.stringify({ ...person, enabled: true }) });
}
export function emptyRecipients(): RecipientSet {
  return { group_ids: [], people_ids: [], dynamic_roles: [], group_mention: false };
}
export function defaultNotificationRule(eventKey = "inventory_alert", firstField = "available_stock"): NotificationRule {
  return {
    name: "新通知规则", event_key: eventKey, enabled: false, scope: {},
    condition: { logic: "and", groups: [{ logic: "and", conditions: [{ field: firstField, op: "lt", value: 10 }] }] },
    recovery_condition: null,
    branches: [], recipients: emptyRecipients(),
    group_template: "【{event_key}】\n{message}\nSKU：{sku}",
    personal_template: "【{event_key}】请处理\n{message}\nSKU：{sku}",
    policy: { mode: "immediate", daily_time: "09:00", timezone: "Asia/Shanghai",
      aggregate_minutes: 30, quiet_from: null, quiet_until: null,
      cooldown_minutes: 60, daily_limit: 100, trigger: "on_enter",
      send_recovery: true, debounce_samples: 1, escalation_minutes: 0,
      escalation_recipients: emptyRecipients() },
  };
}

export type NotificationRuleRevision = { version: number; actor: string; created_at: string };
export async function getNotificationRevisions(id: string): Promise<NotificationRuleRevision[]> {
  return (await backendRequest<NotificationRuleRevision[]>(`${base}/${id}/versions`)).data;
}
export async function restoreNotificationRevision(id: string, version: number): Promise<void> {
  await backendRequest(`${base}/${id}/restore/${version}`, { method: "POST" });
}
