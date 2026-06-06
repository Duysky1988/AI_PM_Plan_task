// ── OPL Types ──────────────────────────────────────────────────────────────────

export type OPLStatus =
  | 'running' | 'closed' | 'overdue' | 'rejected'
  | 'waiting_approval' | 'draft' | 'on_hold' | 'deleted'

export type OPLEntryType = 'Task' | 'Information' | 'Decision' | 'Subtask'
export type Priority = 'High' | 'Medium' | 'Low'

export interface OPLNote {
  text: string
  by: string
  at: string
}

export interface OPLEntry {
  id: string
  entry_type: OPLEntryType
  parent_id: string | null
  subject: string
  description: string
  remarks: string
  last_note: string
  owner: string
  responsible: string[]
  information_to: string[]
  topic_owner: string
  sw_category: string
  topic: string
  sub_topic: string
  category: string
  source: string
  register: string
  tags: string[]
  sprint_tag: string
  meeting: string
  priority: Priority
  status: OPLStatus
  risk_flag: boolean
  risk_impact: string
  confidential: boolean
  pinned: boolean
  linked_risk_id: string | null
  input_date: string | null
  start_date: string | null
  due_date: string | null
  closed_date: string | null
  input_by: string
  notes: OPLNote[]
  attachments: unknown[]
  last_change: string
  last_change_by: string
  created_at: string
  bosch_task_id?: number
  subtasks?: OPLEntry[]
}

export interface OPLListResponse {
  total: number
  page: number
  limit: number
  items: OPLEntry[]
}

// ── Risk Types ─────────────────────────────────────────────────────────────────

export interface RiskMeasure {
  task_id: number | null
  bosch_task_id: number | null
  subject: string
  strategy: string
  description: string
  owner: string
  responsible: string
  due_date: string
  status: string
  created_at: string
}

export interface Risk {
  id: string
  bosch_risk_id?: number
  entry_type: 'Risk'
  subject: string
  description: string
  category: string
  probability: number | null
  impact: number | null
  risk_score: number | null
  status: string
  owner: string
  owner_login: string
  due_date: string
  created_at: string
  measures: RiskMeasure[]
  sync_source: 'bosch' | 'local'
}

// ── Lesson Learned Types ───────────────────────────────────────────────────────

export interface LessonLearned {
  id: string
  bosch_ll_id?: number
  entry_type: 'Lesson'
  subject: string
  observation: string
  cause: string
  actions: string
  phase: string
  category: string
  subcategory: string
  owner: string
  owner_login: string
  status: string
  created_at: string
  sync_source: 'bosch' | 'local'
}

// ── Planning Types ─────────────────────────────────────────────────────────────

export type PlanningSheet = 'master' | 'sw' | 'peru' | 'opl'
export type TaskStatus = 'grey' | 'red' | 'yellow' | 'green'

export interface TaskDependency {
  id: number
  type: 'FS' | 'SS' | 'FF' | 'SF'
  lag_days: number
}

export interface PlanningTask {
  id: number
  parent_id: number | null
  task_name: string
  start_date: string
  finish_date: string
  duration: number
  percent_complete: number
  status: TaskStatus
  resource_names: string
  milestone: boolean
  dependencies: TaskDependency[]
  bar_label: string
  bar_annotation: string
  row_color: string
  outline_level: number
  active: boolean
  source: string
}

export interface PlanningVersion {
  version_id: string
  saved_at: string
  label: string
  task_count: number
  diff_summary: string
}
