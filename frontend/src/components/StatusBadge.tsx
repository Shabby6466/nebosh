interface StatusBadgeProps {
  status: "idle" | "starting" | "active" | "ended";
  violation: string | null | undefined;
}

export default function StatusBadge({ status, violation }: StatusBadgeProps) {
  if (status === "starting") {
    return <span className="badge badge-neutral badge-pulse">Connecting…</span>;
  }

  if (violation) {
    return <span className="badge badge-bad">{violation.replaceAll("_", " ")}</span>;
  }

  return <span className="badge badge-good">Monitoring</span>;
}
