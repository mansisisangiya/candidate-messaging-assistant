import type { RunStatus } from "../types";

interface Props {
  status: RunStatus;
  testId?: string;
}

export function StatusBadge({ status, testId = "status-badge" }: Props) {
  return (
    <span className={`badge badge-${status}`} data-testid={testId}>
      {status.replace("_", " ")}
    </span>
  );
}
