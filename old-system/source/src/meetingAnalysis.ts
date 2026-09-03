/**
 * 飞书会议内容读取 + AI 分析
 *
 * 用法：
 *   npm run meetings:analyze              # 默认最近 7 天
 *   npm run meetings:analyze -- --days 14 # 最近 14 天
 *   npm run meetings:analyze -- --days 7 --write-doc  # 分析结果写入飞书文档
 *
 * 前置：lark-cli 已完成 config init 和 auth login
 */

import "dotenv/config";
import * as fs from "fs";
import { searchMeetings, getMeetingNotes, searchMinutes, fetchDocument, getMinuteNotes, Meeting, MeetingNote, MinuteSummary } from "./feishuMeetingReader";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

const AI_TIMEOUT_MS = 120_000;

// ── CLI 参数解析 ──────────────────────────────────────────

function parseArgs() {
  const args = process.argv.slice(2);
  let days = 7;
  let writeDoc = false;
  let targetDocUrl = "";

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--days" && args[i + 1]) {
      days = parseInt(args[i + 1], 10);
      i++;
    }
    if (args[i] === "--write-doc") {
      writeDoc = true;
    }
    if (args[i] === "--doc" && args[i + 1]) {
      targetDocUrl = args[i + 1];
      writeDoc = true;
      i++;
    }
    if (args[i] === "--no-ai") {
      noAi = true;
    }
  }

  return { days, writeDoc, targetDocUrl, noAi };
}

let noAi = false;

// ── AI 调用 ───────────────────────────────────────────────

async function callAi(systemPrompt: string, userPrompt: string): Promise<string> {
  const baseUrl = (process.env.AI_BASE_URL || process.env.OPENCLAW_AI_BASE_URL || "").replace(/\/$/, "");
  const model = process.env.AI_MODEL || process.env.OPENCLAW_AI_MODEL || "gpt-4o-mini";
  const apiKey = process.env.AI_API_KEY || process.env.OPENCLAW_AI_API_KEY || "";

  if (!baseUrl || !apiKey) {
    throw new Error("AI_BASE_URL 或 AI_API_KEY 未配置，请检查 .env");
  }

  const response = await axios.post(
    `${baseUrl}/chat/completions`,
    {
      model,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
      temperature: 0.3,
    },
    {
      timeout: AI_TIMEOUT_MS,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
    }
  );

  return (response.data?.choices?.[0]?.message?.content ?? "").trim();
}

// ── 主流程 ────────────────────────────────────────────────

