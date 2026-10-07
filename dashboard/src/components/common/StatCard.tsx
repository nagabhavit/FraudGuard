import type { ReactNode } from "react";
import { Skeleton } from "./Skeleton";

export function StatCard({
  label,
  icon,
  value,
  meta,
  loading,
}: {
  label: string;
  icon?: ReactNode;
  value: string;
  meta?: ReactNode;
  loading?: boolean;
}) {
  return (
    <div className="stat-card">
      <div className="stat-card-top">
        <span className="stat-card-label">{label}</span>
        {icon && <span className="stat-card-icon-badge">{icon}</span>}
      </div>
      {loading ? (
        <Skeleton width="65%" height={30} />
      ) : (
        <span className="stat-card-value">{value}</span>
      )}
      {meta && <span className="stat-card-meta">{meta}</span>}
    </div>
  );
}
