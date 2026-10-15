import { describe, expect, it } from "vitest";
import { buildRolePermissionCatalog } from "@/pages/settings/roleManagementApi";

describe("buildRolePermissionCatalog", () => {
  it("keeps actions and fields under their owning page", () => {
    const catalog = buildRolePermissionCatalog({
      version: "2",
      modules: [{
        module_key: "settings",
        name: "设置",
        sort_order: 10,
        pages: [{
          page_key: "settings_user_management",
          name: "用户管理",
          permission_key: "page:settings:user-management:view",
          sort_order: 10,
          actions: [{
            permission_key: "action:settings:user-management:assign-role",
            name: "设置角色",
            description: "用户管理：设置角色",
            permission_type: "action",
            module_key: "settings",
            page_key: "settings_user_management",
            action_key: "assign_role",
            field_key: null,
            risk_level: "high",
            sort_order: 10,
          }],
          fields: [{
            permission_key: "field:settings:user-management:email",
            name: "邮箱",
            description: "用户管理字段：邮箱",
            permission_type: "field",
            module_key: "settings",
            page_key: "settings_user_management",
            action_key: null,
            field_key: "email",
            risk_level: "high",
            sort_order: 10,
          }],
        }],
      }],
    });

    expect(catalog.pagePermissionGroups).toEqual([{
      title: "设置",
      items: ["page:settings:user-management:view"],
    }]);
    expect(catalog.actionPermissionGroups).toEqual([{
      title: "设置 / 用户管理",
      items: ["action:settings:user-management:assign-role"],
    }]);
    expect(catalog.fieldPermissionGroups).toEqual([{
      title: "设置 / 用户管理",
      items: ["field:settings:user-management:email"],
    }]);
    expect(catalog.highRiskPermissions.has(
      "action:settings:user-management:assign-role",
    )).toBe(true);
  });
});
