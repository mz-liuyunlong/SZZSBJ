/**
 * ItemIdLink.tsx — 商品ID(ItemID)沃尔玛跳转链接（2026-07-23 新增，隔离组件，零改旧逻辑）
 *
 * 需求：所有前端展示的商品ID渲染为可点击链接，新标签打开沃尔玛商品页。
 * 口径：仅沃尔玛平台的 ItemID 加链接；亚马逊(ASIN)/希音(平台SKC)等非沃尔玛保持纯文本，避免跳错。
 * 说明：本中台主数据链路(领星→FACT/DIM)均为 platform='walmart'，故未显式给出平台时默认按沃尔玛处理；
 *       多渠道页面(如清货中心)请用 isWalmart 显式门控。
 */
import type { CSSProperties } from "react";

// 沃尔玛商品页链接。用户口径为 walmart.com/ip/{itemid}；统一走 https + www（http/apex 均 301 到此，更稳）。
export function walmartItemUrl(itemId: string): string {
  return `https://www.walmart.com/ip/${encodeURIComponent(itemId)}`;
}

// 判定平台字符串是否沃尔玛；缺省(null/空)也视为沃尔玛（主数据均为 walmart）。
export function isWalmartPlatform(platform?: string | null): boolean {
  if (platform == null) return true;
  const p = String(platform).trim().toLowerCase();
  if (p === "") return true;
  return p === "walmart" || p === "沃尔玛" || p === "wm";
}

// 空值/占位符：不渲染链接，原样透出。
function isBlankId(raw: string): boolean {
  return raw === "" || raw === "-" || raw === "—" || raw === "空";
}

const LINK_STYLE: CSSProperties = { color: "#2563eb", textDecoration: "none" };

interface ItemIdLinkProps {
  itemId: string | number | null | undefined;
  /** 显式指定是否沃尔玛（优先级最高）。多渠道页(清货中心)按渠道门控时用它。 */
  isWalmart?: boolean;
  /** 平台字符串；未显式传 isWalmart 时据此判断。缺省视为沃尔玛。 */
  platform?: string | null;
  /** 链接文本额外样式（如需覆盖颜色等）。 */
  style?: CSSProperties;
}

export function ItemIdLink({ itemId, isWalmart, platform, style }: ItemIdLinkProps): JSX.Element {
  const raw = itemId == null ? "" : String(itemId).trim();
  if (isBlankId(raw)) return <>{raw}</>;
  const walmart = isWalmart ?? isWalmartPlatform(platform);
  if (!walmart) return <>{raw}</>;
  return (
    <a
      href={walmartItemUrl(raw)}
      target="_blank"
      rel="noopener noreferrer"
      style={{ ...LINK_STYLE, ...style }}
      title={`在沃尔玛打开商品 ${raw}`}
    >
      {raw}
    </a>
  );
}
