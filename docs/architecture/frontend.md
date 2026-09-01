# 前端架构规则

## 1. 固定技术栈

```text
React + TypeScript + Vite react-ts + Ant Design + ProComponents + React Router + Zustand + ECharts
```

## 2. 推荐目录

```text
frontend/
├─ src/
│  ├─ app/
│  ├─ config/
│  │  └─ navigation.ts
│  ├─ layouts/
│  │  └─ MainLayout.tsx
│  ├─ router/
│  │  └─ routes.tsx
│  ├─ components/
│  │  ├─ PageShell.tsx
│  │  ├─ ComingSoonPage.tsx
│  │  └─ LegacyPageWrapper.tsx
│  ├─ pages/
│  ├─ services/
│  │  └─ apiClient.ts
│  ├─ hooks/
│  ├─ stores/
│  ├─ types/
│  └─ utils/
```

## 3. 导航规则

- 所有菜单只允许从 `src/config/navigation.ts` 生成。
- 禁止在页面组件里硬编码菜单。
- 禁止在 `routes.tsx` 里维护第二套路由菜单。
- 页面内部 Tab 不作为左侧菜单展示。
- API 文档作为 `数据中心 > API文档` 页面。
- 帮助文档不作为菜单，固定通过页面右上角 `?` 进入。

## 4. 页面配置字段

每个页面配置必须包含：

```ts
{
  key: string;
  title: string;
  path: string;
  phase: number;
  status: 'planned' | 'building' | 'testing' | 'ready' | 'disabled' | 'hidden';
  source: 'pending' | 'legacy_mysql' | 'new_postgres' | 'cache' | 'openapi' | 'mixed';
  sourceTables: string[];
  readOnly: boolean;
  migrationMode: 'pending' | 'legacy' | 'iframe' | 'rewrite' | 'native';
  permissionKey: string;
  actions?: PageAction[];
  tabs?: PageTab[];
  help: {
    enabled: boolean;
    title: string;
    helpUrl: string;
    openInNewTab: true;
  };
}
```

## 5. PageShell 规则

所有页面必须通过 `PageShell` 渲染。`PageShell` 负责统一展示：

```text
页面标题
页面状态
数据来源
数据范围
更新时间
API文档入口，如果有权限
? 帮助入口
```

业务页面不得自己单独实现帮助按钮。

## 6. API Client 规则

- 页面不允许直接写 `fetch`。
- 所有请求必须走 `services/apiClient.ts`。
- apiClient 必须统一处理 `request_id`、错误码、登录状态、权限失败。
- 前端不能解析后端异常字符串，只能根据 `error.code` 判断。

## 7. 组件抽象规则

必须抽组件：

```text
同一 UI 出现 3 次
同一筛选表单出现 2 次
同一表格列逻辑出现 2 次
同一 API 请求逻辑出现 2 次
```

不要过度抽象：

```text
只出现 1 次
业务口径还没稳定
字段仍在调整
抽象后更难读
```


## 8. 页面状态与只读属性

`status` 只表示页面建设状态。

允许值固定为：

```text
planned / building / testing / ready / disabled / hidden
```

页面是否只读必须使用 `readOnly: true/false`，不得使用 `status: 'readonly'`。
`legacy`、`iframe`、`deprecated` 不得作为 `PageStatus` 值。