async function main() {
  const { days, writeDoc, targetDocUrl, noAi: noAiArg } = parseArgs();
  noAi = noAiArg;

  console.log(`\n🔍 读取最近 ${days} 天的飞书会议内容...\n`);

  // Step 1: 搜索已结束的视频会议
  let meetings: Meeting[] = [];
  try {
    meetings = searchMeetings(days);
    console.log(`✅ 找到 ${meetings.length} 场视频会议`);
  } catch (e: any) {
    console.warn(`⚠️  搜索视频会议失败: ${e.message}`);
    console.warn("   提示: 请先运行 lark-cli auth login --domain vc");
  }

  // Step 2: 获取会议纪要（AI 纪要 + 逐字稿）
  const noteMap = new Map<string, MeetingNote>();
  if (meetings.length > 0) {
    try {
      const notes = getMeetingNotes(meetings.map((m) => m.id));
      notes.forEach((n) => noteMap.set(n.meetingId, n));
      const withNotes = notes.filter((n) => n.noteDocToken || n.verbatimDocToken).length;
      console.log(`✅ ${withNotes}/${meetings.length} 场会议有纪要文档`);
    } catch (e: any) {
      console.warn(`⚠️  获取会议纪要失败: ${e.message}`);
    }
  }

  // Step 3: 搜索妙记列表（补充录制产物）
  let minuteItems: string[] = [];
  let minuteList: MinuteSummary[] = [];
  try {
    minuteList = searchMinutes(undefined, 10, days);
    minuteItems = minuteList.map(
      (m) => `• [${m.title}](${m.url})  owner: ${m.owner}  ${m.createTime}`
    );
    console.log(`✅ 找到 ${minuteList.length} 条妙记`);
  } catch (e: any) {
    console.warn(`⚠️  搜索妙记失败: ${e.message}`);
    console.warn("   提示: 请先运行 lark-cli auth login --scope minutes:minutes.search:read");
  }

  // Step 4: 读取会议纪要正文（逐字稿优先；--no-ai 时读全部，否则最多 5 场）
  const meetingContents: string[] = [];
  const topMeetings = noAi ? meetings : meetings.slice(0, 5);

  for (const meeting of topMeetings) {
    const note = noteMap.get(meeting.id);
    if (!note) continue;

    const docToken = note.verbatimDocToken || note.noteDocToken;
    if (!docToken) {
      meetingContents.push(`【${meeting.topic}】${meeting.startTime} — 无纪要文档`);
      continue;
    }

    try {
      const content = fetchDocument(docToken);
      const preview = content.slice(0, 2000); // 控制长度
      meetingContents.push(
        `【${meeting.topic}】${meeting.startTime}（${meeting.duration}分钟，${meeting.participantCount}人）\n${preview}`
      );
    } catch (e: any) {
      meetingContents.push(`【${meeting.topic}】读取文档失败: ${e.message}`);
    }
  }

  // Step 5: 汇总数据，准备 AI 分析
  if (meetings.length === 0 && minuteItems.length === 0) {
    console.log("\n📭 没有找到任何会议内容，请检查权限或时间范围。");
    return;
  }

  const now = new Date().toLocaleDateString("zh-CN");

  // --no-ai：直接输出原始内容，不调 AI
  if (noAi) {
    console.log("\n" + "=".repeat(60));
    console.log(`📋 飞书会议内容读取结果（${now}，最近 ${days} 天）\n`);
    if (meetings.length > 0) {
      console.log(`## 视频会议（${meetings.length} 场）`);
      meetings.forEach((m, i) =>
        console.log(`${i + 1}. ${m.topic} | ${m.startTime} | ${m.duration}分钟 | ${m.participantCount}人`)
      );
      console.log();
    }
    if (minuteItems.length > 0) {
      console.log(`## 妙记列表（${minuteItems.length} 条）`);
      minuteItems.forEach((s) => console.log(s));
      console.log();
    }
    if (meetingContents.length > 0) {
      console.log(`## VC 会议内容`);
      meetingContents.forEach((c) => console.log(c + "\n---"));
      console.log();
    }

    // 读取妙记正文内容（AI总结 + 本地逐字稿）
    if (minuteList.length > 0) {
      console.log(`## 妙记正文内容`);
      try {
        const minuteNotes = getMinuteNotes(minuteList.map((m) => m.token));
        for (const mn of minuteNotes) {
          const meta = minuteList.find((m) => m.token === mn.minuteToken);
          console.log(`\n${"─".repeat(50)}`);
          console.log(`【${mn.title}】`);
          if (meta?.url) console.log(`链接: ${meta.url}`);
          if (mn.keywords.length > 0) console.log(`关键词: ${mn.keywords.join("、")}`);
          console.log();
          if (mn.summary) {
            console.log(`### AI总结`);
            console.log(mn.summary);
          }
          if (mn.transcriptFile && fs.existsSync(mn.transcriptFile)) {
            console.log(`\n### 逐字稿`);
            const transcript = fs.readFileSync(mn.transcriptFile, "utf8");
            console.log(transcript.slice(0, 5000)); // 超长截断
          } else if (mn.transcriptFile) {
            console.log(`\n逐字稿文件: ${mn.transcriptFile}（本地不存在，可能需重新运行）`);
          }
        }
      } catch (e: any) {
        console.warn(`⚠️  读取妙记内容失败: ${e.message}`);
        console.warn("   提示: 请先运行 lark-cli auth login --domain vc");
      }
    }

    console.log("\n" + "=".repeat(60));
    return;
  }

  const userPrompt = buildPrompt({ days, now, meetings, meetingContents, minuteItems });

  console.log("\n🤖 AI 分析中...\n");

  let analysis = "";
  try {
    analysis = await callAi(SYSTEM_PROMPT, userPrompt);
  } catch (e: any) {
    console.error(`❌ AI 分析失败: ${e.message}`);
    analysis = buildRawSummary({ meetings, minuteItems });
  }

  console.log("=".repeat(60));
  console.log(analysis);
  console.log("=".repeat(60));

  // Step 6: 可选——写回飞书文档
  if (writeDoc) {
    await writeToFeishuDoc(analysis, targetDocUrl, days);
  }
}

