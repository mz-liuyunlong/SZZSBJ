/**
 * RosterAdmin.tsx — 用户管理（成员·角色·注册；原"花名册"，2026-08-04 改名+UI_STANDARDS归一）
 * 接后端：GET /api/roster/users, POST /api/roster/set-roles（门禁 超管/人事）。
 * v3：LxToolbar 标准工具条(共N行·同步·页码+刷新/帮助)、帮助壳内(#/help?page=role_guide)、列宽可拖§5。
 * 新用户由 02:35 sync-app-users 自动开户并默认角色=运营组员。
 */
import React, { useCallback, useEffect, useState } from "react";
import { lxTB, IconRefresh, IconHelp } from "./LxToolbar";

interface RUser {
  id: number; username: string; display_name: string; team_name: string;
  is_active: boolean; is_superadmin: boolean; registered: boolean; roles: string[];
}
const C = {
  bg: "#f6f8fc", card: "#fff", txt: "#202124", txt2: "#5f6368", line: "#dadce0",
  blue: "#1a73e8", green: "#188038", red: "#d93025", redSoft: "#fce8e6",
  purple: "#8430ce", purpleSoft: "#f3e8fd", amber: "#b06000", amberSoft: "#fef7e0",
  greenSoft: "#e6f4ea", blueSoft: "#e8f0fe", teal: "#137a6d", tealSoft: "#d7f2ee",
};
const ROLE_COLOR: Record<string, { c: string; s: string }> = {
  "超管": { c: C.purple, s: C.purpleSoft }, "人事": { c: C.green, s: C.greenSoft },
  "财务": { c: C.teal, s: C.tealSoft }, "中台": { c: C.blue, s: C.blueSoft },
  "运营主管": { c: C.amber, s: C.amberSoft }, "运营组员": { c: "#5f6368", s: "#eceff1" },
};
const rc = (r: string) => ROLE_COLOR[r] || { c: "#9aa0a6", s: "#f1f3f4" };

