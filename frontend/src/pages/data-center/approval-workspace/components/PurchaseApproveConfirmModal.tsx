import {useEffect, useState} from "react";
import {Alert, Form, InputNumber, Modal, Select, Spin, message} from "antd";
import {BarChartOutlined, InfoCircleOutlined, ShoppingCartOutlined} from "@ant-design/icons";
import type {ApprovalItem} from "../approvalTypes";
import {decideNewProductPurchase, fetchNewProductPurchaseStoreOptions, type PurchaseApprovalStoreOption} from "../approvalApi";
import "./PurchaseApproveConfirmModal.css";

type Props = {
  item?: ApprovalItem;
  onCancel(): void;
  onSaved(): void;
};

export default function PurchaseApproveConfirmModal({item,onCancel,onSaved}:Props) {
  const [stores,setStores] = useState<PurchaseApprovalStoreOption[]>([]);
  const [storeId,setStoreId] = useState<string>();
  const [quantity,setQuantity] = useState<number|null>(null);
  const [loading,setLoading] = useState(false);
  const [saving,setSaving] = useState(false);
  const [loadError,setLoadError] = useState("");

  useEffect(() => {
    if (!item) return;
    let active = true;
    setStores([]);
    setStoreId(item.purchase_details?.store_id ?? undefined);
    setQuantity(item.purchase_details?.requested_qty ?? null);
    setLoading(true);
    setLoadError("");
    void fetchNewProductPurchaseStoreOptions(item.id).then(data => {
      if (!active) return;
      setStores(data.stores);
      setStoreId(data.source_store_id);
    }).catch((error:unknown) => {
      if (!active) return;
      setLoadError(error instanceof Error ? error.message : "采购店铺读取失败");
    }).finally(() => {if(active)setLoading(false);});
    return () => {active = false;};
  },[item?.id]);

  const requested = item?.purchase_details?.requested_qty ?? null;
  const suggested = item?.purchase_details?.suggested_qty ?? null;
  const validQty = quantity !== null && Number.isSafeInteger(quantity) && quantity >= 1 && quantity <= 100000;
  const validStore = !!storeId && stores.some(store => store.store_id === storeId);
  const submit = async () => {
    if (!item || saving || loading || !validStore || !validQty || !storeId || quantity === null) return;
    setSaving(true);
    try {
      await decideNewProductPurchase(item.id,item.version,"approved","",{
        purchase_store_id:storeId,
        approved_qty:quantity,
      });
      message.success("采购审批通过，采购店铺与批准数量已记录");
      onSaved();
    } catch(error) {
      message.error(error instanceof Error ? error.message : "采购审批失败，请检查申请状态和店铺权限");
    } finally {setSaving(false);}
  };

  return <Modal
    className="np-purchase-approve-confirm"
    open={Boolean(item)}
    destroyOnHidden
    width={620}
    centered
    title={<span className="np-purchase-approve-confirm__title"><ShoppingCartOutlined/>确认批准采购</span>}
    okText="确认批准"
    cancelText="取消"
    onOk={() => {void submit();}}
    onCancel={onCancel}
    okButtonProps={{loading:saving,disabled:loading || !validStore || !validQty || !!loadError}}
    cancelButtonProps={{disabled:saving}}
    closable={!saving}
    maskClosable={!saving}
  >
    <Alert type="info" showIcon icon={<InfoCircleOutlined/>}
      message="请确认采购店铺与采购数量，可根据实际情况进行调整。"/>
    <h3 className="np-purchase-approve-confirm__section">采购信息</h3>
    {loading ? <div className="np-purchase-approve-confirm__loading"><Spin/> 正在核实授权店铺…</div> : null}
    {loadError ? <Alert type="error" message={loadError} description="店铺未核实，暂不能批准，请核实当前账号的店铺维度数据。" showIcon/> : null}
    <Form layout="horizontal" colon={false} labelCol={{span:6}} wrapperCol={{span:18}} requiredMark>
      <Form.Item label="采购店铺" required>
        <Select
          showSearch
          optionFilterProp="label"
          placeholder="请选择采购店铺"
          value={storeId}
          disabled={loading || !!loadError || saving}
          options={stores.map(store=>({value:store.store_id,label:`Walmart US – ${store.store_name}`}))}
          onChange={setStoreId}
          notFoundContent="没有当前数据账号内可用的 Walmart 店铺"
        />
      </Form.Item>
      <Form.Item label="采购数量" required>
        <div className="np-purchase-approve-confirm__quantity-line">
          <InputNumber min={1} max={100000} precision={0}
            value={quantity} disabled={saving}
            onChange={value=>setQuantity(value)}
            aria-label="采购数量"/>
          <span className="np-purchase-approve-confirm__suggestion"><BarChartOutlined/>系统建议：{suggested === null ? "—" : `${suggested} 件`}</span>
        </div>
      </Form.Item>
    </Form>
    {requested !== null && quantity !== null && quantity !== requested ?
      <p className="np-purchase-approve-confirm__changed">本次批准数量 {quantity} 件（运营申请 {requested} 件）；审批后保留原始申请数量。</p> : null}
  </Modal>;
}
// SZZSBJ_PURCHASE_APPROVE_STORE_QTY_V1

// SZZSBJ_PURCHASE_CONFIRM_VISUAL_V3
// SZZSBJ_PURCHASE_CONFIRM_REFERENCE_PARITY_V4
