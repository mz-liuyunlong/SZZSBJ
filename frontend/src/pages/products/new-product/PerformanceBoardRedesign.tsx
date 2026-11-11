/* PR337_UNIFIED_MOCK_ROWS_V75 */
/* PR337_BOARD_PROBLEM_KPIS_V74 */
/** PR337_BOARD_GRADE_SORT_V68 PR337_BOARD_SIDE_BY_SIDE_FAIL_GRADE_V69 PR337_BOARD_COMPACT_NO_X_SCROLL_REASONS_V70 PR337_BOARD_COMPACT_SORT_REMINDERS_V67 PR337_BOARD_REASON_COLORS_GRADES_V66 PR337_PERFORMANCE_BOARD_DATERANGE_V63 PR337_PERFORMANCE_BOARD_V61_HOTFIX PR337_PERFORMANCE_BOARD_V6 - performance dashboard view; no data/API writes. */
import { useLayoutEffect, useRef, useState } from "react";
import { DatePicker } from "antd";
import dayjs from "dayjs";
import {
  AppstoreOutlined,
  BarChartOutlined,
  BellOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  BarsOutlined,
  TeamOutlined,
  TrophyOutlined,
} from "@ant-design/icons";
import {
  grade,
  score,
  type Config,
  type Grade,
  type Product,
} from "./nativeData";
import "./performanceBoardRedesign.css";

type Props = {
  products: Product[];
  config: Config;
  detail: () => void;
  open: (which: string, id?: string) => void;
};

type Row = {
  product: Product;
  total: number | null;
  rating: Grade | null;
};

const gradeOrder: Grade[] = ["S", "A", "B", "C", "D", "Pass"];
const successfulGrades = new Set<Grade>(["S", "A", "B", "C"]);
type FailureDimension = "market" | keyof Product["scores"];
const weakestDimensions: Array<{
  key: FailureDimension;
  label: string;
  tone: string;
}> = [
  { key: "market", label: "市场竞争", tone: "#9563e8" },
  { key: "speed", label: "出单速度", tone: "#3778f6" },
  { key: "ad", label: "广告有效性", tone: "#fa920e" },
  { key: "profit", label: "利润空间", tone: "#17a47c" },
  { key: "trust", label: "数据可信度", tone: "#7968e7" },
];

function ratio(numerator: number, denominator: number): string {
  return denominator > 0 ? `${(numerator / denominator * 100).toFixed(1)}%` : "—";
}

function average(rows: Row[]): string {
  const values = rows.map((x) => x.total).filter((value): value is number => value !== null && Number.isFinite(value));
  return values.length
    ? (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2)
    : "—";
}

function groupStats(rows: Row[]) {
  const completed = rows.filter((x) => x.total !== null && x.rating !== null);
  const passed = completed.filter((x) => x.rating !== null && successfulGrades.has(x.rating));
  const high = completed.filter((x) => x.rating === "S" || x.rating === "A");
  const grades: Record<Grade, number> = { S: 0, A: 0, B: 0, C: 0, D: 0, Pass: 0 };
  completed.forEach((x) => { if (x.rating !== null) grades[x.rating] += 1; });
  return {
    count: rows.length,
    completed: completed.length,
    passed: passed.length,
    rate: ratio(passed.length, completed.length),
    avg: average(completed),
    highRate: ratio(high.length, completed.length),
    grades,
  };
}


function recommendationTone(completed: number, passed: number): "sample" | "risk" | "good" | "watch" {
  if (completed < 5) return "sample";
  if (passed === 0) return "risk";
  if (passed / completed >= 0.6) return "good";
  return "watch";
}

function recommendation(completed: number, passed: number): string {
  if (completed < 5) return "样本较少";
  if (passed === 0) return "关注通过率";
  if (passed / completed >= 0.6) return "持续观察";
  return "继续积累样本";
}


type AnalysisGroupRow = ReturnType<typeof groupStats> & { name: string };
type BoardSort = "rate-desc" | "rate-asc";
function sortedBoardRows(items: AnalysisGroupRow[], sort: BoardSort): AnalysisGroupRow[] {
  return [...items].sort((a, b) => {
    const aRate = Number.parseFloat(a.rate);
    const bRate = Number.parseFloat(b.rate);
    if (Number.isNaN(aRate) !== Number.isNaN(bRate)) return Number.isNaN(aRate) ? 1 : -1;
    const delta = Number.isNaN(aRate) ? 0 : sort === "rate-desc" ? bRate - aRate : aRate - bRate;
    return delta || a.name.localeCompare(b.name, "zh-CN");
  });
}