export default function RosterAdmin({ onNavigate }: { onNavigate?: (p: string) => void } = {}) {
  const [users, setUsers] = useState<RUser[]>([]);
  const [allowed, setAllowed] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [dirty, setDirty] = useState<Record<number, boolean>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [frole, setFrole] = useState("");
  const [freg, setFreg] = useState(""); // ""|reg|unreg
  const [syncTime, setSyncTime] = useState("");
  const [colW, setColW] = useState<Record<string, number>>({});

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const r = await fetch("/api/roster/users");
      if (r.status === 403) { setErr("你没有权限访问用户管理（仅 超管 / 人事 可进）"); setUsers([]); return; }
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "加载失败");
      setUsers(j.users || []); setAllowed(j.allowed_roles || []); setDirty({}); setSyncTime(String(j.latest_sync_time || ""));
    } catch (e: any) { setErr(e?.message || String(e)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const setRoles = (id: number, roles: string[]) => {
    setUsers((us) => us.map((u) => (u.id === id ? { ...u, roles } : u)));
    setDirty((d) => ({ ...d, [id]: true }));
  };
  const addRole = (u: RUser, role: string) => { if (role && !u.roles.includes(role)) setRoles(u.id, [...u.roles, role]); };
  const delRole = (u: RUser, role: string) => setRoles(u.id, u.roles.filter((r) => r !== role));

  const save = async (u: RUser) => {
    setSavingId(u.id);
    try {
      const r = await fetch("/api/roster/set-roles", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: u.id, roles: u.roles }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "保存失败");
      setDirty((d) => { const n = { ...d }; delete n[u.id]; return n; });
      setSavedId(u.id); setTimeout(() => setSavedId((s) => (s === u.id ? null : s)), 1500);
    } catch (e: any) { alert("保存失败：" + (e?.message || e)); } finally { setSavingId(null); }
  };

  const chip = (role: string, onDel?: () => void) => {
    const st = rc(role);
    return (
      <span key={role} style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "2px 9px", borderRadius: 999, fontSize: 12, fontWeight: 600, color: st.c, background: st.s, whiteSpace: "nowrap" }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: st.c }} />{role}
        {onDel && <span onClick={onDel} style={{ cursor: "pointer", opacity: 0.55, fontWeight: 700, marginLeft: 2 }}>×</span>}
      </span>
    );
  };

  const shown = users
    .filter((u) => (!q || u.display_name.includes(q) || (u.username || "").includes(q))
      && (!frole || u.roles.includes(frole))
      && (!freg || (freg === "reg" ? u.registered : !u.registered)))
    .sort((a, b) => Number(b.registered) - Number(a.registered)); // 已注册排前（同注册状态保持后端顺序，JS稳定排序）

  const COLS: { key: string; label: string; w: number }[] = [
    { key: "name", label: "姓名", w: 140 },
    { key: "status", label: "账号状态", w: 100 },
    { key: "reg", label: "是否已注册", w: 110 },
    { key: "roles", label: "角色（点 × 去除，点 + 添加；一人可多角色）", w: 0 },
    { key: "op", label: "操作", w: 120 },
  ];
  const cw = (k: string, def: number) => colW[k] ?? def;
  function startResize(k: string, def: number, e: React.MouseEvent) {
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX; const startW = colW[k] || def || 200;
    const move = (ev: MouseEvent) => setColW((pv) => ({ ...pv, [k]: Math.max(70, startW + (ev.clientX - startX)) }));
    const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  }
  function openHelp() { if (onNavigate) onNavigate("help"); window.location.hash = "#/help?page=role_guide"; }

  const regCount = users.filter((u) => u.registered).length;
  const th: React.CSSProperties = { textAlign: "left", padding: "10px 14px", fontSize: 12, color: C.txt2, fontWeight: 600, borderBottom: `1px solid ${C.line}`, whiteSpace: "nowrap", background: "#fafbfd" };
  const td: React.CSSProperties = { padding: "11px 14px", fontSize: 13, borderBottom: "1px solid #f1f3f4", verticalAlign: "middle" };

  return (
    <div style={{ height: "100%", overflow: "auto", background: C.bg, padding: 20, boxSizing: "border-box", fontFamily: "-apple-system,'PingFang SC','Microsoft YaHei',sans-serif", color: C.txt }}>
      <style>{`
        .ru-grip{position:absolute;right:0;top:22%;height:56%;width:2px;background:#dadce0;border-radius:2px;cursor:col-resize;}
        th:hover .ru-grip{background:#1a73e8;width:3px;top:0;height:100%;}
        .ru-ib:hover{background:#f1f3f4;color:#1a73e8;}
      `}</style>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>👥 用户管理</div>
        <span style={{ color: C.txt2, fontSize: 12 }}>成员 · 角色 · 注册 ｜ 共 {users.length} 人 · 已注册 {regCount}。新员工每日 02:35 自动开户（默认角色：运营组员），角色说明见帮助。</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索姓名…" style={{ border: `1px solid ${C.line}`, borderRadius: 8, padding: "7px 11px", fontSize: 13, width: 150 }} />
        <select value={freg} onChange={(e) => setFreg(e.target.value)} style={{ border: `1px solid ${C.line}`, borderRadius: 8, padding: "7px 10px", fontSize: 13, background: "#fff" }}>
          <option value="">全部注册状态</option>
          <option value="reg">已注册</option>
          <option value="unreg">未注册</option>
        </select>
        <select value={frole} onChange={(e) => setFrole(e.target.value)} style={{ border: `1px solid ${C.line}`, borderRadius: 8, padding: "7px 10px", fontSize: 13, background: "#fff" }}>
          <option value="">全部角色</option>
          {(allowed.length ? allowed : Object.keys(ROLE_COLOR)).map((r) => <option key={r}>{r}</option>)}
        </select>
        {(q || frole || freg) && <button onClick={() => { setQ(""); setFrole(""); setFreg(""); }} style={{ border: `1px solid ${C.line}`, background: "#fff", color: C.txt2, padding: "7px 12px", borderRadius: 8, fontSize: 13, cursor: "pointer" }}>重置</button>}
        <div style={{ flex: 1 }} />
        <span style={{ color: "#80868b", fontSize: 12 }}>共 <b style={{ color: C.txt2 }}>{shown.length}</b> 行 · 同步 <b style={{ color: C.txt2 }}>{syncTime || "—"}</b> · 第 <b style={{ color: C.txt2 }}>1/1</b> 页</span>
        <button className="ru-ib" onClick={load} title="刷新" style={lxTB.iconBtn}><IconRefresh /></button>
        <button className="ru-ib" onClick={openHelp} title="帮助（壳内直达角色权限说明）" style={lxTB.iconBtn}><IconHelp /></button>
      </div>

      {err && <div style={{ padding: 16, background: C.redSoft, color: C.red, borderRadius: 10, fontSize: 13, marginBottom: 12 }}>{err}</div>}

      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, overflow: "hidden" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            {COLS.map((c) => (
              <th key={c.key} style={{ ...th, position: "relative", ...(c.w ? { width: cw(c.key, c.w) } : (colW[c.key] ? { width: colW[c.key] } : {})) }}>
                {c.label}
                <span className="ru-grip" onMouseDown={(e) => startResize(c.key, c.w || 300, e)} />
              </th>
            ))}
          </tr></thead>
          <tbody>
            {loading && <tr><td style={{ ...td, textAlign: "center", color: C.txt2 }} colSpan={5}>加载中…</td></tr>}
            {!loading && shown.length === 0 && !err && <tr><td style={{ ...td, textAlign: "center", color: C.txt2 }} colSpan={5}>无匹配成员</td></tr>}
            {!loading && shown.map((u) => {
              const avail = (allowed.length ? allowed : Object.keys(ROLE_COLOR)).filter((r) => !u.roles.includes(r));
              return (
                <tr key={u.id}>
                  <td style={{ ...td, fontWeight: 600 }}>{u.display_name}</td>
                  <td style={td}>{u.is_active ? <span style={{ color: C.green }}>● 在职</span> : <span style={{ color: C.red }}>● 离职停用</span>}</td>
                  <td style={td}>
                    {u.registered
                      ? <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: C.green, fontSize: 12.5, fontWeight: 600 }}>✓ 已注册</span>
                      : <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: C.amber, background: C.amberSoft, padding: "2px 9px", borderRadius: 999, fontSize: 12, fontWeight: 600 }}>未注册</span>}
                  </td>
                  <td style={td}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      {u.roles.length ? u.roles.map((r) => chip(r, () => delRole(u, r))) : <span style={{ color: C.txt2, fontSize: 12 }}>未分配角色</span>}
                      {avail.length > 0 && (
                        <select value="" onChange={(e) => { addRole(u, e.target.value); e.target.value = ""; }}
                          style={{ border: `1px dashed ${C.line}`, borderRadius: 999, padding: "3px 9px", fontSize: 12, background: "#fff", color: C.txt2, cursor: "pointer" }}>
                          <option value="">+ 添加角色</option>
                          {avail.map((r) => <option key={r}>{r}</option>)}
                        </select>
                      )}
                    </div>
                  </td>
                  <td style={td}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <button onClick={() => save(u)} disabled={savingId === u.id || !dirty[u.id]}
                        style={{ border: `1px solid ${C.line}`, background: "#fff", color: dirty[u.id] ? C.blue : "#c0c4c9", borderRadius: 7, padding: "5px 12px", fontSize: 12, cursor: dirty[u.id] ? "pointer" : "default", fontWeight: 600 }}>
                        {savingId === u.id ? "保存中…" : "保存"}
                      </button>
                      {savedId === u.id && <span style={{ color: C.green, fontSize: 12, fontWeight: 600 }}>✓ 已保存</span>}
                      {dirty[u.id] && savedId !== u.id && <span style={{ color: C.txt2, fontSize: 12 }}>未保存</span>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 12, color: C.txt2, fontSize: 12, lineHeight: 1.7 }}>
        「未注册」= 账号已自动建好但本人尚未通过飞书首登设置密码，无法登录；已注册的排在前面。新员工入职后次日 02:35 自动开户并赋默认角色「运营组员」。角色权限说明见「帮助中心 · 角色权限说明」。
      </div>
    </div>
  );
}
