import {describe,expect,it} from 'vitest';
import * as XLSX from 'xlsx';
import {parseSellerSprite} from './importWorkbook';
function fixture(rows:number,translated:boolean){
 const wb=XLSX.utils.book_new();const grid=[['关键词','关键词翻译','月搜索量','月购买量','购买率','PPC竞价','建议竞价范围','相关ASIN']];
 for(let i=0;i<rows;i++)grid.push([`test storage ${i}`,translated?'测试收纳': '',i===0?'':String(i+1),String(i+2),0.1,'$0.51','$0.38 - $0.64','B012345678/B012345679']);
 XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(grid),'SellerSprite');
 XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet([['词语','出现频次'],['storage',rows]]),'Unique Words');
 XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet([['ASIN'],['B012345678'],['B012345679']]),'Asin');
 XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet([['Notes: synthetic fixture']]),'Notes');
 const raw=XLSX.write(wb,{bookType:'xlsx',type:'array'}) as ArrayBuffer;
 return {name:'synthetic.xlsx',size:raw.byteLength,arrayBuffer:async()=>raw} as File;
}
describe('SellerSprite import',()=>{
 it('reads four sheets and exactly 819 synthetic keyword rows',async()=>{const book=await parseSellerSprite(fixture(819,false));expect(book.keywords).toHaveLength(819);expect(book.roots[0]).toEqual({term:'storage',count:819});expect(book.asins).toHaveLength(2);expect(book.keywords[0].monthlySearches).toBeNull();expect(book.keywords[1].monthlySearches).toBe(2);expect(book.keywords[0].amazonPpc).toBe(.51);expect(book.keywords[0].translation).toBeNull()});
 it('keeps source translation and rejects unsupported file',async()=>{const book=await parseSellerSprite(fixture(2,true));expect(book.keywords[0].translation).toBe('测试收纳');expect(book.keywords[0].translationSource).toBe('file');await expect(parseSellerSprite({name:'bad.exe',size:100,arrayBuffer:async()=>new ArrayBuffer(100)} as File)).rejects.toThrow('仅支持')});
});