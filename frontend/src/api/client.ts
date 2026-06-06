import type {
  OPLEntry, OPLListResponse, OPLStatus,
  Risk, LessonLearned,
  PlanningTask, PlanningSheet, PlanningVersion,
} from '../types'

declare global {
  interface Window { __API_BASE__?: string }
}

const BASE = window.__API_BASE__ ?? 'http://127.0.0.1:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail?.detail ?? res.statusText)
  }
  return res.json() as Promise<T>
}

// ── OPL ───────────────────────────────────────────────────────────────────────

export const api = {
  opl: {
    list(params?: {
      show?: string; category?: string; owner?: string;
      search?: string; tags?: string; priority?: string;
      register?: string; page?: number; limit?: number
    }): Promise<OPLListResponse> {
      const q = new URLSearchParams(params as Record<string, string>).toString()
      return request(`/api/opl${q ? '?' + q : ''}`)
    },

    get(id: string): Promise<OPLEntry & { subtasks: OPLEntry[] }> {
      return request(`/api/opl/${id}`)
    },

    create(entry: Partial<OPLEntry>): Promise<OPLEntry> {
      return request('/api/opl', { method: 'POST', body: JSON.stringify(entry) })
    },

    update(id: string, updates: Partial<OPLEntry>): Promise<OPLEntry> {
      return request(`/api/opl/${id}`, { method: 'PUT', body: JSON.stringify(updates) })
    },

    delete(id: string): Promise<{ status: string; id: string }> {
      return request(`/api/opl/${id}`, { method: 'DELETE' })
    },

    setStatus(id: string, status: OPLStatus, note?: string, by?: string) {
      return request(`/api/opl/${id}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status, note, by }),
      })
    },

    teamMembers(): Promise<{ members: string[] }> {
      return request('/api/opl/team-members')
    },

    async import(file: File, mode: 'append' | 'upsert' = 'append') {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${BASE}/api/opl/import?mode=${mode}`, { method: 'POST', body: form })
      if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText)
      return res.json()
    },

    exportUrl(format: 'xlsx' | 'csv' = 'xlsx', show = 'all', search = '') {
      return `${BASE}/api/opl/export?format=${format}&show=${show}&search=${encodeURIComponent(search)}`
    },
  },

  // ── Bosch ──────────────────────────────────────────────────────────────────

  bosch: {
    status(): Promise<{ connected: boolean; opl: number }> {
      return request('/api/bosch-opl/status')
    },

    allTasks(): Promise<{ total: number; tasks: OPLEntry[] }> {
      return request('/api/bosch-opl/all-tasks')
    },

    sync(): Promise<{ added: number; updated: number; unchanged: number; local_only: number }> {
      return request('/api/bosch-opl/sync', { method: 'POST' })
    },

    pushAll(): Promise<{ pushed: number; failed: number; errors: unknown[] }> {
      return request('/api/bosch-opl/push-all', { method: 'POST' })
    },

    allRisks(): Promise<{ total: number; risks: Risk[] }> {
      return request('/api/bosch-opl/all-risks')
    },

    syncRisks(): Promise<{ added: number; updated: number }> {
      return request('/api/bosch-opl/risks/sync', { method: 'POST' })
    },

    allLessons(): Promise<{ total: number; lessons: LessonLearned[] }> {
      return request('/api/bosch-opl/all-lessons')
    },

    syncLessons(): Promise<{ added: number; updated: number }> {
      return request('/api/bosch-opl/lessons/sync', { method: 'POST' })
    },
  },

  // ── Planning ───────────────────────────────────────────────────────────────

  planning: {
    get(sheet: PlanningSheet): Promise<{ sheet: string; tasks: PlanningTask[]; saved_at: string | null }> {
      return request(`/api/planning?sheet=${sheet}`)
    },

    save(sheet: PlanningSheet, tasks: PlanningTask[], label = ''): Promise<{ saved_at: string; version_id: string }> {
      return request('/api/planning', {
        method: 'POST',
        body: JSON.stringify({ sheet, tasks, label }),
      })
    },

    reset(sheet: PlanningSheet): Promise<{ ok: boolean }> {
      return request(`/api/planning?sheet=${sheet}`, { method: 'DELETE' })
    },

    versions(sheet: PlanningSheet, limit = 20): Promise<{ versions: PlanningVersion[] }> {
      return request(`/api/planning/versions?sheet=${sheet}&limit=${limit}`)
    },

    getVersion(versionId: string, sheet: PlanningSheet): Promise<{ tasks: PlanningTask[] }> {
      return request(`/api/planning/versions/${versionId}?sheet=${sheet}`)
    },

    deleteVersion(versionId: string, sheet: PlanningSheet): Promise<{ ok: boolean }> {
      return request(`/api/planning/versions/${versionId}?sheet=${sheet}`, { method: 'DELETE' })
    },
  },

  health(): Promise<{ status: string; files: Record<string, boolean> }> {
    return request('/api/health')
  },
}
