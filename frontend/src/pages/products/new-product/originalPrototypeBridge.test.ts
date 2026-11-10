import {describe,expect,it} from "vitest";
import {injectOriginalPrototype} from "./originalPrototypeBridge";
import workflow from "./original/new_product_analysis_demo_v4.html?raw";
import dashboard from "./original/new_product_analysis_board.html?raw";
describe("actual owner HTML prototypes",()=>{
it("retains V4 workflow and every original dialog",()=>{
const doc=injectOriginalPrototype(workflow,"workflow");
expect(doc).toContain('id="page-analysis"');
expect(doc).toContain('id="page-tracking"');
expect(doc).toContain("function renderScoreCorrections(");
expect(doc).toContain("function openApproval(");
expect(doc).toContain("function openConfig(");
expect(doc).toContain("np-original-navigate");
});
it("retains separate dashboard charts and interactions",()=>{
const doc=injectOriginalPrototype(dashboard,"dashboard");
expect(doc).toContain("function renderNewDashboard(");
expect(doc).toContain("function renderLaunchDashboard(");
expect(doc).toContain("function renderDashboard(");
expect(doc).toContain("np-original-set-page");
});
it("refuses incomplete HTML",()=>{
expect(()=>injectOriginalPrototype("<div />","workflow")).toThrow("Original HTML prototype is incomplete");
});
});
