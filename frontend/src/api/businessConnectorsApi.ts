import { backendRequest } from "@/api/backendApi";

export type ConnectorKind = "feishu_webhook" | "openai";
export interface BusinessConnector {
  id: string;
  kind: ConnectorKind;
  name: string;
  enabled: boolean;
  credential_configured: boolean;
  signing_configured: boolean;
  config: {
    endpoint?: string | null;
    default_model?: string | null;
    backup_model?: string | null;
    model_allowlist?: string[];
    daily_limit?: number;
    monthly_budget_usd?: string;
    max_output_tokens?: number;
    input_price_per_million?: string;
    output_price_per_million?: string;
  };
  updated_at: string | null;
  last_test_at: string | null;
  last_test_ok: boolean | null;
}

export interface ConnectorWrite {
  kind: ConnectorKind;
  name: string;
  enabled: boolean;
  endpoint?: string;
  credential?: string;
  signing_secret?: string;
  default_model?: string;
  backup_model?: string;
  model_allowlist?: string[];
  daily_limit: number;
  monthly_budget_usd: number;
  max_output_tokens: number;
  input_price_per_million: number;
  output_price_per_million: number;
}
export interface FeishuRoute {
  id: string;
  event_key: string;
  connector_id: string;
  enabled: boolean;
  cooldown_seconds: number;
  daily_limit: number;
}
export interface NotificationTemplate {
  id: string;
  event_key: string;
  title: string;
  body_template: string;
  enabled: boolean;
}
export interface NotificationDelivery {
  id: string;
  event_key: string;
  source_event_id: string;
  status: string;
  attempts: number;
  error_code: string | null;
  created_at: string;
}
const base = "/api/business-rules/connectors";

export async function listBusinessConnectors(): Promise<BusinessConnector[]> {
  return (await backendRequest<BusinessConnector[]>(base)).data;
}
export async function saveBusinessConnector(body: ConnectorWrite, id?: string): Promise<BusinessConnector> {
  return (await backendRequest<BusinessConnector>(id ? base + "/" + id : base, {
    method: id ? "PUT" : "POST",
    body: JSON.stringify(body),
  })).data;
}
export async function disableBusinessConnector(id: string): Promise<BusinessConnector> {
  return (await backendRequest<BusinessConnector>(base + "/" + id, { method: "DELETE" })).data;
}
export async function testBusinessConnector(id: string): Promise<{ok: boolean}> {
  return (await backendRequest<{ok: boolean}>(base + "/" + id + "/test", {
    method: "POST",
  })).data;
}
export async function listFeishuRoutes(): Promise<FeishuRoute[]> {
  return (await backendRequest<FeishuRoute[]>(base + "/routes/list")).data;
}
export async function saveFeishuRoute(body: Omit<FeishuRoute, "id">): Promise<void> {
  await backendRequest(base + "/routes", { method: "POST", body: JSON.stringify(body) });
}
export async function listNotificationTemplates(): Promise<NotificationTemplate[]> {
  return (await backendRequest<NotificationTemplate[]>(base + "/templates/list")).data;
}
export async function saveNotificationTemplate(body: Omit<NotificationTemplate, "id">): Promise<void> {
  await backendRequest(base + "/templates", { method: "POST", body: JSON.stringify(body) });
}
export async function listNotificationDeliveries(): Promise<NotificationDelivery[]> {
  return (await backendRequest<NotificationDelivery[]>(base + "/deliveries/list")).data;
}
export async function listBusinessUsage(): Promise<{
  notifications: Array<{ status: string; n: number }>;
  ai: Array<{ connector_id: string; model: string; requests: number; input_tokens: number; output_tokens: number; cost_usd: string | null }>;
}> {
  return (await backendRequest<{
    notifications: Array<{ status: string; n: number }>;
    ai: Array<{ connector_id: string; model: string; requests: number; input_tokens: number; output_tokens: number; cost_usd: string | null }>;
  }>(base + "/usage/summary")).data;
}
