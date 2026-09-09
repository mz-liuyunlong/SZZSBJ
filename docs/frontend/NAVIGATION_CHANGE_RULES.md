# Navigation Change Rules

## Required Rules

- AI 不得自行新增、删除、移动或重命名一级/二级导航。
- 导航 key、title、path、permission、status、help 和层级变更必须有负责人批准及独立范围。
- 页面可以是 `planned/no_api`，但不得因此重构导航或复制第二套菜单。
- Navigation config 是菜单 metadata 真源；route resolver、layout 和页面消费它，不复制完整 metadata。
- 新页面必须更新 Page Registry；权限和 route contract 同步 Review。
- Decorative emoji 不得作为导航 icon；icon 使用项目批准的组件 metadata。

导航目标或产品信息架构不清楚时停止确认，不用默认模板代替。
