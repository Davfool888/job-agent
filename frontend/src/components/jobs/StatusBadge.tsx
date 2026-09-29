import {
  Archive,
  BookmarkCheck,
  ExternalLink,
  Inbox,
  Send,
} from "lucide-react";
import type { JobStatus } from "../../types/job";
import { STATUS_LABELS } from "../../utils/constants";

const ICONS: Record<JobStatus, typeof Inbox> = {
  new: Inbox,
  kept: BookmarkCheck,
  discarded: Archive,
  opened: ExternalLink,
  applied: Send,
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const Icon = ICONS[status] ?? Inbox;
  return (
    <span className={`badge badge-${status}`}>
      <Icon /> {STATUS_LABELS[status] ?? status}
    </span>
  );
}
