import { beforeEach, describe, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import { listIntegrationSyncTasks } from "@/pages/data-center/integrationSyncTaskApi";

vi.mock("@/api/backendApi", () => ({ backendRequest: vi.fn() }));

const domesticNames: Record<string, string> = {
  domesticWarehouseStatement: "批次看板－入库流水同步",
  domesticBatchDetailList: "批次看板－批次库存同步",
  domesticBatchStatementList: "国内仓－批次流水同步",
  domesticInventoryDetails: "国内仓－库存明细同步",
  domesticWarehouseList: "国内仓－仓库资料同步",
};

describe("domestic sync task display", () => {
  beforeEach(() => {
    vi.mocked(backendRequest).mockImplementation(async (path: string) => {
      if (path.startsWith("/api/integrations/interfaces")) {
        return {
          data: {
            items: Object.keys(domesticNames).map((interfaceKey) => ({
              id: interfaceKey,
              provider: "lingxing",
              interface_key: interfaceKey,
              display_name: "Lingxing Domestic English Name",
              request_kind: "offset_page",
              outbound_enabled: false,
            })),
          },
        };
      }
      return { data: { items: [] } };
    });
  });

  it("shows the confirmed Chinese task name, domestic module and closed description", async () => {
    const { rows } = await listIntegrationSyncTasks();
    expect(rows).toHaveLength(5);
    for (const row of rows) {
      expect(row.taskName).toBe(domesticNames[row.interfaceKey]);
      expect(row.module).toBe("国内仓");
      expect(row.description).toBe(
        `${row.taskName}。可开启定时同步；入库流水和批次流水未指定日期时，按上海日期同步最近 90 天。`,
      );
      expect(row.interfaceName).not.toContain("Lingxing");
      expect(row.taskName).not.toBe("Lingxing Domestic English Name");
    }
  });
});
