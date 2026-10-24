/** This card counts authorized Huizhou PK exceptions, separately from inbound-table row counts. */
import { Alert } from "antd";
import { useQuery } from "@tanstack/react-query";
import { getWarehouseSummary } from "../packing/packingWarehouseApi";
import { initialPackingWarehouseFilters } from "../packing/packingWarehouseTypes";
export default function DomesticPackingRiskCard({ scope }: { scope: string }) {
  const query = useQuery({ queryKey: ["domestic-packing-risk", scope], queryFn: ({ signal }) => getWarehouseSummary({ ...initialPackingWarehouseFilters(), status: "all" }, signal), retry: false });
  return query.error ? <Alert type="warning" message="打包异常统计读取失败" /> : <Alert type={query.data?.data.overpack_blocked ? "warning" : "info"} message={`超发待补入库 ${query.data?.data.overpack_blocked ?? "—"} 张`} description="惠州仓当前全部可见 PK；不随入库表格的店铺或日期筛选变化。" />;
}
