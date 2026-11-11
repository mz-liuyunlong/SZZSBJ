/** PR337_TRACKING_SINGLE_SOURCE_V4
 * Read-only layout fixtures, only for the seven original PR337 local Mock products.
 * The dashboard still receives ONE Product[]; real API results bypass this helper.
 * Never send these records to APIs or persist them.
 */
import type { Grade, Product } from './nativeData';
import type { TrackingProduct } from './trackingBoardMetrics';

const ORIGINAL_MOCK_IDS = new Set([
  'NP-1001', 'NP-1002', 'NP-1003', 'NP-1004', 'NP-1005', 'NP-1006', 'NP-1007',
]);
const fixturePrefix = 'TRACK-LAYOUT-';
export const isTrackingVisualSample = (p:Product):boolean => p.id.startsWith(fixturePrefix);

/** Real/business records, including partially received API records, are NEVER padded. */
export function isOriginalPr337Mock(products:readonly Product[]):boolean {
  return products.length === ORIGINAL_MOCK_IDS.size &&
    products.every(p => ORIGINAL_MOCK_IDS.has(p.id)) &&
    new Set(products.map(p => p.id)).size === ORIGINAL_MOCK_IDS.size;
}

const examples = [
  ['厨房用品', '榨汁器与压汁工具', '手动柠檬榨汁器'],
  ['厨房用品', '厨房切碎工具', '多功能肉馅压碎器'],
  ['厨房用品', '厨房过滤用品', '不锈钢土豆压泥器'],
  ['收纳整理', '透明收纳箱', '透明叠放储物箱'],
  ['收纳整理', '零食收纳容器', '多格零食分装盒'],
  ['收纳整理', '抽屉整理用品', '抽屉隔板收纳套装'],
  ['家居清洁', '除尘工具', '伸缩除尘掸子套件'],
  ['家居清洁', '厨房清洁用品', '可替换刷头清洁刷'],
  ['家居装饰', '墙面保护用品', '防撞墙面保护贴'],
  ['办公用品', '桌面整理', '双层桌面文件架'],
  ['宠物用品', '宠物护理', '宠物毛发清理滚筒'],
  ['宠物用品', '宠物喂食', '折叠便携宠物食盆'],
  ['庭院花园', '浇水工具', '手持园艺喷头'],
  ['庭院花园', '园艺收纳', '可折叠园艺收纳袋'],
  ['五金工具', '测量工具', '多功能定位尺'],
  ['五金工具', '手持工具', '可调节套筒扳手'],
  ['汽车用品', '车内清洁', '汽车内饰清洁套装'],
  ['汽车用品', '车用收纳', '后备箱分隔收纳盒'],
  ['运动户外', '户外便携配件', '防水露营挂扣'],
  ['浴室用品', '淋浴收纳', '免打孔浴室置物篮'],
  ['衣物护理', '衣物除毛', '可水洗衣物除毛刷'],
  ['烘焙用品', '烘焙模具', '可拆卸蛋糕模具'],
  ['旅行用品', '旅行分装', '旅行洗护分装瓶'],
  ['电子配件', '线材收纳', '桌面磁吸理线器'],
] as const;
const operators = ['王宁','陈晨','李敏','赵敏','李倩','陈佳','刘洋','周悦'];
const developers = ['王宁','李敏','陈晨','孙婷','刘洋','张琳'];
const gradeSeries:Grade[] = ['S','A','B','C','B','A','Pass','D','B','C','S','A','B','Pass','C','D'];
const statusSeries = ['打品成功','继续观察','打品失败','打品成功','需要优化','继续观察','等待开售','打品失败'] as const;

const formatUTC = (epoch:number) => new Date(epoch).toISOString().slice(0,10);
/** Make one bounded set of typed rows. This is NOT another selectable data source. */
export function withTrackingVisualSamples(products:Product[], anchorISO:string):Product[] {
  if (!isOriginalPr337Mock(products)) return products;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(anchorISO) ||
    Number.isNaN(Date.parse(`${anchorISO}T00:00:00Z`)) ||
    formatUTC(Date.parse(`${anchorISO}T00:00:00Z`))!==anchorISO) return products;
  const anchor=Date.parse(`${anchorISO}T00:00:00Z`);
  const daysAgo=(days:number)=>formatUTC(anchor-days*86400000);
  const added=Array.from({length:48},(_,i):TrackingProduct=>{
    const [category,secondaryCategory,name]=examples[(i*7+Math.floor(i/12))%examples.length];
    const arrivalAge=2+(i*11)%124;
    const launchedAge=arrivalAge+5+(i%11);
    const tracking=statusSeries[(i*3+Math.floor(i/8))%statusSeries.length];
    const initialGrade=gradeSeries[(i*5+Math.floor(i/10))%gradeSeries.length];
    const approvedQty=100+(i*31)%310;
    const sold30=5+(i*9)%90;
    const sold60=sold30+(i*3)%130;
    const sold90=sold60+(i*7)%90;
    const market=i%6===0?null:Math.max(0,Math.min(10,6+(i*7)%5));
    const row:TrackingProduct={
      id:`${fixturePrefix}${String(i+1).padStart(3,'0')}`,
      sku:`YC${String(20000+i+1).padStart(5,'0')}`,
      item:`${18430941000+i+1}`,
      name,owner:operators[(i*5)%operators.length],operator:operators[(i*5)%operators.length],
      developer:developers[(i*3+Math.floor(i/8))%developers.length],
      category,secondaryCategory,initialGrade,
      days:launchedAge,market,marketReason:market===null?'':'已记录市场竞争评价依据',
      scores:{speed:5+(i*3)%6,ad:4+(i*5)%7,profit:5+(i*7)%6,trust:5+(i*2)%6},
      penalties:0,penaltyFlags:[],roi:.65+((i*7)%90)/100,
      margin:12+(i*13)%18,acos:18+(i*11)%42,
      clicks:35+(i*19)%320,orders:2+(i*5)%38,qty7:2+(i*3)%19,
      sales30:sold30,spend:28+(i*17)%210,unitCost:4+(i*3)%12,
      price:12.99+(i*5)%27,inventory:5+(i*23)%210,risk:'',
      status:market===null?'待市场评分':'已批准',
      suggested:null,requestQty:null,requestReason:'',tracking,
      sales60:sold60,sales90:sold90,margin60:12+(i*11)%18,acos60:19+(i*7)%42,
      launch:daysAgo(launchedAge),arrival:daysAgo(arrivalAge),
      sold30,sold60,sold90,actualQty:approvedQty,reasonFailure:tracking==='打品失败'?'经营表现未达标':'',
    };
    return row;
  });
  return [...products,...added];
}
