import { Cpu, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useGatewayPulse } from "../../hooks/useGatewayPulse";

export function TopBar() {
  const pulse = useGatewayPulse();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    navigate(trimmed ? `/transactions?search=${encodeURIComponent(trimmed)}` : "/transactions");
  };

  return (
    <header className="topbar">
      <form className="topbar-search" onSubmit={handleSearch} role="search">
        <Search size={15} />
        <input
          type="search"
          placeholder="Search transaction, account, or merchant ID…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search transactions"
        />
      </form>

      <div className="topbar-right">
        <span
          className="model-pill"
          title={
            pulse.latestModelVersion
              ? `Scored by ${pulse.latestModelVersion}`
              : "No transaction has been scored by the model yet"
          }
        >
          <Cpu size={13} />
          {pulse.latestModelVersion ?? "no model activity"}
        </span>

        <span
          className={`live-pill${pulse.isLive ? "" : " offline"}`}
          title={
            pulse.isLive
              ? "Gateway and database reachable"
              : "Gateway or database unreachable"
          }
        >
          <span className="live-pill-dot" />
          {pulse.isLive ? "LIVE" : "OFFLINE"}
        </span>

        <span className="profile-chip" title="Single-operator deployment (ADR-0012) — no auth">
          OP
        </span>
      </div>
    </header>
  );
}
