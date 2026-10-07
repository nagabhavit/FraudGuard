import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function CopyableId({ value, display }: { value: string; display?: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access denied (e.g. insecure context) -- nothing to show
      // for a failed copy beyond leaving the icon unchanged.
    }
  };

  return (
    <span
      className="copyable mono"
      onClick={(event) => {
        event.stopPropagation();
        void handleCopy();
      }}
      title={`Copy ${value}`}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          void handleCopy();
        }
      }}
    >
      {display ?? value}
      <span className="copyable-icon">
        {copied ? <Check size={12} /> : <Copy size={12} />}
      </span>
    </span>
  );
}
