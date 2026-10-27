/** V7 conversation workspace in the existing SZZSBJ MainLayout. */
import {
  ArrowUpOutlined, BarChartOutlined, DeleteOutlined, EditOutlined, FileImageOutlined,
  FileOutlined, MenuFoldOutlined, MenuUnfoldOutlined, MoreOutlined, PaperClipOutlined,
  PlusOutlined, RobotOutlined, SearchOutlined, UploadOutlined,
} from '@ant-design/icons';
import { Button, Dropdown, Input, Modal, Tooltip, message as antMessage } from 'antd';
import {
  useEffect, useMemo, useRef, useState,
  type ChangeEvent, type ClipboardEvent, type DragEvent, type KeyboardEvent,
} from 'react';
import PageShell from '@/components/page/PageShell';
import { backendRequest } from '@/api/backendApi';
import type { NavigationPage } from '@/config/navigation';
import './AIAssistantPage.css';

type Attachment = { id: string; name: string; size: number; image: boolean };
type ChatMessage = { id: string; role: 'user' | 'assistant'; text: string; files?: Attachment[]; analysis?: boolean };
type Thread = { id: string; title: string; note: string; draft: string; updatedAt: number; messages: ChatMessage[] };
type UploadItem = Attachment & { file: File; url?: string };
type Props = { page: NavigationPage; preferenceScope?: string };
const MAX_FILES = 10;
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_TOTAL_BYTES = 6 * 1024 * 1024;
const EXT = new Set('docx xlsx csv txt md json pptx xml yaml yml html sql py js ts'.split(' '));
const QUESTIONS = [
  ['产品利润分析', '分析一个 SKU 最近 7 天的利润变化'],
  ['异常产品定位', '哪些 SKU 利润下降最严重？'],
  ['整体经营复盘', '最近 7 天整体经营利润如何变化？'],
  ['广告投入分析', '哪些产品广告花费高但订单少？'],
] as const;
function id() {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2);
}
function fresh(): Thread { return { id: id(), title: '新聊天', note: '', draft: '', updatedAt: Date.now(), messages: [] }; }
function key(scope: string) { return 'szzsbj:ai-v7:' + encodeURIComponent(scope); }
function serverChatsKey(scope: string) { return 'szzsbj:ai-v7-server-chats:' + encodeURIComponent(scope); }
function restoreServerChats(scope: string): Record<string,string> {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(serverChatsKey(scope)) || 'null');
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return Object.fromEntries(Object.entries(value).filter((entry): entry is [string,string] => typeof entry[1] === 'string'));
    }
  } catch { /* local storage can be unavailable */ }
  return {};
}
function restore(scope: string): Thread[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key(scope)) || 'null');
    if (Array.isArray(value)) {
      const items = value.filter((v): v is Thread => Boolean(v) && typeof v === 'object' &&
        typeof v.id === 'string' && typeof v.title === 'string' && typeof v.note === 'string' &&
        typeof v.draft === 'string' && typeof v.updatedAt === 'number' && Array.isArray(v.messages));
      if (items.length) return items;
    }
  } catch { /* local storage can be unavailable */ }
  return [fresh()];
}
function sizeText(n: number) { return n < 1024 ? n + ' B' : n < 1048576 ? Math.ceil(n / 1024) + ' KB' : (n / 1048576).toFixed(1) + ' MB'; }
function FileCard({ file, url, remove }: { file: Attachment; url?: string; remove?: () => void }) {
  return <div className="ai7-file">{file.image && url ? <img src={url} alt={file.name} /> : file.image ? <FileImageOutlined /> : <FileOutlined />}
    <div className="ai7-file-name"><strong title={file.name}>{file.name}</strong><small>{sizeText(file.size)}</small></div>
    {remove && <button type="button" aria-label={'移除 ' + file.name} onClick={remove}>×</button>}
  </div>;
}
function AIAssistantPage({ page, preferenceScope='anonymous' }: Props) {
  const [msgApi, msgContext] = antMessage.useMessage();
  const [threads, setThreads] = useState<Thread[]>(() => restore(preferenceScope));
  const [activeId, setActiveId] = useState(() => threads[threads.length-1].id);
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [editing, setEditing] = useState<string|null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editNote, setEditNote] = useState('');
  const [deleting, setDeleting] = useState<string|null>(null);
  const [pending, setPending] = useState<Record<string,UploadItem[]>>({});
  const [imageUrls,setImageUrls] = useState<Record<string,string>>({});
  const [attachmentMenu,setAttachmentMenu] = useState(false);
  const [dragging,setDragging] = useState(false);
  const [sending,setSending] = useState(false);
  const [serverChats,setServerChats] = useState<Record<string,string>>(() => restoreServerChats(preferenceScope));
  const images = useRef<HTMLInputElement>(null);
  const files = useRef<HTMLInputElement>(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const urls = useRef(new Map<string,string>());
  const chat = threads.find(t => t.id === activeId) ?? threads[0];
  const uploads = pending[chat.id] ?? [];
  const visible = useMemo(() => [...threads].sort((a,b) => b.updatedAt-a.updatedAt).filter(t => (t.title+' '+t.note).toLowerCase().includes(search.toLowerCase())),[threads,search]);
  useEffect(() => { try { localStorage.setItem(key(preferenceScope),JSON.stringify(threads)); } catch { /* optional persistence */ } },[preferenceScope,threads]);
  useEffect(() => { try { localStorage.setItem(serverChatsKey(preferenceScope),JSON.stringify(serverChats)); } catch { /* optional persistence */ } },[preferenceScope,serverChats]);
  useEffect(() => { const map=urls.current;return () => { map.forEach(value => URL.revokeObjectURL(value)); }; },[]);
  useEffect(() => { if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight; },[activeId,chat.messages.length]);
  const changeChat = (identifier:string, patch:Partial<Thread>) => setThreads(before => before.map(t => t.id===identifier ? {...t,...patch,updatedAt:Date.now()} : t));
  const newChat = () => {
    if (!chat.messages.length && !chat.draft.trim() && !uploads.length) { editor.current?.focus();return; }
    const t=fresh();setThreads(before=>[...before,t]);setActiveId(t.id);setMobileOpen(false);setSearch('');
    requestAnimationFrame(()=>editor.current?.focus());
  };
  const cleanupFile = (identifier:string) => {
    const url=urls.current.get(identifier);if(url){URL.revokeObjectURL(url);urls.current.delete(identifier);}
    setImageUrls(before=>{const next={...before};delete next[identifier];return next;});
  };
  const removeFile = (identifier:string) => {cleanupFile(identifier);setPending(before=>({...before,[chat.id]:(before[chat.id]??[]).filter(f=>f.id!==identifier)}));};
  const acceptFiles = (incoming:FileList|File[]) => {
    const next=[...uploads];let rejected=0;
    for (const file of Array.from(incoming)) {
      const ext=file.name.split('.').pop()?.toLowerCase()??'';
      if (next.length>=MAX_FILES || file.size>MAX_BYTES || !EXT.has(ext)) {rejected++;continue;}
      const image=/^(png|jpg|jpeg|webp|gif|bmp|heic|heif)$/.test(ext);
      const identifier=id();
      const url=image && typeof URL.createObjectURL==='function'?URL.createObjectURL(file):undefined;
      if(url){urls.current.set(identifier,url);setImageUrls(before=>({...before,[identifier]:url}));}
      next.push({id:identifier,name:file.name,size:file.size,image,file,url});
    }
    setPending(before=>({...before,[chat.id]:next}));
    if(rejected)void msgApi.warning(rejected+' 个附件不符合格式、2MB 或 10 个的限制；当前支持文本、CSV、JSON 和 Office 文件，不支持图片或 PDF 解析');
    setAttachmentMenu(false);
  };
  const send = async (preset?:string) => {
    const text=(preset??chat.draft).trim() || (uploads.length ? '请分析附件内容并总结重点' : '');
    if(!text && !uploads.length)return;
    if(sending)return;
    if(uploads.some(u=>u.size>MAX_BYTES)
      || uploads.reduce((total,u)=>total+u.size,0)>MAX_TOTAL_BYTES) {
      void msgApi.warning('附件最多 10 个，单个 2MB、总计 6MB；请移除超限附件');
      return;
    }
    let attachments:{name:string;content_base64:string}[];
    try {
      attachments=await Promise.all(uploads.map(async u=>{
        const bytes=new Uint8Array(await u.file.arrayBuffer());
        let binary='';
        for(let i=0;i<bytes.length;i+=32768){
          binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
        }
        return {name:u.name,content_base64:btoa(binary)};
      }));
    } catch {
      void msgApi.error('附件读取失败，请检查文件是否可访问');
      return;
    }
    const target=chat.id;
    setSending(true);
    setThreads(before=>before.map(t=>t.id!==target?t:{...t,
      title:t.messages.length===0 && t.title==='新聊天'?text.slice(0,40):t.title,
      draft:'',updatedAt:Date.now(),messages:[...t.messages,{id:id(),role:'user',text}]}));
    void backendRequest<{chat_id:string;response:string}>('/api/ai-runtime/assistant/ask',{
      method:'POST',body:JSON.stringify({chat_id:serverChats[target]??null,message:text,attachments}),
    }).then(({data})=>{
      setServerChats(before=>({...before,[target]:data.chat_id}));
      setThreads(before=>before.map(t=>t.id!==target?t:{...t,updatedAt:Date.now(),
        messages:[...t.messages,{id:id(),role:'assistant',text:data.response}]}));
    }).catch(()=>{
      void msgApi.error('AI 服务暂时无法回应，请检查模型服务、账户权限和额度');
      setThreads(before=>before.map(t=>t.id!==target?t:{...t,
        messages:[...t.messages,{id:id(),role:'assistant',text:'AI 请求失败；没有生成模拟经营数据。请在业务配置中检查 OpenAI 服务。'}]}));
    }).finally(()=>setSending(false));
    setAttachmentMenu(false);
  };
  const onKeys=(e:KeyboardEvent<HTMLTextAreaElement>)=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();send();}};
  const onPaste=(e:ClipboardEvent<HTMLTextAreaElement>)=>{
    const incoming=Array.from(e.clipboardData.files).filter(f=>f.type.startsWith('image/'));
    if(incoming.length){e.preventDefault();acceptFiles(incoming);}
  };
  const onDrop=(e:DragEvent<HTMLDivElement>)=>{e.preventDefault();setDragging(false);acceptFiles(e.dataTransfer.files);};
  const onSelect=(e:ChangeEvent<HTMLInputElement>)=>{if(e.target.files)acceptFiles(e.target.files);e.target.value='';};
  const openEdit=(identifier:string)=>{
    const t=threads.find(c=>c.id===identifier);if(!t)return;
    setEditing(identifier);setEditTitle(t.title);setEditNote(t.note);
  };
  const saveEdit=()=>{
    if(!editing)return;
    if(!editTitle.trim()){void msgApi.warning('聊天名称不能为空');return;}
    changeChat(editing,{title:editTitle.trim(),note:editNote.trim()});setEditing(null);
  };
  const doDelete=()=>{
    if(!deleting)return;
    const t=threads.find(c=>c.id===deleting);
    for (const f of pending[deleting]??[])cleanupFile(f.id);
    for (const m of t?.messages??[])for(const f of m.files??[])cleanupFile(f.id);
    setPending(before=>{const next={...before};delete next[deleting];return next;});
    const next=threads.filter(c=>c.id!==deleting);
    if(!next.length)next.push(fresh());
    setThreads(next);if(activeId===deleting)setActiveId(next[next.length-1].id);
    setServerChats(before=>{const map={...before};delete map[deleting];return map;});
    setDeleting(null);
  };
  return <PageShell page={page}>
    {msgContext}
    <div className="ai7-root">
      {mobileOpen && <button type="button" className="ai7-shade" aria-label="关闭会话列表" onClick={()=>setMobileOpen(false)}/>}
      <aside className={'ai7-sidebar'+(!expanded?' ai7-collapsed':'')+(mobileOpen?' ai7-mobile-open':'')} aria-label="聊天记录">
        <div className="ai7-side-top">
          <div className="ai7-side-heading"><strong>AI 工作区</strong><Tooltip title="收起会话列表"><Button type="text" icon={<MenuFoldOutlined/>} onClick={()=>{setExpanded(false);setMobileOpen(false);}} aria-label="收起会话列表"/></Tooltip></div>
          <Button block icon={<PlusOutlined/>} className="ai7-new" onClick={newChat} aria-label="新建对话">新建对话</Button>
          <Input allowClear prefix={<SearchOutlined/>} className="ai7-search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索聊天或备注" aria-label="搜索聊天"/>
        </div>
        <div className="ai7-list"><div className="ai7-section">会话记录 <span>{visible.length}</span></div>
          {!visible.length&&<p className="ai7-muted">没有匹配的聊天</p>}
          {visible.map(t=><div className={'ai7-thread'+(t.id===chat.id?' ai7-current':'')} key={t.id}>
            <button type="button" className="ai7-thread-link" onClick={()=>{setActiveId(t.id);setMobileOpen(false);}} aria-current={t.id===chat.id?'page':undefined}><strong title={t.title}>{t.title}</strong><small title={t.note}>{t.note|| (t.messages.length?t.messages.filter(m=>m.role==='user').length+' 条提问':'暂无消息')}</small></button>
            <Dropdown trigger={['click']} menu={{items:[
              {key:'edit',label:'重命名 / 备注',icon:<EditOutlined/>,onClick:()=>openEdit(t.id)},
              {key:'delete',label:'删除聊天',danger:true,icon:<DeleteOutlined/>,onClick:()=>setDeleting(t.id)}
            ]}}><Button type="text" icon={<MoreOutlined/>} size="small" aria-label={'聊天操作：'+t.title}/></Dropdown>
          </div>)}
        </div>
        <p className="ai7-side-footer">聊天列表保存在当前浏览器，对话内容同步至服务端</p>
      </aside>
      <div className="ai7-main">
        <header className="ai7-toolbar"><Button type="text" icon={expanded?<MenuFoldOutlined/>:<MenuUnfoldOutlined/>} aria-label="切换聊天列表" onClick={()=>{setExpanded(!expanded);setMobileOpen(!mobileOpen);}}/><div className="ai7-thread-heading"><strong>{chat.title}</strong><small>{chat.note||'智能经营分析与连续追问'}</small></div></header>
        <div className="ai7-scroll" ref={scroller}>
          {!chat.messages.length?<div className="ai7-welcome"><div className="ai7-hero"><RobotOutlined/></div><h1>今天想分析什么？</h1><p>从单个 SKU 到整体经营，直接提问。<br/>分析数据与结论只在对话中按需显示。</p><div className="ai7-suggestions">{QUESTIONS.map(q=><button type="button" key={q[0]} onClick={()=>send(q[1])}><span><BarChartOutlined/></span><strong>{q[0]}</strong><small>{q[1]}</small></button>)}</div></div>:
          <div className="ai7-messages">{chat.messages.map(m=>m.role==='user'?<div className="ai7-user-row" key={m.id}><div>{!!m.files?.length&&<div className="ai7-file-list">{m.files?.map(f=><FileCard key={f.id} file={f} url={imageUrls[f.id]}/>)}</div>}{m.text&&<p>{m.text}</p>}</div></div>:<div className="ai7-assistant-row" key={m.id}><div className="ai7-bot"><RobotOutlined/></div><p>{m.text}</p></div>)}</div>}
        </div>
        <footer className="ai7-bottom"><div className={'ai7-composer'+(dragging?' ai7-dragging':'')}
          onDragEnter={e=>{e.preventDefault();setDragging(true);}}
          onDragOver={e=>e.preventDefault()}
          onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))setDragging(false);}}
          onDrop={onDrop}>
          {dragging&&<div className="ai7-drop-label"><UploadOutlined/> 拖拽文件到这里</div>}
          {!!uploads.length&&<div className="ai7-file-list">{uploads.map(f=><FileCard key={f.id} file={f} url={f.url} remove={()=>removeFile(f.id)}/>)}</div>}
          <textarea ref={editor} value={chat.draft} onChange={e=>changeChat(chat.id,{draft:e.target.value})}
            onKeyDown={onKeys} onPaste={onPaste} rows={2} placeholder="向 AI 提问，或添加图片与文件……" aria-label="输入问题"/>
          <div className="ai7-composer-actions"><Dropdown trigger={['click']} placement="topLeft" open={attachmentMenu} onOpenChange={setAttachmentMenu}
            menu={{items:[
              {key:'images',label:'上传图片',icon:<FileImageOutlined/>,onClick:()=>images.current?.click()},
              {key:'files',label:'上传文件（PDF、Excel、Word 等）',icon:<PaperClipOutlined/>,onClick:()=>files.current?.click()},
            ]}}><Tooltip title="添加图片或文件"><Button type="text" className="ai7-attach-btn" icon={<PlusOutlined/>} aria-label="添加附件"/></Tooltip></Dropdown>
            <Button type="primary" shape="circle" className="ai7-send" icon={<ArrowUpOutlined/>} aria-label="发送消息" disabled={sending||(!chat.draft.trim()&&!uploads.length)} loading={sending} onClick={()=>send()}/>
          </div>
          <input ref={images} type="file" accept="image/*" multiple hidden onChange={onSelect} aria-label="选择图片"/>
          <input ref={files} type="file" multiple hidden onChange={onSelect} aria-label="选择文件"/>
        </div><small>Enter 发送 · Shift+Enter 换行 · 支持拖拽和粘贴图片</small></footer>
      </div>
      <Modal title="编辑聊天信息" open={editing!==null} onCancel={()=>setEditing(null)} onOk={saveEdit} okText="保存" destroyOnHidden>
        <label className="ai7-label" htmlFor="ai7-title">聊天名称</label><Input id="ai7-title" maxLength={70} value={editTitle} onChange={e=>setEditTitle(e.target.value)}/>
        <label className="ai7-label" htmlFor="ai7-note">聊天备注</label><Input.TextArea id="ai7-note" rows={4} maxLength={300} value={editNote} onChange={e=>setEditNote(e.target.value)}/>
      </Modal>
      <Modal title="删除聊天？" open={deleting!==null} onCancel={()=>setDeleting(null)} onOk={doDelete} okText="删除聊天" okButtonProps={{danger:true}} destroyOnHidden>
        删除后，此聊天及备注将从当前浏览器的演示记录中移除，无法恢复。
      </Modal>
    </div>
  </PageShell>;
}
export default AIAssistantPage;
