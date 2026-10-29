/** V3 approval business views; no simulated approvals in production. */
export type ApprovalBusinessKey = "all"|"purchase"|"wfs"|"clearance"|"listing"|"disposal"|"price"|"finance";
export interface ApprovalBusiness {
  key: ApprovalBusinessKey;
  label: string;
  type?: string;
  live: boolean;
  columns: readonly string[];
}
export const approvalBusinesses: readonly ApprovalBusiness[] = [
 {key:"all",label:"全部业务",live:true,columns:["approval_type","title","risk_level","amount","applicant_id","submitted_at","status","action"]},
 {key:"purchase",label:"采购审批",type:"purchase_exception",live:true,columns:["approval_type","title","business_ref","amount","risk_level","applicant_id","submitted_at","status","action"]},
 {key:"wfs",label:"WFS异常费用",type:"wfs_case_abandon",live:true,columns:["approval_type","title","follow_log","case_opened_at","follow_count","risk_level","amount","applicant_id","submitted_at","status","action"]},
 {key:"clearance",label:"清货审批",type:"clearance_request",live:false,columns:["approval_type","title","business_ref","risk_level","applicant_id","submitted_at","status","action"]},
 {key:"listing",label:"Listing归档",type:"listing_archive",live:false,columns:["approval_type","title","business_ref","risk_level","applicant_id","submitted_at","status","action"]},
 {key:"disposal",label:"库存处置",type:"inventory_disposal",live:false,columns:["approval_type","title","business_ref","amount","risk_level","applicant_id","submitted_at","status","action"]},
 {key:"price",label:"价格调整",type:"price_adjustment",live:false,columns:["approval_type","title","business_ref","risk_level","applicant_id","submitted_at","status","action"]},
 {key:"finance",label:"财务调整",type:"finance_exception",live:true,columns:["approval_type","title","business_ref","risk_level","applicant_id","submitted_at","status","action"]},
];
export const approvalBusinessByKey = Object.fromEntries(approvalBusinesses.map(x=>[x.key,x])) as Record<ApprovalBusinessKey,ApprovalBusiness>;
export const approvalBusinessLabel = (type:string) => approvalBusinesses.find(x=>x.type===type)?.label ??
 (type==="operations_plan_ack"?"运营事项":type==="access_change"?"权限变更":"其他审批");
