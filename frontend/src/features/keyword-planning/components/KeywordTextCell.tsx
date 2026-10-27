import {Button, Space, Typography} from 'antd';
import {CopyableTextCell} from '@/components/report-table/cells';
import type {MarketKeyword} from '../types';
import './KeywordTextCell.css';

/** Feature-local composition of existing canonical report cells; no parallel Shared component. */
export function KeywordTextCell({keyword,onEdit}:{keyword:MarketKeyword;onEdit?:(keyword:MarketKeyword)=>void}){
  return <div className="keyword-planning__term">
    <CopyableTextCell text={keyword.term} label="复制英文关键词" textClassName="keyword-planning__term-original"/>
    <Space size={4}>
      <Typography.Text type="secondary" className="keyword-planning__term-translation">{keyword.translation||'待翻译'}</Typography.Text>
      {onEdit?<Button type="link" size="small" onClick={()=>onEdit(keyword)} aria-label={`修改 ${keyword.term} 的中文翻译`}>编辑</Button>:null}
    </Space>
  </div>;
}
