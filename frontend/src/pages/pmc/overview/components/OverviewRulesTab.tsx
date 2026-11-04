/** 规则设置 tab: read-only judgement parameters (phase 1, PRP D5). */
import { Alert, Descriptions, Typography } from "antd";
import { overviewErrorText } from "@/pages/pmc/overview/overviewApi";
import { PARAM_DOC } from "@/pages/pmc/overview/overviewDisplay";
import { useOverviewRulesQuery } from "@/pages/pmc/overview/overviewQueries";

function OverviewRulesTab() {
  const query = useOverviewRulesQuery(true);
  if (query.error) return <Alert type="error" showIcon message={overviewErrorText(query.error)} />;
  const values = new Map((query.data?.params ?? []).map((x) => [x.key, x.value]));
  const groups: { title: string; rows: (readonly string[])[] }[] = [];
  for (const d of PARAM_DOC) {
    if (d.length === 1) groups.push({ title: d[0], rows: [] });
    else if (groups.length) groups[groups.length - 1].rows.push(d);
  }
  return (
    <div className="pmc-overview__tab-body">
      <Alert type="info" showIcon message={`一期只读（PRP D5）：规则版本 ${query.data?.rule_version ?? "—"}；要改参数走规则版本，不在本页改。`} />
      {groups.map((g) => (
        <Descriptions
          key={g.title}
          title={g.title}
          size="small"
          bordered
          column={{ xs: 1, md: 2 }}
          items={g.rows.map((d) => ({
            key: d[0],
            label: <span>{d[1]}<br /><Typography.Text type="secondary">{d[2]}</Typography.Text></span>,
            children: values.get(d[0]) ?? "—",
          }))}
        />
      ))}
    </div>
  );
}

export default OverviewRulesTab;
