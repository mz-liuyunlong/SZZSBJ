/** Owner-supplied unmodified HTML prototypes in isolated sandbox iframes. */
export type PrototypeMode = "performance" | "tracking";
export type PrototypeTab = "detail" | "board";
type Kind = "workflow" | "dashboard";
const workflowCss = `
html,body{height:100%;min-height:0;overflow:hidden}
.app{height:100%;min-height:0}
.sidebar,.topbar,.tabsbar,.nav-foot{display:none!important}
.main{margin-left:0!important;width:100%!important;height:100%!important;min-height:0!important}
.content{margin:0!important;padding:12px!important;max-width:none!important;
width:100%!important;border-radius:0!important;background:#fff!important}
`;
const dashboardCss = `
html,body{height:100%;min-height:0;overflow:hidden}
.app{height:100%!important;min-height:0!important}
.topbar,.primary-nav,.secondary-nav,.nav-foot,.tabbar,.dashboard-tabs{display:none!important}
.workspace{display:block!important;height:100%!important;min-height:0!important}
.content-workspace{height:100%!important;min-height:0!important;
margin:0!important;width:100%!important}
.content-frame{height:100%!important;min-height:0!important;width:100%!important;
margin:0!important;padding:12px!important;overflow:auto!important}
.page{min-height:0!important;padding:0!important;width:100%!important}
`;
const workflowJs = `
var originalNavigate = navigate;
window.addEventListener('message',function(e){
  if(!e.data||e.data.type!=='np-original-set-page')return;
  if(e.data.page==='analysis'||e.data.page==='tracking')originalNavigate(e.data.page);
});
navigate=function(target){
  if(['analysis','tracking','new-dashboard','launch-dashboard'].includes(target)){
    window.parent.postMessage({type:'np-original-navigate',page:target},'*');
    return;
  }
  return originalNavigate(target);
};
`;
const boardJs = `
window.addEventListener('message',function(e){
 if(!e.data||e.data.type!=='np-original-set-page')return;
 if(e.data.page!=='new'&&e.data.page!=='launch')return;
 state.dashboard=e.data.page;renderDashboard();
});
`;
export function injectOriginalPrototype(html:string,kind:Kind):string {
 if(!html.includes("</head>")||!html.includes("</body>"))
   throw new Error("Original HTML prototype is incomplete");
 return html
 .replace("</head>","<style data-original-shell>"+(kind==="workflow"?workflowCss:dashboardCss)+"</style></head>")
 .replace("</body>","<script data-original-bridge>"+(kind==="workflow"?workflowJs:boardJs)+"</script></body>");
}
