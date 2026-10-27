/** V7 conversation workspace in the existing SZZSBJ MainLayout. UI preview only. */
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
import type { NavigationPage } from '@/config/navigation';
import './AIAssistantPage.css';

type Attachment = { id: string; name: string; size: number; image: boolean };
type ChatMessage = { id: string; role: 'user' | 'assistant'; text: string; files?: Attachment[]; analysis?: boolean };
type Thread = { id: string; title: string; note: string; draft: string; updatedAt: number; messages: ChatMessage[] };
type UploadItem = Attachment & { file: File; url?: string };
type Props = { page: NavigationPage; preferenceScope?: string };
const MAX_FILES = 10;
const MAX_BYTES = 20 * 1024 * 1024;
const EXT = new Set('png jpg jpeg webp gif bmp heic heif pdf doc docx xls xlsx csv txt md json ppt pptx xml yaml yml zip html sql py js ts'.split(' '));
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
function DemoReply({ question, followup }: { question: string; followup: (text: string) => void }) {
  const isManager = /整体|公司|店铺|管理/.test(question);
  const isAds = /广告|ACOS|ROAS/.test(question);
  const title = isManager ? '整体经营变化分析' : isAds ? '广告投入与订单分析' : /哪些|排名|最严重/.test(question) ? '异常 SKU 排查' : 'SKU 经营诊断';
  const metrics = isManager
    ? [['销售额','$28,560','-6.2%'],['订单利润','$3,410','-12.8%'],['广告费用','$4,820','+9.4%']]
    : isAds ? [['广告费用','$726','+14.2%'],['广告订单','52 单','-5.5%'],['广告占比','18.6%','+3.1pp']]
    : [['销售额','$1,240','-8.2%'],['订单利润','$186','-27.4%'],['退款损失','$42','+$19']];
  return <div className="ai7-answer">
    <div className="ai7-demo-label">演示分析 · 模拟数据，尚未接入真实业务接口和 OpenAI</div>
    <h3>{title}</h3>
    <p>从销售、利润、广告和退款变化中定位经营异常。此处为界面预览，所有指标仅用于演示，不能据此作出真实经营决策。</p>
    <div className="ai7-card"><h4>关键指标对比</h4><div className="ai7-metrics">{metrics.map(m => <div key={m[0]}><small>{m[0]}</small><strong>{m[1]}</strong><em>{m[2]} 较上期</em></div>)}</div></div>
    <div className="ai7-card"><h4>{isManager ? '店铺经营明细' : '需要关注的 SKU'}</h4><div className="ai7-table-wrap"><table><thead><tr><th>{isManager ? '店铺' : 'SKU'}</th><th>销售额</th><th>订单利润</th><th>利润变化</th></tr></thead><tbody>{(isManager ? [['Store A','$12,100','$1,420','-$270'],['Store B','$9,260','$1,180','-$142'],['Store C','$7,200','$810','+$30']] : [['SKU-1082','$1,240','$186','-$70'],['SKU-3106','$986','$94','-$63'],['SKU-4210','$876','$128','-$51']]).map(row => <tr key={row[0]}>{row.map((cell,i) => <td key={i}>{i===0 ? <button type="button" className="ai7-textlink" onClick={() => followup('继续分析 ' + cell)}>{cell}</button> : cell}</td>)}</tr>)}</tbody></table></div></div>
    <div className="ai7-card"><h4>分析与建议</h4><ol><li>核对利润变化与费用变化的金额，不将相关性当作因果关系。</li><li>如果广告或退款明细缺失，应标注数据不足并优先核实。</li></ol></div>
    <div className="ai7-followups"><button type="button" onClick={() => followup(isManager ? '按负责人继续分析' : '分析 SKU-1082 的广告费用')}>进一步下钻 ↗</button><button type="button" onClick={() => followup('列出利润下降最严重的 SKU')}>查看异常产品 ↗</button></div>
  </div>;
}
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
  const images = useRef<HTMLInputElement>(null);
  const files = useRef<HTMLInputElement>(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const urls = useRef(new Map<string,string>());
  const chat = threads.find(t => t.id === activeId) ?? threads[0];
  const uploads = pending[chat.id] ?? [];
  const visible = useMemo(() => [...threads].sort((a,b) => b.updatedAt-a.updatedAt).filter(t => (t.title+' '+t.note).toLowerCase().includes(search.toLowerCase())),[threads,search]);
  useEffect(() => { try { localStorage.setItem(key(preferenceScope),JSON.stringify(threads)); } catch { /* optional persistence */ } },[preferenceScope,threads]);
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
    if(rejected)void msgApi.warning(rejected+' 个附件不符合格式、20MB 或 10 个的限制');
    setAttachmentMenu(false);
  };
  const send = (preset?:string) => {
    const text=(preset??chat.draft).trim();
    if(!text && !uploads.length)return;
    const added:Attachment[]=uploads.map(f=>({id:f.id,name:f.name,size:f.size,image:f.image}));
    setThreads(before=>before.map(t=>{
      if(t.id!==chat.id)return t;
      return {...t,title:t.messages.length===0 && t.title==='新聊天'?(text||'附件：'+added[0].name).slice(0,40):t.title,
        draft:'',updatedAt:Date.now(),messages:[...t.messages,
          {id:id(),role:'user',text,files:added},
          {id:id(),role:'assistant',text:text?'':'文件已添加至本地演示会话。尚未上传服务器或供 OpenAI 解析。',analysis:!!text}]};
    }));
    setPending(before=>({...before,[chat.id]:[]}));
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
        <p className="ai7-side-footer">演示会话仅保存在当前浏览器</p>
      </aside>
      <div className="ai7-main">
        <header className="ai7-toolbar"><Button type="text" icon={expanded?<MenuFoldOutlined/>:<MenuUnfoldOutlined/>} aria-label="切换聊天列表" onClick={()=>{setExpanded(!expanded);setMobileOpen(!mobileOpen);}}/><div className="ai7-thread-heading"><strong>{chat.title}</strong><small>{chat.note||'智能经营分析与连续追问'}</small></div></header>
        <div className="ai7-scroll" ref={scroller}>
          {!chat.messages.length?<div className="ai7-welcome"><div className="ai7-hero"><RobotOutlined/></div><h1>今天想分析什么？</h1><p>从单个 SKU 到整体经营，直接提问。<br/>分析数据与结论只在对话中按需显示。</p><div className="ai7-suggestions">{QUESTIONS.map(q=><button type="button" key={q[0]} onClick={()=>send(q[1])}><span><BarChartOutlined/></span><strong>{q[0]}</strong><small>{q[1]}</small></button>)}</div></div>:
          <div className="ai7-messages">{chat.messages.map(m=>m.role==='user'?<div className="ai7-user-row" key={m.id}><div>{!!m.files?.length&&<div className="ai7-file-list">{m.files?.map(f=><FileCard key={f.id} file={f} url={imageUrls[f.id]}/>)}</div>}{m.text&&<p>{m.text}</p>}</div></div>:<div className="ai7-assistant-row" key={m.id}><div className="ai7-bot"><RobotOutlined/></div>{m.analysis?<DemoReply question={chat.messages[chat.messages.findIndex(x=>x.id===m.id)-1]?.text??''} followup={send}/>:<p>{m.text}</p>}</div>)}</div>}
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
            <Button type="primary" shape="circle" className="ai7-send" icon={<ArrowUpOutlined/>} aria-label="发送消息" disabled={!chat.draft.trim()&&!uploads.length} onClick={()=>send()}/>
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
