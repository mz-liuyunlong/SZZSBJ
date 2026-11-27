// Shared display types for the authoritative SKU progress API.
export type ListingProgress = {
  key: string; id: string; msku: string; store: string; owner: string;
  listing: "已上架" | "未上架" | ""; date: string;
  strike: string; effect: "已生效" | "未生效" | ""; price: string;
};
export type SkuProgressRow = {
  key: string; sku: string; name: string; dev: string; owner: string;
  image: string; previewImage: string; ls: ListingProgress[];
  unmatchedListingStatus: "未上架" | "";
  purchasePlan: "未提交"; independentSite: "未提交";
};
export const emptyListing = (listing: "未上架" | "" = ""): ListingProgress => ({key:"no-match",id:"",msku:"",store:"",owner:"",listing,date:"",strike:"",effect:"",price:""});
