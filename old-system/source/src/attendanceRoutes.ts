/**
 * attendanceRoutes.ts — AI人力·考勤 只读接口（隔离新模块，2026-07-29）
 * 挂载：/api/hr/attendance
 * 访问控制：requireAuth + requirePermission('hr_attendance')（超管绕过；人事黄少如授权）。
 * 只读 FACT(fact_attendance_daily)，禁直查 RAW。
 *   GET /months                     可选月份(YYYY-MM)
 *   GET /monthly?month=YYYY-MM      月度核算(按人汇总 + KPI)
 */
import { Router, Response } from "express";
import * as mysql from "mysql2/promise";
import { requireAuth, requirePermission, AuthedRequest } from "./authMiddleware";

const router = Router();
function dbConfig(): mysql.ConnectionOptions {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  };
}

// 全部接口：先登录，再校验 hr_attendance 权限（超管绕过）
router.use(requireAuth, requirePermission("hr_attendance"));

router.get("/months", async (_req: AuthedRequest, res: Response): Promise<void> => {
  const db = await mysql.createConnection(dbConfig());
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT DATE_FORMAT(stat_date,'%Y-%m') AS ym, COUNT(*) AS days FROM fact_attendance_daily GROUP BY ym ORDER BY ym DESC LIMIT 24",
    );
    res.json({ months: rows.map((r) => String(r.ym)) });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    await db.end().catch(() => undefined);
  }
});

router.get("/monthly", async (req: AuthedRequest, res: Response): Promise<void> => {
  const month = String(req.query.month ?? "").trim();
  if (!/^\d{4}-\d{2}$/.test(month)) { res.status(400).json({ error: "month 格式应为 YYYY-MM" }); return; }
  const start = month + "-01";
  const end = month + "-31";
  const db = await mysql.createConnection(dbConfig());
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT f.open_id, f.name, " +
      "SUM(f.is_scheduled=1) AS scheduled, " +
      "SUM(f.is_scheduled=1 AND (f.check_in_time IS NOT NULL OR f.check_out_time IS NOT NULL) AND NOT (f.day_status='缺卡' AND a.ack_status='expired')) AS present, " +
      "SUM(f.day_status='迟到') AS late, SUM(f.day_status='早退') AS early, " +
      "SUM(f.day_status='缺卡' AND (a.ack_status IS NULL OR a.ack_status<>'expired')) AS lack, " +
      "SUM(f.day_status='旷工') + SUM(f.day_status='缺卡' AND a.ack_status='expired') AS absent, " +
      "ROUND(SUM(CASE WHEN f.leave_type LIKE '%事假%' THEN f.leave_hours ELSE 0 END),1) AS personal_leave_h, " +
      "ROUND(SUM(CASE WHEN f.leave_type LIKE '%病假%' THEN f.leave_hours ELSE 0 END),1) AS sick_leave_h, " +
      "ROUND(SUM(CASE WHEN f.leave_type LIKE '%年假%' THEN f.leave_hours ELSE 0 END),1) AS annual_leave_h, " +
      "ROUND(SUM(f.leave_hours),1) AS leave_h, ROUND(SUM(f.out_hours),1) AS out_h, " +
      "ROUND(SUM(f.overtime_minutes)/60,1) AS overtime_h " +
      "FROM fact_attendance_daily f " +
      "LEFT JOIN event_attendance_lack_alert a ON a.stat_date=f.stat_date AND a.open_id=f.open_id " +
      "WHERE f.stat_date BETWEEN ? AND ? GROUP BY f.open_id, f.name ORDER BY f.name",
      [start, end],
    );
    const items = rows.map((r) => {
      const scheduled = Number(r.scheduled ?? 0);
      const present = Number(r.present ?? 0);
      return {
        open_id: String(r.open_id ?? ""), name: String(r.name ?? ""),
        scheduled, present, late: Number(r.late ?? 0), early: Number(r.early ?? 0),
        lack: Number(r.lack ?? 0), absent: Number(r.absent ?? 0),
        personal_leave_h: Number(r.personal_leave_h ?? 0), sick_leave_h: Number(r.sick_leave_h ?? 0),
        annual_leave_h: Number(r.annual_leave_h ?? 0), leave_h: Number(r.leave_h ?? 0),
        out_h: Number(r.out_h ?? 0), overtime_h: Number(r.overtime_h ?? 0),
        rate: scheduled ? Math.round((present / scheduled) * 1000) / 10 : 0,
      };
    });
    const kpi = {
      people: items.length,
      full_attendance: items.filter((x) => x.scheduled > 0 && x.present === x.scheduled && x.late === 0 && x.lack === 0 && x.absent === 0).length,
      abnormal: items.filter((x) => x.late > 0 || x.early > 0 || x.lack > 0 || x.absent > 0).length,
      avg_rate: items.length ? Math.round((items.reduce((s, x) => s + x.rate, 0) / items.length) * 10) / 10 : 0,
      late_total: items.reduce((s, x) => s + x.late, 0),
      absent_total: items.reduce((s, x) => s + x.absent, 0),
    };
    const [syncRows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT DATE_FORMAT(MAX(updated_at),'%Y-%m-%d %H:%i') AS latest FROM fact_attendance_daily WHERE stat_date BETWEEN ? AND ?",
      [start, end],
    );
    const latest_sync_time = String((syncRows[0] && syncRows[0].latest) || "");
    res.json({ month, kpi, items, latest_sync_time });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    await db.end().catch(() => undefined);
  }
});

export default router;
