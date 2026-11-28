/** Read model: product IDs are strings, not globally unique across stores. */
export interface WooProductRow {
  id: string;
  storeId: string;
  store: string;
  name: string;
  sku: string;
  brands: string[];
  images: number;
  imageUrl: string | null;
  points: string[];
  descriptionLength: number;
  stockStatus: string;
  stockQuantity: number | null;
  price: string;
  regularPrice: string;
  currency: string | null;
  createdAt: string;
  listedAt: string | null;
  status: string;
  url: string;
  lastSyncedAt: string;
  sources: { account: string; storeId: string; itemId: string; storeName: string; url: string }[];
}
