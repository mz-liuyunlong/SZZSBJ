import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import SearchTermsPage from "./SearchTermsPage";
const page={key:"ads_search_terms",title:"搜索词",path:"/ads/search-terms",phase:1,status:"building",source:"new_postgres",sourceTables:[],readOnly:false,migrationMode:"native",permissionKey:"ads.search_terms.view",help:{enabled:true,title:"搜索词",helpUrl:"/help/ads/search_terms",openInNewTab:true}} as const;
describe("SearchTermsPage",()=>{
 it("renders the confirmed SP workbench controls without mock rows",()=>{
  render(<MemoryRouter><SearchTermsPage page={page}/></MemoryRouter>);
  expect(screen.getByText("全部 SP")).toBeInTheDocument();
  expect(screen.getByText("自动广告")).toBeInTheDocument();
  expect(screen.getByText("手动广告")).toBeInTheDocument();
  expect(screen.getByText("搜索词汇总")).toBeInTheDocument();
  expect(screen.getByText("活动明细")).toBeInTheDocument();
 });
});
