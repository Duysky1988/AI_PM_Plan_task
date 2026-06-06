import { useEffect, useRef, useState, useCallback } from 'react'
import { api } from '../../api/client'
import type { OPLEntry, OPLStatus } from '../../types'
import { StatusBadge, PriorityBadge } from '../ui/StatusBadge'
import OPLDetail from './OPLDetail'
import OPLForm from './OPLForm'

const SHOW_OPTIONS = [
  { value: 'all', label: 'All active' },
  { value: 'running', label: 'Running' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'closed', label: 'Closed' },
  { value: 'on_hold', label: 'On Hold' },
  { value: 'draft', label: 'Draft' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'waiting_approval', label: 'Waiting Approval' },
  { value: 'all_deleted', label: 'All (incl. deleted)' },
]

export default function OPLTab() {
  const [items, setItems] = useState<OPLEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [show, setShow] = useState('all')
  const [search, setSearch] = useState('')
  const [owner, setOwner] = useState('')
  const [priority, setPriority] = useState('')
  const [page, setPage] = useState(1)
  const limit = 100

  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const searchRef = useRef<ReturnType<typeof setTimeout>>()

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.opl.list({ show, search, owner, priority, page, limit })
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [show, search, owner, priority, page])

  useEffect(() => { load() }, [load])

  const handleSearch = (v: string) => {
    clearTimeout(searchRef.current)
    searchRef.current = setTimeout(() => { setSearch(v); setPage(1) }, 350)
  }

  const handleExport = () => {
    window.open(api.opl.exportUrl('xlsx', show, search), '_blank')
  }

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const res = await api.opl.import(file, 'append')
      alert(`Imported ${res.imported}, skipped ${res.skipped}`)
      load()
    } catch (err) {
      alert('Import failed: ' + String(err))
    }
    e.target.value = ''
  }

  const handleStatusChange = async (id: string, status: OPLStatus) => {
    await api.opl.setStatus(id, status)
    load()
  }

  const totalPages = Math.ceil(total / limit)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={show} onChange={e => { setShow(e.target.value); setPage(1) }} style={{ width: 160 }}>
          {SHOW_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <input placeholder="Search…" onChange={e => handleSearch(e.target.value)} style={{ width: 220 }} />
        <input placeholder="Owner…" value={owner} onChange={e => { setOwner(e.target.value); setPage(1) }} style={{ width: 140 }} />
        <select value={priority} onChange={e => { setPriority(e.target.value); setPage(1) }} style={{ width: 120 }}>
          <option value="">All priority</option>
          <option value="High">High</option>
          <option value="Medium">Medium</option>
          <option value="Low">Low</option>
        </select>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{total} entries</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn-ghost" onClick={handleExport}>Export XLSX</button>
          <label className="btn-ghost" style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid var(--border)', cursor: 'pointer' }}>
            Import
            <input type="file" accept=".xlsx,.xls,.csv" onChange={handleImport} style={{ display: 'none' }} />
          </label>
          <button className="btn-primary" onClick={() => setCreating(true)}>+ New Entry</button>
        </div>
      </div>

      {error && <div style={{ color: 'var(--danger)', padding: 8 }}>{error}</div>}

      {/* Table */}
      <div className="card" style={{ overflow: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ width: 90 }}>ID</th>
              <th style={{ width: 60 }}>Type</th>
              <th>Subject</th>
              <th style={{ width: 130 }}>Owner</th>
              <th style={{ width: 90 }}>Due</th>
              <th style={{ width: 90 }}>Priority</th>
              <th style={{ width: 110 }}>Status</th>
              <th style={{ width: 80 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>Loading…</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>No entries found</td></tr>
            )}
            {items.map(item => (
              <tr key={item.id} style={{ cursor: 'pointer' }} onClick={() => setSelected(item.id)}>
                <td style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--text-muted)' }}>
                  {item.pinned && '📌 '}{item.id}
                </td>
                <td style={{ fontSize: 12 }}>{item.entry_type}</td>
                <td>
                  <div style={{ fontWeight: 500 }}>{item.subject || '(no subject)'}</div>
                  {item.last_note && (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                      ↳ {item.last_note.slice(0, 80)}{item.last_note.length > 80 ? '…' : ''}
                    </div>
                  )}
                </td>
                <td style={{ fontSize: 13 }}>{item.owner}</td>
                <td style={{ fontSize: 12, color: item.status === 'overdue' ? 'var(--danger)' : undefined }}>
                  {item.due_date ?? '—'}
                </td>
                <td><PriorityBadge priority={item.priority} /></td>
                <td><StatusBadge status={item.status} /></td>
                <td onClick={e => e.stopPropagation()}>
                  {item.status === 'running' || item.status === 'overdue' ? (
                    <button className="btn-ghost" style={{ fontSize: 11, padding: '3px 8px' }}
                      onClick={() => handleStatusChange(item.id, 'closed')}>Close</button>
                  ) : item.status === 'closed' ? (
                    <button className="btn-ghost" style={{ fontSize: 11, padding: '3px 8px' }}
                      onClick={() => handleStatusChange(item.id, 'running')}>Reopen</button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          <button className="btn-ghost" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
          <span style={{ padding: '6px 12px', fontSize: 13 }}>Page {page} / {totalPages}</span>
          <button className="btn-ghost" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next →</button>
        </div>
      )}

      {/* Detail drawer */}
      {selected && (
        <OPLDetail id={selected} onClose={() => { setSelected(null); load() }} />
      )}

      {/* Create form */}
      {creating && (
        <OPLForm onClose={() => { setCreating(false); load() }} />
      )}
    </div>
  )
}
