/** User-management No-API acceptance data; replace it when a real permission API is approved. */
import {
  userRoleOptions,
  type UserManagementRow,
  type UserRoleName,
  type UserStatus,
} from "@/pages/settings/userManagementTypes";

const baseUsers: UserManagementRow[] = [
  {
    id: "user-001",
    username: "AI_YunYing",
    realName: "AI-小运营",
    phone: "-",
    email: "-",
    status: "启用",
    roles: ["AI助手"],
    createdAt: "2026-09-12 10:30",
    lastLoginAt: "2026-09-13 03:58",
  },
  {
    id: "user-002",
    username: "WANGQIAOTING",
    realName: "王巧婷",
    phone: "-",
    email: "-",
    status: "启用",
    roles: ["运营"],
    createdAt: "2026-09-11 16:23",
    lastLoginAt: "2026-09-12 22:19",
  },
  {
    id: "user-003",
    username: "LIUQING02",
    realName: "李清清",
    phone: "-",
    email: "-",
    status: "启用",
    roles: ["运营", "采购"],
    createdAt: "2026-08-04 10:39",
    lastLoginAt: "2026-09-07 09:12",
  },
  {
    id: "user-004",
    username: "CAIHUOHUI",
    realName: "蔡焕姬",
    phone: "-",
    email: "-",
    status: "停用",
    roles: ["仓库管理"],
    createdAt: "2026-07-14 15:28",
    lastLoginAt: "2026-08-31 09:00",
  },
  {
    id: "user-005",
    username: "ZHANGLEI03",
    realName: "张磊",
    phone: "-",
    email: "-",
    status: "启用",
    roles: ["财务管理"],
    createdAt: "2026-03-26 10:03",
    lastLoginAt: "2026-09-01 16:01",
  },
  {
    id: "user-006",
    username: "SKU-WUXIANLING",
    realName: "吴晓玲",
    phone: "-",
    email: "-",
    status: "启用",
    roles: ["运营"],
    createdAt: "2026-03-24 10:06",
    lastLoginAt: "2026-09-12 15:00",
  },
];

const realNames = [
  "陈一舟",
  "林晓",
  "周琳",
  "赵明",
  "许悦",
  "黄小曼",
  "罗成",
  "何静",
  "孙琪",
  "高航",
  "梁雨",
  "唐宁",
];
const namePrefixes = ["OPS", "BUY", "WHS", "FIN", "ADS", "SKU", "LIST", "DATA"];
const statuses: UserStatus[] = ["启用", "启用", "启用", "启用", "停用"];

const generatedUsers: UserManagementRow[] = Array.from({ length: 54 }, (_, index) => {
  const serial = String(index + 7).padStart(3, "0");
  const role = userRoleOptions[index % userRoleOptions.length];
  const secondRole = index % 6 === 0 ? userRoleOptions[(index + 2) % userRoleOptions.length] : undefined;
  const roles = [role, secondRole].filter(Boolean) as UserRoleName[];
  const month = String(index % 9 + 1).padStart(2, "0");
  const day = String(index % 27 + 1).padStart(2, "0");
  const hour = String(8 + index % 10).padStart(2, "0");
  const minute = String(index * 7 % 60).padStart(2, "0");

  return {
    id: `user-${serial}`,
    username: `${namePrefixes[index % namePrefixes.length]}_USER_${serial}`,
    realName: realNames[index % realNames.length],
    phone: index % 4 === 0 ? "-" : `138****${String(1000 + index).slice(-4)}`,
    email: index % 5 === 0 ? "-" : `user${serial}@example.com`,
    status: statuses[index % statuses.length],
    roles,
    createdAt: `2026-${month}-${day} ${hour}:${minute}`,
    lastLoginAt: index % 7 === 0 ? "-" : `2026-09-${String(index % 12 + 1).padStart(2, "0")} ${hour}:${minute}`,
  };
});

export const userManagementMockData: UserManagementRow[] = [
  ...baseUsers,
  ...generatedUsers,
];
