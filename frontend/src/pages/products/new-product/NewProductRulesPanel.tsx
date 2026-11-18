import { Alert, Checkbox, Input, InputNumber, Select, Slider, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ReactNode } from "react";
import type { Grade, Product } from "./nativeData";
import { dimensionNames, dimensionKeys, tierNames } from "./NewProductRulesModel";
import type { RuleDraft, RuleTier, RiskConditionRule } from "./NewProductRulesModel";
import NewProductConfirmedScoringPanel from "./NewProductConfirmedScoringPanel";

interface Props { tab: string; draft: RuleDraft; onChange: (draft: RuleDraft) => void; version: number; products: Product[] }

export default function NewProductRulesPanel({ tab, draft, onChange, version, products }: Props) {
  const update = (delta: Partial<RuleDraft>) => onChange({ ...draft, ...delta });
  const sum = Object.values(draft.weights).reduce((a, b) => a + b, 0);
  const titleAndIntro = (title: string, intro: string) => <div className="np-rule-intro"><h2>{title}</h2><p>{intro}</p></div>;
  const group = (title: string, desc: string, children: ReactNode) => <section className="np-rule-group"><h3>{title}</h3>{desc && <p>{desc}</p>}{children}</section>;
  const number = (value: number, apply: (v: number) => void, opts?: { min?: number; max?: number; step?: number; disabled?: boolean }) => (
    <InputNumber
      value={value}
      min={opts?.min}
      max={opts?.max}
      step={opts?.step}
      disabled={opts?.disabled}
      controls={false}
      style={{ width: "100%" }}
      onChange={v => { if (v !== null) apply(v); }}
    />
  );
  const gradeColors: Record<Grade, string> = { S: "#6941c6", A: "#027a48", B: "#175cd3", C: "#b54708", D: "#b42318", Pass: "#b42318" };


  if (tab === "weights") return <div className="np-rule-panel">
    {titleAndIntro("评分权重", "按测品评分表配置 5 个维度。权重合计必须为 100%，市场竞争由运营填写，其余 4 项由系统计算。")}
    {group("", "", <>
      {dimensionKeys.map(key => <div className="np-rule-weight-row" key={key}>
        <label>{dimensionNames[key]}</label>
        <Slider value={draft.weights[key]} min={0} max={100} tooltip={{ open: false }} onChange={v => update({ weights: { ...draft.weights, [key]: v } })} />
        {number(draft.weights[key], v => update({ weights: { ...draft.weights, [key]: v } }), { min: 0, max: 100 })}
      </div>)}
      <div className="np-rule-total"><span>当前权重合计</span><strong style={{color:sum===100?"#027a48":"#b42318"}}>{sum}%</strong></div>
    </>)}
    <Alert type="warning" showIcon={false} message="待确认：原评分表顶部说明写利润 20%、风险与供应链 15%；实际评分行写利润 25%、数据可信度 10%。当前 Demo 按实际评分行使用 15 / 30 / 20 / 25 / 10。" />
    {group("评分触发与提醒", "系统不会自动生成最终总分和评级；Listing 达到提醒天数后提醒运营填写市场竞争评分，提交后才计算最终结果。", <>
      <label className="np-rule-field-label">上架满多少天提醒运营评分</label>
      {number(draft.remindDays, v => update({remindDays:v}), {min:1,max:180})}
      <div className="np-rule-help">默认 30 天。提醒只生成一次，未完成任务持续显示在待办中。</div>
    </>)}
  </div>;

  if (tab === "criteria") return <NewProductConfirmedScoringPanel draft={draft} onChange={onChange} products={products}/>;

  if (tab === "grades") {
    const columns: ColumnsType<{key:Grade}> = [
      { title:"评级", dataIndex:"key", width:"10%", render:(g:Grade)=><strong style={{color:gradeColors[g]}}>{g}</strong> },
      { title:"最低分", width:"16%", render:(_,item)=>item.key==="Pass"?"—":number(draft.gradeBands[item.key as RuleTier][0], v=>{
        const gradeBands={...draft.gradeBands,[item.key]:[v,draft.gradeBands[item.key as RuleTier][1]] as [number,number]}; update({gradeBands});
      },{min:0,max:10,step:.01}) },
      { title:"最高分", width:"16%", render:(_,item)=>item.key==="Pass"?"—":number(draft.gradeBands[item.key as RuleTier][1], v=>{
        const gradeBands={...draft.gradeBands,[item.key]:[draft.gradeBands[item.key as RuleTier][0],v] as [number,number]};update({gradeBands});
      },{min:0,max:10,step:.01}) },
      { title:"采购最小量", width:"22%", render:(_,item)=>number(draft.quantities[item.key][0],v=>{
        const quantities={...draft.quantities,[item.key]:[v,draft.quantities[item.key][1]] as [number,number]};update({quantities});
      },{min:0,disabled:item.key==="D"||item.key==="Pass"}) },
      { title:"采购最大量", width:"22%", render:(_,item)=>number(draft.quantities[item.key][1],v=>{
        const quantities={...draft.quantities,[item.key]:[draft.quantities[item.key][0],v] as [number,number]};update({quantities});
      },{min:0,disabled:item.key==="D"||item.key==="Pass"}) },
      { title:"生成建议", width:"14%", render:(_,item)=>item.key==="D"||item.key==="Pass"?"否":"是" },
    ];
    return <div className="np-rule-panel">
      {titleAndIntro("评级与采购数量", "每个评级的采购数量范围可以配置。系统建议采购量无论预测需求是多少，都必须落在对应评级范围内。")}
      {group("评级分数与采购范围", "评级分数区间与采购数量范围均可配置。发布前应检查分数区间无重叠、无空档。", <Table className="np-rule-table" rowKey="key" pagination={false} size="small"  columns={columns} dataSource={tierNames.map(key=>({key}))}/>)}
      {group("建议数量计算策略", "先根据当前需求计算，再限制在评级范围内。即使预测数量低于最小值或高于最大值，也不允许系统建议量越界。", <>
        <label className="np-rule-field-label">区间内建议策略</label>
        <Select style={{width:"100%"}} value={draft.quantityStrategy} onChange={v=>update({quantityStrategy:v})} options={[
          {label:"取评级最低数量",value:"min"},{label:"参考近期销量，在区间内取值",value:"mid"},{label:"取评级最高数量",value:"max"},
        ]}/>
        <Alert type="info" showIcon={false} message="约束公式：建议数量 = min(评级最大量, max(评级最小量, 预测需求))。D / Pass 不生成采购建议。" />
      </>)}
    </div>;
  }

  if (tab === "penalties") {
    // The existing config-navigation key is retained to avoid unnecessary
    // page-state changes; all user-visible copy now says 配置风险条件.
    const changeRisk=(code:string, patch:Partial<RiskConditionRule>)=>update({
      riskConditions:draft.riskConditions.map(r=>r.code===code?{...r,...patch}:r),
    });
    const changeParameter=(r:RiskConditionRule,field:string,value:number|null)=>changeRisk(r.code,{
      params:{...r.params,[field]:value},
    });
    const thresholds:Record<string,Array<[string,string]>>={
      ad_sample_insufficient:[["clicks_below","累计点击少于"]],
      ad_uncontrolled:[["min_clicks","累计点击至少"],["cvr_below_pct","广告CVR低于(%)"]],
      low_margin:[["margin_below_pct","毛利率低于(%)"]],
      high_ad_spend_ratio:[["share_above_pct","广告占比高于(%)"]],
    };
    const riskCols:ColumnsType<RiskConditionRule>=[
      {title:"启用",width:"9%",render:(_,r)=><Checkbox checked={r.enabled} onChange={e=>changeRisk(r.code,{enabled:e.target.checked})}/>},
      {title:"风险条件",dataIndex:"name",width:"23%",render:(name:string,r:RiskConditionRule)=>
        r.code==="roi_very_low"?"ROI严重偏低":r.code==="roi_low"?"ROI偏低":name},
      {title:"触发条件",width:"45%",render:(_,r)=>r.source==="manual"
        ?<span>运营在市场评分时人工确认</span>
        :<div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          {(thresholds[r.code]??[]).map(([field,label])=><label key={field} style={{display:"inline-flex",alignItems:"center",gap:4}}>
            <span>{label}</span>
            <InputNumber style={{width:92}} controls={false} min={0}
              max={["margin_below_pct","share_above_pct","cvr_below_pct"].includes(field)?100:undefined}
              precision={["clicks_below","min_clicks"].includes(field)?0:2}
              placeholder="待配置" value={r.params[field]}
              onChange={value=>changeParameter(r,field,value)}/>
          </label>)}
        </div>},
      {title:"等级限制",width:"23%",render:(_,r)=><Select style={{width:"100%"}} value={r.limit}
        options={(r.source==="system"?["B","C","D"]:["none","B","C","D","recommend_not_pass"]).map(value=>({
          value,label:value==="none"?"仅提示 / 复核":value==="recommend_not_pass"?"系统不建议通过":`最高 ${value} 级`,
        }))}
        onChange={value=>changeRisk(r.code,{limit:value as RiskConditionRule["limit"]})}/>},
    ];
    return <div className="np-rule-panel">
      {titleAndIntro("配置风险条件","五维评分不额外扣分。系统风险按已启用的阈值自动识别；人工风险由运营勾选。命中风险时只限制建议等级，保留基础得分。")}
      {group("系统识别风险","四项阈值已确认；可勾选启用。正式评分执行链路仍需单独接通，未接通前不自动限制等级。",
        <Table className="np-rule-table" size="small" rowKey="code" pagination={false} columns={riskCols}
          dataSource={draft.riskConditions.filter(r=>r.source==="system")}/>)}
      {group("人工风险条件","运营在市场评分时选择实际风险；配置停用后不允许新选择。‘无’是人工选项，不是可配置风险。",
        <Table className="np-rule-table" size="small" rowKey="code" pagination={false} columns={riskCols}
          dataSource={draft.riskConditions.filter(r=>r.source==="manual")}/>)}
    </div>;
  }

  if (tab === "success") return <div className="np-rule-panel">
    {titleAndIntro("打品成功标准", "采购后经营结果独立于测评评级。观察期从首批库存到货且 Listing 可售之日开始。")}
    {group("观察周期", "", <div className="np-rule-pair"><div><label className="np-rule-field-label">阶段观察点</label><Input value="30 / 60 / 90 天" disabled /></div><div><label className="np-rule-field-label">追踪起算条件</label><Input value="首批到货 + Listing 可售" disabled /></div></div>)}
    {group("成功目标（示例，可配置）", "", <>
      <div className="np-rule-pair">{([
        ["sales30", "30 天累计销量不少于",0,100000], ["margin", "利润率不低于（%）",0,100],
        ["acos", "ACOS 不高于（%）",0,100], ["needProfitDays", "持续盈利天数",1,90],
      ] as const).map(([key,label,min,max])=><div key={key}>
        <label className="np-rule-field-label">{label}</label>
        {number(draft.success[key],v=>update({success:{...draft.success,[key]:v}}),{min,max})}
      </div>)}</div>
      <Alert type="info" showIcon={false} message="建议初期采用「系统根据配置判定 + 运营确认结果」。数据不足、未到观察期或因断货导致观察失真时，不自动判失败。" />
    </>)}
    {group("打品结果", "", <div className="np-rule-result-list">{[
      ["打品成功", "达到配置的销量、利润和广告目标"],
      ["继续观察", "观察期未结束或样本不足"],
      ["需要优化", "尚未达标，但仍有可改善空间"],
      ["打品失败", "观察期结束且未达标，需记录失败原因"],
    ].map(([key,value])=><div key={key}><strong>{key}</strong><span>{value}</span></div>)}</div>)}
  </div>;

  return <div className="np-rule-panel">
    {titleAndIntro("规则版本", "规则版本与评分结果、采购建议和审批申请绑定，发布新规则不覆盖历史快照。")}
    <div className="np-rule-result-list">{[
      ["当前草稿版本", `v${version}.0-demo`],
      ["生效方式", "发布后用于后续评分；已提交审核的申请保留原规则快照"],
      ["修改记录", "权重、采购数量区间、风险条件等修改需保留人员、时间与原因"],
      ["历史评分", "保留分项得分、数据截止时间、最终分数、评级和采购建议"],
    ].map(([name,value])=><div key={name}><strong>{name}</strong><span>{value}</span></div>)}</div>
    {group("正式发布前待确认", "", <Alert type="warning" showIcon={false} message="① 权重表头与评分行不一致；② 7.85 分示例评级 B/C 不一致；③ ROI 评级上限 0.7/0.8 不一致。Demo 不自动替你裁决这些业务规则。" />)}
  </div>;
}