export default function PerformanceBoardRedesign({ products, config, open }: Props) {
  // Fit below the actual tab/header position, including browser zoom changes.
  // Direct DOM style update avoids state effects or rerender loops.
  const viewportBoardRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = viewportBoardRef.current;
    if (!element) return;
    const fit = () => {
      const top = Math.max(0, element.getBoundingClientRect().top);
      const available = Math.max(0, window.innerHeight - top - 16);
      element.style.setProperty("--np-pb-viewport-height", `${Math.floor(available)}px`);
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);

  // Inclusive range: today and the preceding 59 calendar days.
  const [dateRange, setDateRange] = useState<[string, string]>(() => {
    const today = dayjs();
    return [today.subtract(59, "day").format("YYYY-MM-DD"), today.format("YYYY-MM-DD")];
  });


  const [categorySort, setCategorySort] = useState<BoardSort>("rate-desc");
  const [developerSort, setDeveloperSort] = useState<BoardSort>("rate-desc");

  const filteredProducts = products.filter((p) => {
    // Product.launch is the actual listing date (not the mock "days" counter).
    // ISO calendar dates compare lexicographically and both ends are inclusive.
    const listingDate = p.launch?.slice(0, 10);
    return Boolean(listingDate && /^\d{4}-\d{2}-\d{2}$/.test(listingDate)
      && listingDate >= dateRange[0] && listingDate <= dateRange[1]);
  });
  const rows: Row[] = filteredProducts.map((product) => ({
    product,
    total: score(product, config),
    rating: grade(product, config),
  }));
  const completed = rows.filter((x) => x.total !== null && Number.isFinite(x.total) && x.rating !== null);
  const passed = completed.filter((x) => x.rating !== null && successfulGrades.has(x.rating));
  const failed = completed.filter((x) => x.rating === "D" || x.rating === "Pass");
  const due = filteredProducts.filter((p) => p.market === null && p.days >= config.remindDays)
    .sort((a, b) => b.days - a.days);
  const lowGrade = completed.filter((x) => x.rating === "C");

  const reminderDisplay = due;

  const grades: Record<Grade, number> = { S: 0, A: 0, B: 0, C: 0, D: 0, Pass: 0 };
  completed.forEach((x) => { if (x.rating !== null) grades[x.rating] += 1; });
  const gradeMax = Math.max(1, ...gradeOrder.map((g) => grades[g]));

  // Diagnostic only: lowest *available* five-dimensional score of D / Pass samples.
  // This does not assert the root cause of a failed assessment.
  // Use actual D/Pass items when present. Otherwise show a CLEARLY-LABELED weak-dimension reference
  // computed from completed items; never present those counts as real failure causes.
  const diagnosticRows = failed.length > 0 ? failed : completed;
  const failureCounts = Object.fromEntries(weakestDimensions.map((x) => [x.key, 0])) as Record<FailureDimension, number>;
  diagnosticRows.forEach(({ product }) => {
    const available: Array<{ key: FailureDimension; value: number }> = [];
    weakestDimensions.forEach((dim) => {
      const value = dim.key === "market"
        ? product.market
        : (product.overrides?.[dim.key] ?? product.scores[dim.key]);
      if (typeof value === "number" && Number.isFinite(value)) {
        available.push({ key: dim.key, value });
      }
    });
    available.sort((a, b) => a.value - b.value);
    if (available[0]) failureCounts[available[0].key] += 1;
  });
  const failureMax = Math.max(1, ...Object.values(failureCounts));

  const categories = [...new Set(rows.map(({ product }) => product.category || "未分类"))]
    .map((name) => ({ name, ...groupStats(rows.filter(({ product }) => (product.category || "未分类") === name)) }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "zh"));
  const developers = [...new Set(rows.map(({ product }) => product.developer || product.owner || "未分配"))]
    .map((name) => ({ name, ...groupStats(rows.filter(({ product }) => (product.developer || product.owner || "未分配") === name)) }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "zh"));

  const displayedCategories = sortedBoardRows(categories, categorySort);
  const displayedDevelopers = sortedBoardRows(developers, developerSort);

  return (
    <div ref={viewportBoardRef} className="np-pb" data-pr337-board="performance-v6">


      <div className="np-pb-filterbar np-pb-filterbar--dates">
        <div className="np-pb-date-filter">
          <span className="np-pb-date-label">日期范围</span>
          <DatePicker.RangePicker
            allowClear={false}
            format="YYYY-MM-DD"
            value={[dayjs(dateRange[0]), dayjs(dateRange[1])]}
            onChange={(dates) => {
              if (dates?.[0] && dates[1]) {
                setDateRange([dates[0].format("YYYY-MM-DD"), dates[1].format("YYYY-MM-DD")]);
              }
            }}
          />
        </div>
      </div>

      <div className="np-pb-layout">
        <section className="np-pb-overview" aria-label="核心指标总览">
          <div className="np-pb-overview-title"><AppstoreOutlined/><h2>核心指标总览</h2></div>
          <div className="np-pb-metrics">
            <article className="np-pb-metric np-pb-metric-blue">
              <div className="np-pb-metric-head"><span className="np-pb-metric-icon"><BarChartOutlined/></span><b>测评总数</b></div>
              <strong>{rows.length}</strong><span>当前筛选范围内</span>
            </article>
            <article className="np-pb-metric np-pb-metric-green">
              <div className="np-pb-metric-head"><span className="np-pb-metric-icon"><CheckCircleOutlined/></span><b>测评通过率</b></div>
              <strong>{ratio(passed.length, completed.length)}</strong><span>通过 {passed.length} / 已完成 {completed.length}</span>
            </article>
            <article className="np-pb-metric np-pb-metric-danger">
              <div className="np-pb-metric-head"><span className="np-pb-metric-icon"><CloseCircleOutlined/></span><b>测评不通过数</b></div>
              <strong>{failed.length}</strong><span>D / Pass 级，重点复盘</span>
            </article>
            <article className="np-pb-metric np-pb-metric-orange">
              <div className="np-pb-metric-head"><span className="np-pb-metric-icon"><ExclamationCircleOutlined/></span><b>低分待优化数</b></div>
              <strong>{lowGrade.length}</strong><span>C 级新品，优先观察改进</span>
            </article>
          </div>

          <section className="np-pb-reminders" aria-label="待评分提醒">
            <div className="np-pb-reminder-title"><BellOutlined/><div><h3>待评分提醒</h3><p>上架满{config.remindDays}天仍未确认市场竞争评分</p><span className="np-pb-reminder-counter">{reminderDisplay.length} 条待评分</span></div></div>
            <div className="np-pb-reminder-table-wrap">
              <table className="np-pb-reminder-table">
                <thead><tr><th>商品</th><th>开发人员</th><th>上架天数</th><th>操作</th></tr></thead>
                <tbody>
                  {reminderDisplay.map((item) => (
                    <tr key={item.id}>
                      <td><strong>{item.sku}</strong><small title={item.name}>{item.name}</small></td>
                      <td>{item.developer || item.owner || "—"}</td>
                      <td><span className="np-pb-days">{item.days} 天</span></td>
                      <td><button type="button" className="np-pb-mini-button" onClick={() => open("market", item.id)}>去评分</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </section>

        <div className="np-pb-main">
          <div className="np-pb-top-grid">
            <section className="np-pb-panel np-pb-score-panel">
              <div className="np-pb-panel-head"><div className="np-pb-panel-title"><BarChartOutlined/><h2>测评等级分布</h2></div><span>按已完成测评分类统计</span></div>
              <div className="np-pb-panel-body np-pb-barlist">
                {gradeOrder.map((g) => (
                  <div className="np-pb-barrow" key={g}>
                    <span className="np-pb-barlabel">{g === "Pass" ? "Pass" : `${g}级`}</span>
                    <div className="np-pb-track"><span className={`np-pb-fill np-pb-grade-${g.toLowerCase()}`} style={{ width: `${grades[g] / gradeMax * 100}%` }}/></div>
                    <strong>{grades[g]}</strong>
                  </div>
                ))}
              </div>
            </section>
            <section className="np-pb-panel np-pb-reason-panel">
              <div className="np-pb-panel-head"><div className="np-pb-panel-title"><TrophyOutlined/><h2>测评失败原因</h2></div><span>{failed.length > 0 ? "D / Pass 样本 · 最低分维度" : completed.length > 0 ? "无不通过样本 · 展示低分维度参考" : "暂无已完成测评"}</span></div>
              <div className="np-pb-panel-body np-pb-barlist">
                {weakestDimensions.map((dim) => (
                  <div className="np-pb-barrow" key={dim.key}>
                    <span className="np-pb-barlabel np-pb-reasonlabel">{dim.label}</span>
                    <div className="np-pb-track"><span className="np-pb-fill" style={{ width: `${failureCounts[dim.key] / failureMax * 100}%`, background: dim.tone }}/></div>
                    <strong>{failureCounts[dim.key]}</strong>
                  </div>
                ))}
                {failed.length === 0 && <p className="np-pb-panel-note">{completed.length > 0 ? "当前无 D / Pass；柱形显示已完成商品的最低分维度参考，不代表实际失败原因。" : "当前范围没有已完成测评，暂无失败原因数据。"}</p>}
              </div>
            </section>
          </div>

          <section className="np-pb-panel np-pb-data-panel">
            <div className="np-pb-panel-head"><div className="np-pb-panel-title"><BarsOutlined/><h2>类目测评表现</h2><span className="np-pb-inline-sub">查看通过率及可继续拓展的类目</span></div>
              <div className="np-pb-panel-actions"><span>{displayedCategories.length} 个类目</span>
                <button type="button" className="np-pb-sort-toggle"
                  aria-label={`类目通过率排序：${categorySort === "rate-desc" ? "从高到低" : "从低到高"}，点击切换`}
                  title={`按通过率${categorySort === "rate-desc" ? "从高到低" : "从低到高"}排序，点击切换`}
                  onClick={() => setCategorySort((value) => value === "rate-desc" ? "rate-asc" : "rate-desc")}>
                  通过率 {categorySort === "rate-desc" ? "↓" : "↑"}
                </button>
              </div>
            </div>
            <div className="np-pb-table-scroll"><table className="np-pb-data-table">
              <thead><tr><th>类目</th><th>测评数</th><th>通过数</th><th>不通过数</th><th>通过率</th><th>高等级占比</th><th>建议</th></tr></thead>
              <tbody>
                {displayedCategories.map((x) => (
                  <tr key={x.name}>
                    <td><strong className="np-pb-row-label">{x.name}</strong></td>
                    <td>{x.count}</td><td>{x.passed}</td><td>{x.completed - x.passed}</td><td>{x.rate}</td><td>{x.highRate}</td>
                    <td><span className={`np-pb-pill np-pb-pill--${recommendationTone(x.completed, x.passed)}`}>{recommendation(x.completed, x.passed)}</span></td>
                  </tr>
                ))}
                {displayedCategories.length === 0 && <tr><td className="np-pb-empty" colSpan={7}>当前筛选下暂无类目数据</td></tr>}
              </tbody>
            </table></div>
          </section>

          <section className="np-pb-panel np-pb-data-panel">
            <div className="np-pb-panel-head"><div className="np-pb-panel-title"><TeamOutlined/><h2>新品开发人员表现</h2><span className="np-pb-inline-sub">仅统计已完成测评样本</span></div>
              <div className="np-pb-panel-actions"><span>{displayedDevelopers.length} 位开发人员</span>
                <button type="button" className="np-pb-sort-toggle"
                  aria-label={`开发人员通过率排序：${developerSort === "rate-desc" ? "从高到低" : "从低到高"}，点击切换`}
                  title={`按通过率${developerSort === "rate-desc" ? "从高到低" : "从低到高"}排序，点击切换`}
                  onClick={() => setDeveloperSort((value) => value === "rate-desc" ? "rate-asc" : "rate-desc")}>
                  通过率 {developerSort === "rate-desc" ? "↓" : "↑"}
                </button>
              </div>
            </div>
            <div className="np-pb-table-scroll"><table className="np-pb-data-table np-pb-developer-table">
              <thead><tr><th>开发人员</th><th>测评数</th><th>通过数</th><th>不通过数</th><th>通过率</th><th>等级分布</th></tr></thead>
              <tbody>
                {displayedDevelopers.map((x) => (
                  <tr key={x.name}>
                    <td><strong className="np-pb-row-label">{x.name}</strong></td>
                    <td>{x.count}</td><td>{x.passed}</td><td>{x.completed - x.passed}</td><td>{x.rate}</td>
                    <td className="np-pb-grade-spread">
                      {x.completed > 0 ? (
                        <div className="np-pb-grade-compact"
                          title={gradeOrder.map((g) => `${g} 级：${x.grades[g]} 个`).join(" · ")}
                          aria-label={`等级分布：${gradeOrder.map((g) => `${g} ${x.grades[g]}`).join("，")}`}>
                          {gradeOrder.filter((g) => x.grades[g] > 0)

                            .map((g) => <span key={g} className={`np-pb-grade-chip np-pb-grade-chip--${g.toLowerCase()}`}>{g} {x.grades[g]}</span>)}
                        </div>
                      ) : <span className="np-pb-grade-no-data">暂无已完成测评</span>}
                    </td>
                  </tr>
                ))}
                {displayedDevelopers.length === 0 && <tr><td className="np-pb-empty" colSpan={6}>当前筛选下暂无开发人员数据</td></tr>}
              </tbody>
            </table></div>
          </section>
        </div>
      </div>
    </div>
  );
}