// ── Prompt 构建 ───────────────────────────────────────────

const SYSTEM_PROMPT = `你是跨境电商运营团队的会议分析助手。
职责：
1. 提炼本周/本阶段会议的核心决策和行动项
2. 识别跨会议的共同议题和潜在风险
3. 列出所有明确的待办事项（含负责人、截止日期）
4. 输出简洁、可直接发给老板的中文报告

输出格式：
## 会议概览（X场，总时长X小时）
## 核心决策
## 行动项清单（含负责人）
## 风险与关注点
## 跟进建议`;

function buildPrompt(opts: {
  days: number;
  now: string;
  meetings: Meeting[];
  meetingContents: string[];
  minuteItems: string[];
}): string {
  const { days, now, meetings, meetingContents, minuteItems } = opts;

  const meetingList = meetings
    .map(
      (m, i) =>
        `${i + 1}. ${m.topic} | ${m.startTime} | ${m.duration}分钟 | ${m.participantCount}人 | 组织者:${m.organizer}`
    )
    .join("\n");

  return (
    `分析时间：${now}，覆盖最近 ${days} 天\n\n` +
    `## 视频会议列表（共 ${meetings.length} 场）\n${meetingList || "无"}\n\n` +
    `## 会议纪要内容（读取了前 ${meetingContents.length} 场）\n${meetingContents.join("\n\n---\n\n") || "无"}\n\n` +
    `## 妙记列表（最近 10 条）\n${minuteItems.join("\n") || "无"}\n\n` +
    `请根据以上内容生成会议分析报告。`
  );
}

function buildRawSummary(opts: { meetings: Meeting[]; minuteItems: string[] }): string {
  const { meetings, minuteItems } = opts;
  const lines = [
    `## 会议列表（${meetings.length} 场）`,
    ...meetings.map((m) => `- ${m.topic} ${m.startTime} ${m.duration}分钟`),
    "",
    `## 妙记列表`,
    ...minuteItems,
  ];
  return lines.join("\n");
}

// ── 写回飞书文档（可选）────────────────────────────────────

async function writeToFeishuDoc(content: string, docUrl: string, days: number) {
  const { execFileSync } = await import("child_process");

  const title = `会议纪要汇总（最近 ${days} 天）`;
  const markdownContent = `# ${title}\n\n${content}`;

  const args = docUrl
    ? [
        "docs",
        "+update",
        "--api-version",
        "v2",
        "--doc",
        docUrl,
        "--command",
        "append",
        "--doc-format",
        "markdown",
        "--content",
        markdownContent,
      ]
    : [
        "docs",
        "+create",
        "--api-version",
        "v2",
        "--doc-format",
        "markdown",
        "--content",
        markdownContent,
      ];

  try {
    const result = execFileSync("./scripts/lark-cli", args, {
      cwd: process.cwd(),
      encoding: "utf8",
      maxBuffer: 5 * 1024 * 1024,
    });
    console.log("\n✅ 已写入飞书文档");
    console.log(result);
  } catch (e: any) {
    const msg = e.stderr?.toString() || e.message;
    console.error(`❌ 写入飞书文档失败: ${msg}`);
  }
}

// ── 入口 ──────────────────────────────────────────────────

main().catch((e) => {
  console.error("❌ 执行失败:", e.message);
  process.exit(1);
});
