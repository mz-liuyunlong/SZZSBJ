import {describe,it,expect} from "vitest";
import {samples,defaultConfig,score,grade,suggestion,bands,categoryStats} from "./nativeData";
describe("Owner original Demo native page fixture",()=>{
it("preserves original V4 SKU examples",()=>{expect(samples).toHaveLength(7);expect(samples[0].sku).toBe("YC00738");expect(categoryStats.length).toBeGreaterThan(0)});
it("blocks final grade until human market score",()=>{const row=samples.find(p=>p.market===null)!;expect(score(row,defaultConfig)).toBeNull();expect(grade(row,defaultConfig)).toBeNull();expect(suggestion(row,defaultConfig)).toBe(0)});
it("preserves confirmed procurement band ranges",()=>{expect(bands.S).toEqual([400,600]);expect(bands.A).toEqual([300,500]);expect(bands.B).toEqual([200,400]);expect(bands.C).toEqual([150,250]);expect(bands.D).toEqual([0,0])});
});
