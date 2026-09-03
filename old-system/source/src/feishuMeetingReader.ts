import { execFileSync } from "child_process";

const LARK_CLI = process.env.LARK_CLI_PATH || "./scripts/lark-cli";

// ── 基础类型 ──────────────────────────────────────────────

export interface Meeting {
  id: string;
  topic: string;
  startTime: string;
  endTime: string;
  duration: number; // 分钟
  organizer: string;
  participantCount: number;
}

export interface MeetingNote {
  meetingId: string;
  noteDocToken: string | null;   // AI 纪要文档
  verbatimDocToken: string | null; // 逐字稿文档
  minuteToken: string | null;    // 妙记 token
}

export interface MinuteSummary {
  token: string;
  title: string;
  url: string;
  duration: number; // 秒
  createTime: string;
  owner: string;
}

// ── VC 会议搜索 ───────────────────────────────────────────

/**
 * 搜索已结束的视频会议（最近 N 天）
 * 对应：lark-cli vc +search --start ... --end ... --format json
 */
export function searchMeetings(daysBack = 7, pageSize = 30): Meeting[] {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - daysBack);

  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  const raw = execLarkCli([
    "vc",
    "+search",
    "--start",
    fmt(start),
    "--end",
    fmt(end),
    "--page-size",
    String(pageSize),
    "--format",
    "json",
  ]);

  const parsed = parseJson<{ ok: boolean; data?: { meeting_brief_infos?: unknown[] } }>(raw);
  if (!parsed.ok || !parsed.data?.meeting_brief_infos) {
    return [];
  }

  return parsed.data.meeting_brief_infos.map((m: any) => ({
    id: m.id ?? m.meeting_id ?? "",
    topic: m.topic ?? "无标题",
    startTime: m.start_time ?? "",
    endTime: m.end_time ?? "",
    duration: m.duration ? Math.round(Number(m.duration) / 60) : 0,
    organizer: m.host_user?.name ?? m.organizer?.name ?? "",
    participantCount: m.participant_count ?? 0,
  }));
}

// ── VC 会议纪要 ───────────────────────────────────────────

/**
 * 批量获取会议纪要（含 AI 纪要文档 + 逐字稿文档 + 妙记 token）
 * 对应：lark-cli vc +notes --meeting-ids "id1,id2,..."
 * 单次最多 50 个，自动分批
 */
export function getMeetingNotes(meetingIds: string[]): MeetingNote[] {
  if (meetingIds.length === 0) return [];

  const results: MeetingNote[] = [];
  const BATCH = 50;

  for (let i = 0; i < meetingIds.length; i += BATCH) {
    const batch = meetingIds.slice(i, i + BATCH);
    let raw: string;
    try {
      raw = execLarkCli([
        "vc",
        "+notes",
        "--meeting-ids",
        batch.join(","),
        "--format",
        "json",
      ]);
    } catch {
      // 整批失败：每个会议标记无纪要
      batch.forEach((id) =>
        results.push({ meetingId: id, noteDocToken: null, verbatimDocToken: null, minuteToken: null })
      );
      continue;
    }

    const parsed = parseJson<{ ok: boolean; data?: { notes?: unknown[] } }>(raw);
    const notes: any[] = parsed.data?.notes ?? [];

    for (const id of batch) {
      const note = notes.find((n: any) => n.meeting_id === id || n.id === id);
      results.push({
        meetingId: id,
        noteDocToken: note?.note_doc_token ?? null,
        verbatimDocToken: note?.verbatim_doc_token ?? null,
        minuteToken: note?.minute_token ?? null,
      });
    }
  }

  return results;
}

// ── 妙记纪要内容（逐字稿 / AI总结）────────────────────────

export interface MinuteNotes {
  minuteToken: string;
  title: string;
  summary: string;           // AI 生成的会议总结
  keywords: string[];        // 关键词
  transcriptFile: string;    // 本地转写文件路径（相对项目根目录）
}

/**
 * 通过 minute_token 获取妙记纪要产物（AI总结 + 关键词 + 本地逐字稿文件）
 * 对应：lark-cli vc +notes --minute-tokens <token1,token2,...>
 * 返回结构：data.notes[].artifacts.{summary, keywords, transcript_file}
 */
