import type { StatusRole } from "../../lib/risk";

export function StatusBadge({
  label,
  role,
}: {
  label: string;
  role: StatusRole | "neutral";
}) {
  return (
    <span className={`status-badge ${role}`}>
      <span className="status-badge-dot" />
      {label}
    </span>
  );
}
