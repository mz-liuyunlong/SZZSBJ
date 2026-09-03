/**
 * 会议分析 API 服务
 * 端口：3457
 *
 * 路由：
 *   GET  /api/meetings/list?days=400&profile=default
 *   POST /api/meetings/analyze  (multipart/form-data)
 *        body: minuteTokens (JSON string), prompt (string), files[] (binary)
 */

import "dotenv/config";
import * as http from "http";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";

const express = require("express");
const multer = require("multer");
const axios = require("axios/dist/node/axios.cjs");

import { searchMinutes, getMinuteNotes, MinuteSummary, MinuteNotes } from "./feishuMeetingReader";

const PORT = Number(process.env.MEETING_SERVER_PORT ?? 3457);
const AI_TIMEOUT_MS = 180_000;

const app = express();
app.use(express.json());

// multer: 内存存储，限 20MB
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 20 * 1024 * 1024 } });

// ── CORS（允许 Vite dev server）─────────────────────────
app.use((req: any, res: any, next: any) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

// ── GET /api/meetings/list ────────────────────────────
app.get("/api/meetings/list", (req: any, res: any) => {
  const days = Number(req.query.days ?? 400);
  const profile: string = req.query.profile ?? "default";

  try {
    // 服务器 profile 映射：default(JIM) → cli_aabe5b22cc385cdd，company2(掌上便捷) → cli_aaac1c28a4f81beb
    const profileMap: Record<string, string> = {
      'default': 'jim',
      'company2': 'company2',
    };
    const larkProfile = profileMap[profile] ?? 'jim';
    const minutes = searchMinutes(undefined, 30, days, larkProfile);
    res.json({ ok: true, data: minutes });
  } catch (e: any) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── POST /api/meetings/analyze ────────────────────────
app.post("/api/meetings/analyze", upload.array("files"), async (req: any, res: any) => {
  try {
    const minuteTokens: string[] = JSON.parse(req.body.minuteTokens ?? "[]");
    const prompt: string = req.body.prompt ?? "请总结这次会议的核心内容、决策和行动项。";
    const profile: string = req.body.profile ?? "default";
    const files: any[] = req.files ?? [];

    // 1. 拉取妙记内容
    let meetingContext = "";
    if (minuteTokens.length > 0) {
      try {
        const profileMap2: Record<string, string> = {
          'default': 'jim',
          'company2': 'company2',
        };
        const larkProfile = profileMap2[profile] ?? 'jim';
        const notes = getMinuteNotes(minuteTokens, larkProfile);
        for (const n of notes) {
          meetingContext += `\n\n## 妙记：${n.title}\n`;
          if (n.keywords.length > 0) meetingContext += `关键词：${n.keywords.join("、")}\n`;
          if (n.summary) meetingContext += `\nAI总结：\n${n.summary}\n`;
          if (n.transcriptFile && fs.existsSync(n.transcriptFile)) {
            const transcript = fs.readFileSync(n.transcriptFile, "utf8").slice(0, 6000);
            meetingContext += `\n逐字稿（节选）：\n${transcript}\n`;
          }
        }
      } catch (e: any) {
        meetingContext = `[读取妙记失败: ${e.message}]`;
      }
    }

    // 2. 构建 AI messages
    const systemMsg = {
      role: "system",
      content: "你是跨境电商运营团队的会议分析助手，擅长提炼会议重点、识别行动项和风险点，输出简洁、可操作的中文报告。",
    };

    const userContent: any[] = [];

    // 文字部分：提示词 + 会议内容
    userContent.push({
      type: "text",
      text: `${prompt}\n\n${meetingContext ? "以下是会议内容：" + meetingContext : "（无会议文字内容，请根据上传文件分析）"}`,
    });

    // 文件部分（多模态）
    for (const file of files) {
      const mime: string = file.mimetype ?? "application/octet-stream";
      if (mime.startsWith("image/")) {
        // 图片：base64 vision
        const b64 = file.buffer.toString("base64");
        userContent.push({
          type: "image_url",
          image_url: { url: `data:${mime};base64,${b64}` },
        });
      } else if (mime === "application/pdf") {
        // PDF：提取文本
        try {
          const pdfParse = require("pdf-parse");
          const parsed = await pdfParse(file.buffer);
          userContent.push({
            type: "text",
            text: `\n[附件 PDF: ${file.originalname}]\n${parsed.text.slice(0, 4000)}`,
          });
        } catch {
          userContent.push({ type: "text", text: `\n[附件 PDF: ${file.originalname}，解析失败]` });
        }
      } else if (
        mime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
        mime === "application/msword"
      ) {
        // DOCX：提取文本
        try {
          const mammoth = require("mammoth");
          const result = await mammoth.extractRawText({ buffer: file.buffer });
          userContent.push({
            type: "text",
            text: `\n[附件 Word: ${file.originalname}]\n${result.value.slice(0, 4000)}`,
          });
        } catch {
          userContent.push({ type: "text", text: `\n[附件 Word: ${file.originalname}，解析失败]` });
        }
      } else {
        // 其他文件：尝试当文本
        userContent.push({
          type: "text",
          text: `\n[附件: ${file.originalname}]\n${file.buffer.toString("utf8", 0, 2000)}`,
        });
      }
    }

    // 3. 调 AI
    const baseUrl = (process.env.AI_BASE_URL || "").replace(/\/$/, "");
    const model = process.env.AI_MODEL || "gpt-4o";
    const apiKey = process.env.AI_API_KEY || "";

    if (!baseUrl || !apiKey) {
      return res.status(500).json({ ok: false, error: "AI_BASE_URL 或 AI_API_KEY 未配置" });
    }

    const aiRes = await axios.post(
      `${baseUrl}/chat/completions`,
      { model, messages: [systemMsg, { role: "user", content: userContent }], temperature: 0.3 },
      { timeout: AI_TIMEOUT_MS, headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` } }
    );

    const output = aiRes.data?.choices?.[0]?.message?.content ?? "";
    res.json({ ok: true, result: output });
  } catch (e: any) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── 启动 ──────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n✅ 会议分析服务已启动: http://localhost:${PORT}`);
  console.log(`   GET  /api/meetings/list?days=400`);
  console.log(`   POST /api/meetings/analyze\n`);
});
