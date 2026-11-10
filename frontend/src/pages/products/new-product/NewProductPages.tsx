import {useEffect,useMemo,useRef,useState} from "react";
import {Tabs,Typography} from "antd";
import {useNavigate} from "react-router-dom";
import type {NavigationPage} from "@/config/navigation";
import workflowHtml from "./original/new_product_analysis_demo_v4.html?raw";
import dashboardHtml from "./original/new_product_analysis_board.html?raw";
import {injectOriginalPrototype,type PrototypeMode,type PrototypeTab} from "./originalPrototypeBridge";
import "./NewProductOriginalPreview.css";

type Props={
  page:NavigationPage;
  mode:PrototypeMode;
  username?:string;
  canManage?:boolean;
  canConfigure?:boolean;
  canScore?:boolean;
  canRequest?:boolean;
  canReview?:boolean;
  canViewCost?:boolean;
};

/** Original HTML visual/interaction acceptance, not production business processing. */
export default function NewProductPages({page,mode}:Props){
 const navigate=useNavigate();
 const [tab,setTab]=useState<PrototypeTab>("detail");
 const workflow=useRef<HTMLIFrameElement>(null);
 const board=useRef<HTMLIFrameElement>(null);
 const currentMode=useRef(mode);
 currentMode.current=mode;

 const docs=useMemo(()=>({
   workflow:injectOriginalPrototype(workflowHtml,"workflow"),
   dashboard:injectOriginalPrototype(dashboardHtml,"dashboard")
 }),[]);

 function sync(target:"workflow"|"dashboard",nextMode:PrototypeMode){
   const frame=target==="workflow"?workflow.current:board.current;
   frame?.contentWindow?.postMessage({
     type:"np-original-set-page",
     page:target==="workflow"
       ?(nextMode==="performance"?"analysis":"tracking")
       :(nextMode==="performance"?"new":"launch")
   },"*");
 }
 useEffect(()=>{
   sync("workflow",mode);
   sync("dashboard",mode);
 },[mode]);
 useEffect(()=>{
   const onMessage=(event:MessageEvent)=>{
     if(event.source!==workflow.current?.contentWindow ||
        event.data?.type!=="np-original-navigate")return;
     const dest=event.data.page;
     if(!["analysis","tracking","new-dashboard","launch-dashboard"].includes(dest))return;
     const nextMode:PrototypeMode=dest==="analysis"||dest==="new-dashboard"?"performance":"tracking";
     const nextTab:PrototypeTab=dest.endsWith("dashboard")?"board":"detail";
     setTab(nextTab);
     if(nextMode!==currentMode.current){
       currentMode.current=nextMode;
       navigate(nextMode==="performance"?"/products/new-product-analysis":"/products/launch-tracking");
     } else {
       sync(nextTab==="detail"?"workflow":"dashboard",nextMode);
     }
   };
   window.addEventListener("message",onMessage);
   return ()=>window.removeEventListener("message",onMessage);
 },[navigate]);
 const tabs=mode==="performance"
 ?[{key:"detail",label:"新品表现"},{key:"board",label:"新品表现看板"}]
 :[{key:"detail",label:"打品跟踪"},{key:"board",label:"打品跟踪看板"}];
 return <div className="np-original-acceptance" data-page-key={page.key}>
   <div className="np-original-heading">
     <Typography.Text strong>{mode==="performance"?"新品表现":"打品跟踪"}</Typography.Text>
     <Typography.Text type="secondary">原始 HTML Mock 样式与交互验收 · 不连接业务数据库</Typography.Text>
   </div>
   <Tabs activeKey={tab} items={tabs} className="np-original-tabs"
     onChange={next=>{
       const value=next as PrototypeTab;
       setTab(value);
       sync(value==="detail"?"workflow":"dashboard",mode);
     }}/>
   <div className="np-original-frame-host">
     <iframe ref={workflow}
       title={mode==="performance"?"新品表现原始 V4 明细":"打品跟踪原始 V4 明细"}
       sandbox="allow-scripts" srcDoc={docs.workflow}
       onLoad={()=>sync("workflow",currentMode.current)}
       style={{display:tab==="detail"?"block":"none"}}/>
     <iframe ref={board}
       title={mode==="performance"?"新品表现原始看板":"打品跟踪原始看板"}
       sandbox="allow-scripts" srcDoc={docs.dashboard}
       onLoad={()=>sync("dashboard",currentMode.current)}
       style={{display:tab==="board"?"block":"none"}}/>
   </div>
 </div>;
}
