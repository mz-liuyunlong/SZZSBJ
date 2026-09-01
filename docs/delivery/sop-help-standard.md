# 页面帮助与 SOP 标准

## 1. 最终规则

```text
API 文档 = 数据中心里的开发/维护入口，不给所有人看。
帮助文档 / SOP = 每个页面右上角固定小问号，打开新标签页跳到对应文章。
公司其他 SOP = 统一进入帮助中心 / SOP 中心管理。
```

## 2. 页面右上角帮助

每个正式页面必须通过 `PageShell` 统一显示：

```text
? 帮助
```

点击后：

```text
window.open(help.helpUrl, '_blank', 'noopener,noreferrer')
```

业务页面不能自己单独实现帮助按钮。

## 3. navigation.ts 配置

```ts
help: {
  enabled: true,
  title: '每日销售使用说明',
  helpUrl: '/help/sales/daily-sales',
  openInNewTab: true,
}
```

没有 `help` 配置或 SOP 文档的页面，不允许标记为 `ready`。

## 4. SOP 目录

```text
docs/sop/
├─ dashboard/
├─ products/
├─ sales/
├─ ads/
├─ aftersales/
├─ warehouse/
├─ finance/
├─ operations/
├─ purchase/
├─ ai-center/
├─ data-center/
├─ statistics/
├─ settings/
└─ company/
```

`company/` 用于公司通用 SOP，如退款处理、采购审批、刷单流程、测评流程、客服处理。

## 5. SOP 模板

每篇 SOP 必须包含：

```text
功能位置
这个页面是干嘛的
谁需要使用
它有什么用
操作步骤
字段说明
数据来源
权限说明
常见问题
注意事项
相关页面
版本记录
```

高风险功能额外包含：

```text
风险说明
是否可回滚
审计记录在哪里
出错后怎么处理
```

## 6. 功能完成标准

```text
功能完成 = 页面/API完成 + 测试通过 + API文档完成 + 用户SOP完成 + 页面右上角帮助入口可用 + 开发交接完成
```
