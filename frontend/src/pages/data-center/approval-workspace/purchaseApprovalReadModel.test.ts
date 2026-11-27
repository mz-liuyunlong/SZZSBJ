import { describe, expect, it } from 'vitest';
import { verifiedPurchaseListing, verifiedPurchaseSku, verifiedUnitCost, verifiedUnitProfitUsd } from './purchaseApprovalReadModel';
import type { Identity, NewProductListing, PageResponse } from '@/pages/products/new-product/newProductBusinessApi';
import parent from './components/ApprovalBusinessDetailDrawer.tsx?raw';
import drawer from './components/PurchaseApprovalDecisionDrawer.tsx?raw';

const identity: Identity = {source_account_ref:'primary',store_id:'2603',item_id:'12345678901'};
const row = (patch: Partial<Identity> = {}) => ({listing:{...identity,...patch,local_sku:'YC00745'}} as NewProductListing);
const page = (items:NewProductListing[], total=items.length): PageResponse => ({items,total,page:1,page_size:200,rule_version:1});

describe('purchase drawer read performance', () => {
  it('opens from the list without waiting for data; actions require fresh approval detail', () => {
    expect(parent).toContain('open={Boolean(seed)}');
    expect(parent).not.toContain('open={Boolean(seed) && !pendingPurchase}');
    expect(parent).toContain('onAction={pendingPurchase || purchaseFetchFailed ? undefined : onAction}');
    expect(parent).toContain('staleTime:0, gcTime:60_000, retry:0');
    expect(drawer).toContain("detailState === 'ready' && record.status === 'submitted'");
    expect(drawer).not.toContain('fetchListingManagementRows');
    expect(drawer).not.toContain('listProductManagementSkus');
  });
  it('requires a complete page and an exact unique identity', () => {
    const expected = row();
    expect(verifiedPurchaseListing(page([row({source_account_ref:'other'}), expected]),identity)).toBe(expected);
    expect(verifiedPurchaseListing(page([expected],2),identity)).toBeNull();
    expect(verifiedPurchaseListing(page([expected,expected]),identity)).toBeNull();
    expect(verifiedPurchaseListing(page([row({store_id:'2602'})]),identity)).toBeNull();
    expect(verifiedPurchaseSku(expected,'YC00745')).toBe('YC00745');
    expect(verifiedPurchaseSku(expected,'WRONG')).toBeNull();
  });
  it('does not guess cost when redacted, incomplete or ambiguous', () => {
    const rows = [{sku:'YC00745',purchase_cost_cny:'27.5000'}];
    expect(verifiedUnitCost(rows,1,'YC00745')).toBe(27.5);
    expect(verifiedUnitCost(rows,2,'YC00745')).toBeNull();
    expect(verifiedUnitCost([...rows,...rows],2,'YC00745')).toBeNull();
    expect(verifiedUnitCost([{sku:'YC00745',purchase_cost_cny:null}],1,'YC00745')).toBeNull();
  });
  it('uses the same verified testing profit, never incomplete evidence', () => {
    const proof = {status:'scored',source:'new_products_testing_profit_full_history_v2',policy:'returns_ignored_samples_excluded_sample_ads_included',totals:{sales_units:'20',profit_usd:'30'}};
    expect(verifiedUnitProfitUsd(proof)).toBe(1.5);
    expect(verifiedUnitProfitUsd({...proof,status:'unverified'})).toBeNull();
    expect(verifiedUnitProfitUsd({...proof,totals:{sales_units:0,profit_usd:30}})).toBeNull();
  });
});
