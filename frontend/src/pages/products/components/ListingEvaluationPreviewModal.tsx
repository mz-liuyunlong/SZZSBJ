/** Read-only evidence details. Never presents provisional candidates as published grades. */
import { useEffect, useState } from "react";
import { Alert, Descriptions, Modal, Skeleton, Tag, Typography } from "antd";
import { backendRequest } from "@/api/backendApi";
import type { ListingManagementRow } from "@/pages/products/listingManagementData";

interface Diagnostic {
  listing_id: string;
  cutoff_la: string;
  current_lifecycle: string | null;
  current_grade: string | null;
  lifecycle_candidate: string | null;
  grade_candidate: string | null;
  lifecycle_evidence_reason: string | null;
  valid_short: number;
  valid_medium: number;
  valid_stock_days_30: number;
  observed_stock_days_7: number;
  low_stock_days_7: number;
  weighted_margin_percent: string | null;
  missing_evidence: string[];
  published: boolean;
}
interface Props {
  listing: ListingManagementRow | null;
  onClose: () => void;
}
export default function ListingEvaluationPreviewModal({ listing, onClose }: Props) {
  const [data, setData] = useState<Diagnostic | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!listing) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setLoading(true);
      setData(null);
      setError("");
      try {
        const result = await backendRequest<Diagnostic>(
          `/api/listings/evaluation-preview?listing_id=${encodeURIComponent(listing.id)}`,
        );
        if (active) setData(result.data);
      } catch {
        if (active) setError("试算接口尚未启用，或当前账号无权访问。没有写入任何评级结果。");
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [listing]);

  return (
    <Modal title="Listing 计算依据（只读试算）" open={listing !== null}
      onCancel={onClose} footer={null} destroyOnHidden width={680}>
      <Alert type="warning" showIcon style={{ marginBottom: 16 }}
        message="候选值仅供核查，不代表正式生命周期或等级"
        description="财务、广告及审批来源未完成验证之前，不自动覆盖Listing当前字段。" />
      {listing && <Typography.Text type="secondary">Item ID：{listing.productId} · MSKU：{listing.msku}</Typography.Text>}
      {loading ? <Skeleton active /> : error ? <Alert type="info" showIcon message={error} style={{ marginTop: 12 }} />
        : data ? (
          <>
            <Descriptions bordered size="small" column={2} style={{ marginTop: 16 }}>
              <Descriptions.Item label="业务截止日期">{data.cutoff_la}</Descriptions.Item>
              <Descriptions.Item label="发布状态"><Tag>未发布</Tag></Descriptions.Item>
              <Descriptions.Item label="当前生命周期">{data.current_lifecycle ?? "未设置"}</Descriptions.Item>
              <Descriptions.Item label="生命周期候选">{data.lifecycle_candidate ?? "证据不足"}</Descriptions.Item>
              <Descriptions.Item label="当前等级">{data.current_grade ?? "未设置"}</Descriptions.Item>
              <Descriptions.Item label="等级候选">{data.grade_candidate ?? "待评级"}</Descriptions.Item>
              <Descriptions.Item label="7 / 14天有效财务日">{data.valid_short} / {data.valid_medium}</Descriptions.Item>
              <Descriptions.Item label="加权毛利率">{data.weighted_margin_percent == null ? "-" : `${data.weighted_margin_percent}%`}</Descriptions.Item>
              <Descriptions.Item label="最近7天WFS快照">{data.observed_stock_days_7}天</Descriptions.Item>
              <Descriptions.Item label="最近7天低库存">{data.low_stock_days_7}天</Descriptions.Item>
              <Descriptions.Item label="30天有效有货日">{data.valid_stock_days_30}天</Descriptions.Item>
              <Descriptions.Item label="阶段依据">{data.lifecycle_evidence_reason ?? "未知"}</Descriptions.Item>
            </Descriptions>
            <Typography.Title level={5} style={{ marginTop: 20 }}>尚缺少的证据</Typography.Title>
            {data.missing_evidence.length ? data.missing_evidence.map(code => (
              <Tag key={code} style={{ marginBottom: 6 }}>{code}</Tag>
            )) : <Typography.Text>无</Typography.Text>}
          </>
        ) : null}
    </Modal>
  );
}
