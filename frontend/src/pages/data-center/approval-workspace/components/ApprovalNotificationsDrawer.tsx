import { Button, Drawer, Empty, List, Space, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";
import {
 fetchApprovalNotifications, markApprovalNotificationRead,
 type ApprovalNotification,
} from "../approvalWorkflowApi";

interface Props { open:boolean; onClose():void; onRefresh():void }
export default function ApprovalNotificationsDrawer({ open,onClose,onRefresh }:Props) {
 const [items,setItems]=useState<ApprovalNotification[]>([]);
 const [api,holder]=message.useMessage();
 const load=()=>void fetchApprovalNotifications().then(setItems)
  .catch(()=>void api.error("提醒读取失败"));
 useEffect(()=>{if(open)load();},[open]);
 return <>
  {holder}
  <Drawer open={open} onClose={onClose} width={520} title="审批提醒"
   extra={<Button size="small" onClick={load}>刷新</Button>}>
   <List dataSource={items} locale={{emptyText:<Empty description="暂无提醒"/>}}
    renderItem={(item)=>(
     <List.Item actions={[
      <Button key="read" size="small" disabled={item.status==="read"}
       onClick={()=>void markApprovalNotificationRead(item.id).then(()=>{load();onRefresh();})
        .catch(()=>void api.error("标记失败"))}>
       {item.status==="read"?"已读":"标记已读"}
      </Button>,
     ]}>
      <List.Item.Meta
       title={<Space>
        <Tag color={item.status==="unread"?"blue":"default"}>{item.status==="unread"?"未读":"已读"}</Tag>
        <span>{item.event_key.startsWith("overdue")?"审批超时提醒":"审批状态更新"}</span>
       </Space>}
       description={<Typography.Text type="secondary">
        审批单：{item.approval_id} · {new Date(item.created_at).toLocaleString("zh-CN")}
       </Typography.Text>}
      />
     </List.Item>
    )}/>
  </Drawer>
 </>;
}
