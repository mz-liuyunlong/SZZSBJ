import { beforeEach, describe, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import { fetchDailySalesRows } from "@/pages/sales/dailySalesApi";
import {
  fetchOrderProfitRows,
  fetchOrderProfitTrendPoints,
} from "@/pages/sales/orderProfitApi";

vi.mock("@/api/backendApi", () => ({ backendRequest: vi.fn() }));

const backendRequestMock = vi.mocked(backendRequest);
const meta = {
  latest_calculated_at: null,
  page: 1,
  page_size: 50,
  total: 0,
  partial: false,
  input_missing: false,
};

describe("profit field access null handling", () => {
  beforeEach(() => {
    backendRequestMock.mockReset();
  });

  it("keeps a restricted daily-sales summary profit as null", async () => {
    backendRequestMock.mockResolvedValueOnce({
      data: {
        items: [],
        summary: {
          sales_qty: "3",
          order_count: "2",
          sales_amount: "39.99",
          sales_currency_code: "USD",
          order_profit_amount: null,
          order_profit_currency_code: null,
          ad_spend_amount: "5.25",
          sem_ad_spend_amount: "0",
          total_ad_spend_amount: "5.25",
          ad_spend_currency_code: "USD",
          refund_event_qty: "0",
          refund_event_amount: "0",
          refund_loss_amount: "0",
          refund_event_currency_code: "USD",
          wfs_available_quantity: null,
        },
      },
      meta,
    } as never);

    const result = await fetchDailySalesRows({});

    expect(result.summary?.orderProfitAmount).toBeNull();
  });

  it("keeps restricted order-profit summary and trend values as null", async () => {
    backendRequestMock
      .mockResolvedValueOnce({
        data: {
          items: [],
          summary: {
            sales_qty: "3",
            order_count: "2",
            sales_amount: "39.99",
            sales_currency_code: "USD",
            return_qty: "0",
            refund_amount: "0",
            refund_loss_amount: "0",
            refund_currency_code: "USD",
            order_profit_amount: null,
            order_profit_currency_code: null,
            ad_spend_amount: "5.25",
            sem_ad_spend_amount: "0",
            total_ad_spend_amount: "5.25",
            ad_spend_currency_code: "USD",
            ad_ratio: "0.13",
          },
        },
        meta,
      } as never)
      .mockResolvedValueOnce({
        data: {
          items: [{
            date: "2026-10-17",
            sales_qty: "3",
            order_count: "2",
            sales_amount: "39.99",
            sales_currency_code: "USD",
            return_qty: "0",
            refund_amount: "0",
            refund_loss_amount: "0",
            refund_currency_code: "USD",
            order_profit_amount: null,
            order_profit_currency_code: null,
            profit_margin: null,
            ad_spend_amount: "5.25",
            sem_ad_spend_amount: "0",
            total_ad_spend_amount: "5.25",
            ad_spend_currency_code: "USD",
            ad_ratio: "0.13",
          }],
        },
        meta: null,
      } as never);

    const rows = await fetchOrderProfitRows({});
    const trend = await fetchOrderProfitTrendPoints({});

    expect(rows.summary?.orderProfitAmount).toBeNull();
    expect(trend[0].orderProfit).toBeNull();
    expect(trend[0].profitMargin).toBeNull();
  });
});
