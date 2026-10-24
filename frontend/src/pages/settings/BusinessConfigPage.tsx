import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Input, Space, Statistic, Switch, Table, Tag, Typography, message } from "antd";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import {
  fetchDecodoConfig, fetchDecodoUsage, updateDecodoConfig,
  type DecodoConfig, type DecodoUsageDay,
} from "@/api/decodoApi";

const { Text } = Typography;

export default function BusinessConfigPage({page}:{page:NavigationPage}) {
  const [config,setConfig] = useState<DecodoConfig|null>(null);
  const [rows,setRows] = useState<DecodoUsageDay[]>([]);
  const [today,setToday] = useState("");
  const [usZip,setUsZip] = useState("10001");
  const [enabled,setEnabled] = useState(false);
  const [authorization,setAuthorization] = useState("");
  const [loading,setLoading] = useState(true);
  const [saving,setSaving] = useState(false);
  const [failed,setFailed] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const [c,u] = await Promise.all([fetchDecodoConfig(),fetchDecodoUsage(7)]);
      setConfig(c);setUsZip(c.us_zip);setEnabled(c.enabled);setRows(u.days);setToday(u.today);setFailed(false);
    } catch {
      setFailed(true);message.error("Decodo 配置或用量读取失败，请检查登录及权限");
    } finally { setLoading(false); }
  },[]);
  useEffect(() => {
    let active = true;

    void Promise.all([fetchDecodoConfig(), fetchDecodoUsage(7)])
      .then(([c, u]) => {
        if (!active) return;
        setConfig(c);
        setUsZip(c.us_zip);
        setEnabled(c.enabled);
        setRows(u.days);
        setToday(u.today);
        setFailed(false);
      })
      .catch(() => {
        if (!active) return;
        setFailed(true);
        message.error("Decodo 配置或用量读取失败，请检查登录及权限");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, []);
  const localTestMode=config?.mode === "local_test";
  const summary=useMemo(()=>rows.find(x=>x.date===today),[rows,today]);
  const save=async()=>{
    if(!/^\d{5}$/.test(usZip)){message.error("请输入 5 位美国邮编");return;}
    if(enabled && !config?.configured && !authorization.trim()){
      message.error("首次启用必须填写新生成的 Decodo Basic Authorization");return;
    }
    setSaving(true);
    try {
      await updateDecodoConfig({us_zip:usZip,enabled,...(authorization.trim()?{authorization:authorization.trim()}:{})});
      setAuthorization("");
      message.success("Decodo 业务配置已保存，密钥不会回显");
      await refresh();
    } catch {message.error("保存失败，请确认当前账号具有超级管理员权限和后端已配置加密密钥");}
    finally {setSaving(false);}
  };
  return <PageShell page={page}>
    <div style={{padding:16,maxWidth:1150,display:"grid",gap:16}}>
      <Card title="Decodo 爬虫接口配置" loading={loading}>
        {localTestMode?<Alert type="info" showIcon style={{marginBottom:12}} message="本地临时测试模式（SQLite）：默认美国邮编 10001。Authorization 仅从本地后端环境变量读取；此页面暂不修改密钥。调用统计保存在本机，不涉及服务器数据库。"/>:null}
        {failed?<Alert type="error" showIcon message="接口不可用：请确认服务已注册、数据库迁移已授权完成，并检查账号权限" style={{marginBottom:16}}/>:null}
        <Alert type="info" showIcon message="Authorization 在浏览器填写后仅发送到 SZZSBJ 后端，由后端加密存储并代为调用 Decodo。已有密钥不会回显。" style={{marginBottom:16}} />
        <div style={{display:"grid",gap:12,maxWidth:580}}>
          <div><Text strong>认证状态：</Text>{config?.configured?<Tag color="green">已配置</Tag>:<Tag color="orange">未配置</Tag>}</div>
          <div><Text strong>Authorization (Basic)</Text><Input.Password disabled={localTestMode} autoComplete="new-password" value={authorization} onChange={e=>setAuthorization(e.target.value)} placeholder="填写新密钥；留空表示沿用已保存密钥" /></div>
          <div><Text strong>美国 ZIP Code</Text><Input disabled={localTestMode} value={usZip} maxLength={5} onChange={e=>setUsZip(e.target.value.replace(/\D/g,""))} placeholder="10001" /></div>
          <Space><Text strong>启用 Decodo</Text><Switch disabled={localTestMode} checked={enabled} onChange={setEnabled}/><Text type="secondary">解析 JSON · 默认关闭 JS</Text></Space>
          <Space><Button type="primary" disabled={localTestMode||failed||loading} loading={saving} onClick={()=>void save()}>保存接口配置</Button><Button onClick={()=>{setLoading(true);void refresh();}} loading={loading}>刷新状态</Button></Space>
          <Text type="secondary">密钥修改仅限超级管理员；认证值不能通过 GET、日志或浏览器本地存储再次读取。</Text>
        </div>
      </Card>
      <Card title="Decodo 每日调用统计（美国东部时间）" extra={<Button onClick={()=>{setLoading(true);void refresh();}}>刷新</Button>}>
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(100px,1fr))",gap:12,marginBottom:16}}>
          <Statistic title="今日总请求" value={summary?.total??0}/>
          <Statistic title="Amazon" value={summary?.amazon_requests??0}/>
          <Statistic title="Walmart" value={summary?.walmart_requests??0}/>
          <Statistic title="今日失败" value={summary?.failed??0}/>
        </div>
        <Table<DecodoUsageDay> rowKey="date" size="small" loading={loading} pagination={false} dataSource={rows}
          columns={[{title:"美国日期",dataIndex:"date"},{title:"Amazon",dataIndex:"amazon_requests"},{title:"Walmart",dataIndex:"walmart_requests"},{title:"总请求",dataIndex:"total"},{title:"成功",dataIndex:"success"},{title:"失败",dataIndex:"failed"},{title:"处理中",dataIndex:"pending"}]}/>
        <Text type="secondary">按实际向 Decodo 发出的请求尝试计数，失败请求也计入；前端刷新、缓存读取和配置保存不计入。调用量不等于官方最终计费次数。</Text>
      </Card>
    </div>
  </PageShell>;
}
