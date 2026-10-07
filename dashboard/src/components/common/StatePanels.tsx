import { Inbox, RefreshCw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="state-panel">
      <div className="state-panel-icon">{icon ?? <Inbox size={28} />}</div>
      <div className="state-panel-title">{title}</div>
      {description && <p>{description}</p>}
    </div>
  );
}

export function ErrorStatePanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-panel error">
      <div className="state-panel-icon">
        <TriangleAlert size={28} />
      </div>
      <div className="state-panel-title">Could not load data</div>
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          <RefreshCw size={13} />
          Retry
        </button>
      )}
    </div>
  );
}
