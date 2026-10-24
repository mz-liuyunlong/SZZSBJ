/** Browser-only SellerSprite import. Workbook contents are untrusted; formulas are not evaluated. */
import * as XLSX from 'xlsx';
import { makeTermId, normalizeTerm } from './model';
import type { MarketKeyword, SourceWorkbook } from './types';

const MAX_BYTES=12*1024*1024;
const MAX_ROWS=12000;
const num=(v:unknown):number|null=>{
  if(v===null||v===undefined||String(v).trim()==='')return null;
  const parsed=Number(String(v).replace(/[$,%\s,]/g,''));return Number.isFinite(parsed)?parsed:null;
};
const text=(v:unknown):string=>String(v??'').trim();
const rate=(v:unknown):number|null=>{
  const n=num(v);if(n===null)return null;
  return typeof v==='string'&&v.includes('%')?n/100:n;
};
const price=(v:unknown):number|null=>num(v);
const headerAt=(rows:unknown[][],needle:string):number=>rows.findIndex(r=>r.some(x=>text(x)===needle));
const getCell=(r:unknown[],head:string[],key:string):unknown=>{const i=head.indexOf(key);return i<0?null:r[i]};
function safeSheetRows(sheet:XLSX.WorkSheet):unknown[][] {
  const rows=XLSX.utils.sheet_to_json<unknown[]>(sheet,{header:1,raw:true,defval:null,blankrows:false});
  if(rows.length>MAX_ROWS+30)throw new Error(`表格最多允许 ${MAX_ROWS} 行关键词`);
  return rows;
}
export async function parseSellerSprite(file:File):Promise<SourceWorkbook>{
  if(!/\.(xlsx|xls|csv|tsv)$/i.test(file.name))throw new Error('仅支持 xlsx、xls、csv、tsv 文件');
  if(file.size===0||file.size>MAX_BYTES)throw new Error('文件不能为空，且不能超过 12MB');
  const bytes=new Uint8Array(await file.arrayBuffer());
  let wb:XLSX.WorkBook;
  try{wb=XLSX.read(bytes,{type:'array',cellFormula:false,cellHTML:false,cellStyles:false,bookVBA:false});}
  catch{throw new Error('无法读取文件，请检查 Excel 或 CSV 格式是否正确')}
  const main=wb.SheetNames.find(name=>{
    const sheet=wb.Sheets[name];if(!sheet)return false;
    const rows=safeSheetRows(sheet).slice(0,15);return headerAt(rows,'关键词')>=0;
  });
  if(!main)throw new Error('没有找到「关键词」表头，请上传卖家精灵关键词拓展表');
  const mainRows=safeSheetRows(wb.Sheets[main]);const hi=headerAt(mainRows,'关键词');
  const heads=mainRows[hi].map(text);
  const warnings:string[]=[];
  for(const col of ['关键词翻译','月搜索量','月购买量','购买率','PPC竞价','建议竞价范围'])if(!heads.includes(col))warnings.push(`缺少参考字段：${col}`);
  const map=new Map<string,MarketKeyword>();
  for(let i=hi+1;i<mainRows.length;i++){
    const row=mainRows[i];const original=text(getCell(row,heads,'关键词'));
    if(!original||original.startsWith('='))continue;
    const normalized=normalizeTerm(original);if(!normalized)continue;
    if(map.has(normalized))continue;
    const translated=text(getCell(row,heads,'关键词翻译'));
    const asins=text(getCell(row,heads,'相关ASIN')).split(/[/,;，；\s]+/).filter(v=>/^[A-Z0-9]{10}$/.test(v.toUpperCase()));
    const k:MarketKeyword={id:makeTermId(original),term:original,normalized,originalTranslation:translated||null,translation:translated||null,translationSource:translated?'file':'missing',monthlySearches:num(getCell(row,heads,'月搜索量')),monthlyPurchases:num(getCell(row,heads,'月购买量')),marketPurchaseRate:rate(getCell(row,heads,'购买率')),amazonPpc:price(getCell(row,heads,'PPC竞价')),bidRange:text(getCell(row,heads,'建议竞价范围'))||null,trafficType:text(getCell(row,heads,'流量词类型'))||null,relatedAsins:[...new Set(asins)],sponsoredCompetitors:num(getCell(row,heads,'广告竞品数')),listingCount:num(getCell(row,heads,'商品数')),root:normalized.split(' ').slice(0,2).join(' '),source:'excel',sourceRow:i+1};
    map.set(normalized,k);
  }
  if(!map.size)throw new Error('关键词主表没有可导入的有效关键词');
  const roots:SourceWorkbook['roots']=[];
  const rootSheet=wb.Sheets['Unique Words'];
  if(rootSheet){for(const r of safeSheetRows(rootSheet).slice(1)){
    const root=text(r[0]),count=num(r[1]);if(root&&count!==null)roots.push({term:root,count});
  }}else warnings.push('未找到 Unique Words 工作表');
  const asins:string[]=[];const asinSheet=wb.Sheets['Asin'];
  if(asinSheet){for(const r of safeSheetRows(asinSheet).slice(1)){
    const asin=text(r[0]).toUpperCase();if(/^[A-Z0-9]{10}$/.test(asin)&&!asins.includes(asin))asins.push(asin);
  }}else warnings.push('未找到 Asin 工作表；请手动录入');
  return {fileName:file.name,sheets:wb.SheetNames,keywords:[...map.values()],roots,asins,importedAt:new Date().toISOString(),warnings};
}
export function downloadKeywordReviewWorkbook(fileName:string,headers:string[],rows:Array<Array<string|number|null>>):void{
  const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet([headers,...rows]),'关键词资产');
  XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet([['状态','本地关键词初筛，不是 Walmart 官方批量上传文件'],['声明','市场 PPC 来自上传源文件，当前未接入真实广告数据或 AI 分析服务']]),'说明');
  XLSX.writeFile(wb,fileName+'_关键词资产.xlsx');
}