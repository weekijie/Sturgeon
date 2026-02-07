"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ProseProps {
  content: string;
  className?: string;
}

export default function Prose({ content, className = "" }: ProseProps) {
  return (
    <div className={`prose-medical ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
