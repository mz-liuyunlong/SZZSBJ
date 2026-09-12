/** Role-management No-API acceptance data; replace it when a real RBAC API is approved. */
import {
  type FieldPermissionValue,
  type PermissionGroup,
  type RoleManagementRow,
  type RolePermissionState,
} from "@/pages/settings/roleManagementTypes";

export const roleManagementMockData: RoleManagementRow[] = [
  { id: "role-ai-assistant", name: "AI助手", description: "AI 调整广告、分析数据辅助角色", preset: true, userCount: 1 },
  { id: "role-operator", name: "运营", description: "日常运营角色", preset: false, userCount: 18 },
  { id: "role-buyer", name: "采购", description: "采购计划、采购单与供应商资料维护", preset: false, userCount: 4 },
  { id: "role-warehouse", name: "仓库管理", description: "库存、入库运输、库存库龄与差异处理", preset: false, userCount: 5 },
  { id: "role-finance", name: "财务管理", description: "利润、结算、广告账单与费用规则", preset: false, userCount: 3 },
  { id: "role-ad-admin", name: "广告负责人", description: "广告活动、关键词、否定词和调价记录管理", preset: false, userCount: 2 },
  { id: "role-boss", name: "老板", description: "查看全局经营数据和关键异常", preset: false, userCount: 1 },
  { id: "role-admin", name: "管理员", description: "系统配置、用户、角色和权限维护", preset: true, userCount: 2 },
];

export const pagePermissionGroups: PermissionGroup[] = [
  { title: "工作台", items: ["今日销售", "今日利润", "库存预警", "待办任务"] },
  { title: "产品", items: ["产品管理", "Listing管理", "认领中心", "新品分析", "产品生命周期"] },
  { title: "销售", items: ["每日销售", "订单利润", "Review看板", "补货建议"] },
  { title: "广告", items: ["广告总览", "广告活动", "关键词排名", "搜索词", "AI优化记录"] },
  { title: "售后", items: ["退款管理", "退货管理", "客户消息", "Case管理"] },
  { title: "仓库", items: ["库存明细", "库存预警", "入库运输", "库存库龄"] },
  { title: "财务", items: ["利润中心", "单品现金利润", "结算对账", "广告账单"] },
  { title: "设置", items: ["用户管理", "角色管理", "费用规则", "系统配置"] },
];

export const actionPermissionGroups: PermissionGroup[] = [
  { title: "通用操作", items: ["查看", "新增", "编辑", "删除", "导出", "下载"] },
  { title: "产品操作", items: ["同步产品资料", "修改产品等级", "查看成本", "查看物流费用"] },
  { title: "Listing操作", items: ["同步Listing", "修改标题", "查看Buy Box", "查看跟卖状态"] },
  { title: "广告操作", items: ["查看广告", "调整预算", "调整出价", "否定关键词", "查看操作日志"] },
  { title: "系统操作", items: ["设置角色", "重置密码", "停用用户", "删除用户"] },
];

export const fieldPermissionNames = [
  "采购成本",
  "采购链接",
  "库存单价",
  "库存货值",
  "供应商",
  "物流费用",
  "平台佣金",
  "利润金额",
  "广告花费",
  "回款金额",
  "店铺授权信息",
  "账号密钥摘要",
];

const buildBooleanPermissions = (groups: PermissionGroup[], enabled = true) => Object.fromEntries(
  groups.flatMap((group) => group.items.map((item) => [item, enabled])),
);

const buildFieldPermissions = (value: FieldPermissionValue) => Object.fromEntries(
  fieldPermissionNames.map((field) => [field, value]),
) as Record<string, FieldPermissionValue>;

export const createDefaultRolePermissions = (): RolePermissionState => ({
  pagePermissions: buildBooleanPermissions(pagePermissionGroups),
  actionPermissions: buildBooleanPermissions(actionPermissionGroups),
  fieldPermissions: buildFieldPermissions("visible"),
});

export const rolePermissionMockData: Record<string, RolePermissionState> = Object.fromEntries(
  roleManagementMockData.map((role) => {
    const defaults = createDefaultRolePermissions();
    if (role.name === "AI助手") {
      return [role.id, {
        ...defaults,
        actionPermissions: {
          ...defaults.actionPermissions,
          删除: false,
          删除用户: false,
          停用用户: false,
        },
        fieldPermissions: {
          ...defaults.fieldPermissions,
          账号密钥摘要: "adminOnly",
          店铺授权信息: "adminOnly",
        },
      }];
    }
    if (role.name === "采购") {
      return [role.id, {
        ...defaults,
        fieldPermissions: {
          ...defaults.fieldPermissions,
          利润金额: "hidden",
          回款金额: "hidden",
          广告花费: "hidden",
        },
      }];
    }
    return [role.id, defaults];
  }),
);
