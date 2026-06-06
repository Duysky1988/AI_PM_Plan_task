import type { OPLStatus, Priority } from '../../types'

export function StatusBadge({ status }: { status: OPLStatus }) {
  const labels: Record<OPLStatus, string> = {
    running: 'Running', closed: 'Closed', overdue: 'Overdue',
    rejected: 'Rejected', waiting_approval: 'Waiting', draft: 'Draft',
    on_hold: 'On Hold', deleted: 'Deleted',
  }
  return <span className={`badge badge-${status}`}>{labels[status] ?? status}</span>
}

export function PriorityBadge({ priority }: { priority: Priority | string }) {
  return <span className={`badge badge-${priority}`}>{priority}</span>
}