export function getMinuteNotes(minuteTokens: string[], profile?: string): MinuteNotes[] {
  if (minuteTokens.length === 0) return [];
  let raw: string;
  try {
    raw = execLarkCli([
      "vc", "+notes",
      "--as", "user",
      "--minute-tokens", minuteTokens.join(","),
      "--format", "json",
    ], undefined, profile);
  } catch (e: any) {
    throw new Error(`vc +notes --minute-tokens 失败: ${e.message}`);
  }
  const parsed = parseJson<{ ok: boolean; data?: { notes?: unknown[] } }>(raw);
  const notes: any[] = parsed.data?.notes ?? [];
  return minuteTokens.map((token) => {
    const n = notes.find((x: any) => x.minute_token === token);
    return {
      minuteToken: token,
      title: n?.title ?? token,
      summary: n?.artifacts?.summary ?? "",
      keywords: n?.artifacts?.keywords ?? [],
      transcriptFile: n?.artifacts?.transcript_file ?? "",
    };
  });
}

// ── 妙记搜索 ─────────────────────────────────────────────

/**
 * 搜索妙记列表
 * 对应：lark-cli minutes +search --start ... --end ... --format json [--query ...]
 * 注意：必须传 --start / --end 至少一个时间参数，否则 API 报错
 */
export function searchMinutes(keyword?: string, limit = 20, daysBack = 400, profile?: string): MinuteSummary[] {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - daysBack);

  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  const args = [
    "minutes", "+search",
    "--as", "user",
    "--start", fmt(start),
    "--end", fmt(end),
    "--page-size", String(limit),
    "--format", "json",
  ];
  if (keyword) {
    args.push("--query", keyword);
  }

  let raw: string;
  try {
    raw = execLarkCli(args, undefined, profile);
  } catch (e: any) {
    throw new Error(`searchMinutes lark-cli 失败: ${e.message}`);
  }

  const parsed = parseJson<{ ok: boolean; data?: { items?: unknown[] } }>(raw);
  const items: any[] = parsed.data?.items ?? [];

  return items.map((m: any) => {
    // 实际返回结构：token / meta_data.app_link / display_info（含标题、owner、时长）
    const appLink: string = m.meta_data?.app_link ?? "";
    // display_info：去掉 HTML 标签后，第一个非空行是标题
    const cleanDisplay = (m.display_info ?? "")
      .replace(/&lt;[^&]*&gt;/g, "")
      .replace(/<[^>]*>/g, "");
    const displayLines = cleanDisplay.split("\n");
    const title = displayLines.find((l: string) => l.trim()) || m.token || "无标题";
    // description 格式："所有者: XX 开始时间: YYYY.MM.DD HH:MM:SS 时长: N 分 M 秒"
    const desc: string = m.meta_data?.description ?? "";
    const ownerMatch = desc.match(/所有者:\s*(\S+)/);
    const owner = ownerMatch?.[1] ?? "";
    return {
      token: m.token ?? "",
      title,
      url: appLink,
      duration: 0, // display_info 里有文字时长，不做解析
      createTime: desc,
      owner,
    };
  });
}

// ── 文档内容获取 ──────────────────────────────────────────

/**
 * 读取飞书文档内容（纪要文档 / 逐字稿文档）
 * 对应：lark-cli docs +fetch --api-version v2 --doc <token> --doc-format markdown
 */
export function fetchDocument(docToken: string): string {
  const raw = execLarkCli([
    "docs",
    "+fetch",
    "--api-version",
    "v2",
    "--doc",
    docToken,
    "--doc-format",
    "markdown",
  ]);

  // lark-cli +fetch 返回 JSON 包装或直接 markdown，两种都处理
  try {
    const parsed = parseJson<{ ok: boolean; data?: { content?: string } }>(raw);
    if (parsed.ok && parsed.data?.content) {
      return parsed.data.content;
    }
  } catch {
    // 不是 JSON，直接返回原始内容
  }
  return raw;
}

// ── 工具函数 ──────────────────────────────────────────────

function execLarkCli(args: string[], input?: string, profile?: string): string {
  // 若指定 profile，在所有命令前插入 --profile <name>
  const fullArgs = profile ? ["--profile", profile, ...args] : args;
  try {
    return execFileSync(LARK_CLI, fullArgs, {
      cwd: process.cwd(),
      encoding: "utf8",
      input,
      maxBuffer: 20 * 1024 * 1024,
      stdio: input === undefined ? ["ignore", "pipe", "pipe"] : ["pipe", "pipe", "pipe"],
    });
  } catch (error) {
    const err = error as { stderr?: Buffer | string; message?: string };
    const stderr = Buffer.isBuffer(err.stderr) ? err.stderr.toString("utf8") : err.stderr;
    throw new Error(stderr || err.message || "lark-cli command failed");
  }
}

function parseJson<T>(raw: string): T {
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new Error(`lark-cli 返回非 JSON 内容: ${raw.slice(0, 200)}`);
  }
}
