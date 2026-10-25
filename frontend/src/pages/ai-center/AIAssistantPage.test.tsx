// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode, ButtonHTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from 'react';
import type { NavigationPage } from '@/config/navigation';
import AIAssistantPage from './AIAssistantPage';

vi.mock('@/components/page/PageShell', () => ({
  default: ({ children }: { children: ReactNode }) => <div data-testid="page-shell">{children}</div>,
}));
vi.mock('antd', async () => {
  const React = await import('react');
  type Btn = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> & { icon?: ReactNode; type?: string; shape?: string; size?: string; block?: boolean };
  const Button = ({ icon, children, type: _t, shape: _s, size: _z, block: _b, ...props }: Btn) => {
    void _t;void _s;void _z;void _b;
    return <button type="button" {...props}>{icon}{children}</button>;
  };
  type Inp = Omit<InputHTMLAttributes<HTMLInputElement>, 'prefix'> & { prefix?: ReactNode; allowClear?: boolean };
  const Input = Object.assign(({prefix,allowClear,...props}:Inp)=>{
    void prefix;void allowClear;return <input {...props}/>;
  }, {TextArea:(props:TextareaHTMLAttributes<HTMLTextAreaElement>)=><textarea {...props}/>});
  const Dropdown = ({children,menu}:{
    children:ReactNode;menu:{items:{key:string;label:ReactNode;onClick?:()=>void}[]}
  })=>{
    const [opened,setOpened]=React.useState(false);
    return <div><span onClick={()=>setOpened(v=>!v)}>{children}</span>
      {opened&&<div role="menu">{menu.items.map(item=><button type="button" role="menuitem" key={item.key} onClick={()=>{item.onClick?.();setOpened(false);}}>{item.label}</button>)}</div>}</div>;
  };
  const Modal=({children,title,open,onCancel,onOk}:{
    children:ReactNode;title:ReactNode;open:boolean;onCancel?:()=>void;onOk?:()=>void
  })=>open?<div role="dialog" aria-label={String(title)}>{children}<button onClick={onCancel}>取消</button><button onClick={onOk}>确定</button></div>:null;
  return {
    Button, Input, Dropdown, Modal,
    Tooltip:({children}:{children:ReactNode})=><>{children}</>,
    message:{useMessage:()=>[{warning:vi.fn()},null]},
  };
});
const page={key:'ai_center_assistant',title:'AI助手'} as NavigationPage;
beforeEach(()=>window.localStorage.clear());
afterEach(cleanup);
function mount(){return render(<AIAssistantPage page={page} preferenceScope="ai-v7-test"/>);}
describe('AI assistant V7 inside existing MainLayout',()=>{
  it('renders only its page shell and new conversation workspace',()=>{
    mount();
    expect(screen.getByTestId('page-shell')).toBeInTheDocument();
    expect(screen.getByRole('heading',{name:'今天想分析什么？'})).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'新建对话'})).toBeInTheDocument();
    expect(screen.queryByText('我的授权产品')).not.toBeInTheDocument();
    expect(screen.queryByText('数据依据与分析边界')).not.toBeInTheDocument();
  });
  it('sends mock analysis with prominent disclaimer',()=>{
    mount();
    fireEvent.change(screen.getByRole('textbox',{name:'输入问题'}),{target:{value:'哪些 SKU 利润下降？'}});
    fireEvent.click(screen.getByRole('button',{name:'发送消息'}));
    expect(screen.getByText(/演示分析 · 模拟数据/)).toBeInTheDocument();
    expect(screen.getByText('异常 SKU 排查')).toBeInTheDocument();
  });
  it('preserves independent drafts across conversations',()=>{
    mount();
    fireEvent.change(screen.getByRole('textbox',{name:'输入问题'}),{target:{value:'第一条消息'}});
    fireEvent.click(screen.getByRole('button',{name:'发送消息'}));
    fireEvent.click(screen.getByRole('button',{name:'新建对话'}));
    fireEvent.change(screen.getByRole('textbox',{name:'输入问题'}),{target:{value:'第二个聊天的草稿'}});
    const first=screen.getByRole('button',{name:/聊天操作：第一条消息/});
    expect(first).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:/^第一条消息\s*1 条提问$/}));
    expect(screen.getByRole('textbox',{name:'输入问题'})).toHaveValue('');
    fireEvent.click(screen.getByRole('button',{name:/^新聊天\s*暂无消息$/}));
    expect(screen.getByRole('textbox',{name:'输入问题'})).toHaveValue('第二个聊天的草稿');
  });
  it('supports attachment-only messages and removal',()=>{
    mount();
    const report=new File(['sample'],'report.csv',{type:'text/csv'});
    fireEvent.change(screen.getByLabelText('选择文件'),{target:{files:[report]}});
    expect(screen.getByText('report.csv')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'发送消息'}));
    expect(screen.getByText(/尚未上传服务器或供 OpenAI 解析/)).toBeInTheDocument();
    const picture=new File(['mock'],'demo.png',{type:'image/png'});
    fireEvent.change(screen.getByLabelText('选择图片'),{target:{files:[picture]}});
    expect(screen.getByText('demo.png')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'移除 demo.png'}));
    expect(screen.queryByText('demo.png')).not.toBeInTheDocument();
  });
});