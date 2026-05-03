"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders LLM / report markdown on dark surfaces. Used by:
 *  - FindingDetailModal "Translate to Thai" output
 *  - (future) report translation output
 *
 * Styling targets the dark theme palette already in tailwind.config.ts so
 * Thai/English markdown both read well at body size 14px.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown-body text-sm leading-relaxed text-slate-100">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => (
            <h1 className="mt-4 mb-2 text-base font-semibold text-slate-50 first:mt-0" {...p} />
          ),
          h2: (p) => (
            <h2 className="mt-4 mb-2 text-sm font-semibold uppercase tracking-wide text-slate-200 first:mt-0" {...p} />
          ),
          h3: (p) => (
            <h3 className="mt-3 mb-1.5 text-sm font-semibold text-slate-200 first:mt-0" {...p} />
          ),
          h4: (p) => (
            <h4 className="mt-3 mb-1 text-xs font-semibold uppercase tracking-wide text-slate-300 first:mt-0" {...p} />
          ),
          p: (p) => <p className="mb-2 last:mb-0" {...p} />,
          a: (p) => (
            <a
              className="text-accent underline-offset-2 hover:underline"
              target="_blank"
              rel="noopener noreferrer"
              {...p}
            />
          ),
          ul: (p) => <ul className="mb-2 ml-5 list-disc space-y-1" {...p} />,
          ol: (p) => <ol className="mb-2 ml-5 list-decimal space-y-1" {...p} />,
          li: (p) => <li className="text-slate-200" {...p} />,
          strong: (p) => <strong className="font-semibold text-slate-50" {...p} />,
          em: (p) => <em className="italic text-slate-200" {...p} />,
          blockquote: (p) => (
            <blockquote
              className="my-2 border-l-2 border-accent/40 pl-3 italic text-slate-300"
              {...p}
            />
          ),
          hr: () => <hr className="my-3 border-border-subtle" />,
          code: (props) => {
            const { children, className } = props as {
              children?: React.ReactNode;
              className?: string;
            };
            const isBlock = Boolean(className?.startsWith("language-"));
            if (isBlock) {
              return (
                <code className="font-mono text-xs">{children}</code>
              );
            }
            return (
              <code className="rounded bg-bg/80 px-1 py-0.5 font-mono text-[12px] text-slate-100">
                {children}
              </code>
            );
          },
          pre: (p) => (
            <pre
              className="my-2 overflow-x-auto rounded-md bg-bg/80 p-3 font-mono text-xs leading-relaxed text-slate-200"
              {...p}
            />
          ),
          table: (p) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-xs" {...p} />
            </div>
          ),
          thead: (p) => <thead className="bg-bg/50 text-slate-300" {...p} />,
          th: (p) => (
            <th
              className="border border-border-subtle px-2 py-1 text-left font-medium"
              {...p}
            />
          ),
          td: (p) => (
            <td className="border border-border-subtle px-2 py-1 align-top" {...p} />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
