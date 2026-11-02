import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Keep reference to the AST node out of the rendered DOM props.


const safeUrl = (url: string): string => {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' ? url : '';
  } catch { return ''; }
};

/** Markdown is rendered as React elements; raw HTML is not executed. */
export default function AssistantMarkdown({ value }: { value: string }) {
  return <div className="ai7-markdown">
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      urlTransform={safeUrl}
      components={{
        a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer nofollow">{children}</a>,
        table: ({ children }) => <div className="ai7-markdown-table"><table>{children}</table></div>,
      }}
    >{value}</ReactMarkdown>
  </div>;
}
