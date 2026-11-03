/** 财务板块中尚未迁到正式系统的页面：说明内容、Demo 对应位置与正式化顺序（本地预览阶段 A）。 */
import { Descriptions } from "antd";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import FinanceBoardFrame from "@/pages/finance/FinanceBoardFrame";

const PLAN: Record<string, { demo: string; what: string; next: string }> = {
  finance_profit_center: { demo: "① 经营总览", what: "管理层面板：财务简报、产品结算利润、现金利润三档、资金盘点。", next: "最后做：汇总 现金利润 / 结算利润 / 财务报表 / 资金流水 的结果" },
  finance_sku_cash_profit: { demo: "② 现金利润", what: "单品现金账：投入（采购 + 头程 + 其他）→ 回款 = 现金利润，按商品 / 店铺 / 批次。", next: "与结算利润共用成本引擎（领星发货单 + 成本计价同步、旧系统镜像费用）" },
  finance_settlement_profit: { demo: "③ 结算利润", what: "按账单月：结算单 + 成本 + 广告 / 仓储 / WFS 费用 + 人工调整 + 待核清单。", next: "等 #290 结算单同步 + 成本引擎" },
  finance_settlement_reconciliation: { demo: "④ 回款对账", what: "每期账单 vs 到账流水：自动识别收款账户、确认 / 核销 / 指定到账 / 撤销。", next: "PR-C；依赖 #289 流水导入 + #290 结算 / 回款单" },
  finance_performance_report: { demo: "⑤ 财务报表", what: "经营利润表、现金口径月报。", next: "现金利润 / 结算利润 / 资金流水 之后" },
  finance_balance_sheet: { demo: "⑥ 资产负债表", what: "资金盘点口径：账户月末余额 − 剔除净额 + 平台应收 + 库存。", next: "资金流水之后" },
  finance_cost_exception: { demo: "⑧ 成本异常处理", what: "期初库存 / 无发货单货件 / 固定值订单的成本修正清单，结账锁月。", next: "随成本引擎" },
  finance_settings: { demo: "⑨ 口径与设置", what: "类别字典、自动分类规则（财务专员维护，版本化）、汇率、页签说明。", next: "随 PR-E 资金流水" },
};

function FinancePlaceholderPage({ page }: { page: NavigationPage }) {
  const plan = PLAN[page.key];
  return (
    <PageShell page={page}>
      <FinanceBoardFrame title={page.title} subtitle="正式页面建设中；服务器 Demo 对应页可先用">
        <Descriptions column={1} size="small" bordered style={{ maxWidth: 960 }}>
          <Descriptions.Item label="Demo 对应">{plan?.demo ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="内容">{plan?.what ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="正式化">{plan?.next ?? "—"}</Descriptions.Item>
        </Descriptions>
      </FinanceBoardFrame>
    </PageShell>
  );
}

export default FinancePlaceholderPage;
