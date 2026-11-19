import { useState, type ReactNode } from "react";
import { Popover } from "antd";
import "./newProductCorrectionPopover.css";

export type CorrectionSubmission = { ok: boolean; error?: string };

type CorrectionDimension = "speed" | "ad" | "profit" | "trust";

type Props = {
  dimension: CorrectionDimension;
  currentScore: number | null;
  children: ReactNode;
  onSubmit: (requestedScore: number, reason: string) => Promise<CorrectionSubmission> | CorrectionSubmission;
};

const dimensionTitle: Record<CorrectionDimension, string> = {
  speed: "出单速度",
  ad: "广告有效性",
  profit: "利润空间",
  trust: "数据可信度",
};

/** PR337_CORRECTION_POPOVER_V7: scoped input state; no parent page rerender while typing. */
export default function NewProductCorrectionPopover({
  dimension,
  currentScore,
  children,
  onSubmit,
}: Props) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [requested, setRequested] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");

  const changeOpen = (next: boolean) => {
    if (next) {
      setRequested(currentScore === null ? "" : currentScore.toFixed(2));
      setReason("");
      setError("");
    }
    setOpen(next);
  };

  const submit = async () => {
    if (saving) return;
    const value = requested.trim();
    // Only actual numbers 0..10, with at most two decimal places.
    const validNumber = /^(?:[0-9](?:\.\d{1,2})?|10(?:\.0{1,2})?)$/.test(value);
    if (!validNumber) {
      setError("请输入0–10之间的分数，最多保留两位小数");
      return;
    }
    const explanation = reason.trim();
    if (explanation.length < 5 || explanation.length > 500) {
      setError("修正依据至少5个字，最多500字");
      return;
    }
    setSaving(true);
    try {
      const result = await onSubmit(Number(value), explanation);
      if (result.ok) changeOpen(false);
      else setError(result.error || "保存修正失败");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存修正失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Popover
      trigger="click"
      placement="topRight"
      open={open}
      onOpenChange={changeOpen}
      arrow
      autoAdjustOverflow
      rootClassName="np-score-correction-popover"
      zIndex={1200}
      content={
        <div className="np-score-correction-panel">
          <div className="np-score-correction-head">
            <strong>修正分数 · {dimensionTitle[dimension]}</strong>
            <span className="np-score-correction-current">
              当前评分 <b>{currentScore === null ? "—" : currentScore.toFixed(2)}</b><em> / 10</em>
            </span>
          </div>
          <div className="np-score-correction-field">
            <label htmlFor={`np-correction-score-${dimension}`}>修正分数 <span>*</span></label>
            <input
              id={`np-correction-score-${dimension}`}
              type="number"
              inputMode="decimal"
              min="0"
              max="10"
              step="0.01"
              placeholder="0.00–10.00"
              value={requested}
              onChange={(event) => {setRequested(event.target.value);setError("");}}
            />
          </div>
          <div className="np-score-correction-field np-score-correction-reason">
            <label htmlFor={`np-correction-reason-${dimension}`}>修正依据 <span>*</span></label>
            <div className="np-score-correction-textarea-wrap">
              <textarea
                id={`np-correction-reason-${dimension}`}
                rows={3}
                maxLength={500}
                placeholder="请填写修正依据…"
                value={reason}
                onChange={(event) => {setReason(event.target.value);setError("");}}
              />
              <span className="np-score-correction-count">{reason.length} / 500</span>
            </div>
          </div>
          {error ? <div className="np-score-correction-error" role="alert">{error}</div> : null}
          <div className="np-score-correction-footer">
            <button type="button" className="np-score-correction-cancel" onClick={() => changeOpen(false)}>取消</button>
            <button type="button" className="np-score-correction-submit" onClick={submit} disabled={saving}>保存修正</button>
          </div>
        </div>
      }
    >
      {children}
    </Popover>
  );
}
