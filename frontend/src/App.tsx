import { useState } from 'react'
import OPLTab from './components/opl/OPLTab'
import BoschTab from './components/opl/BoschTab'
import RisksTab from './components/risks/RisksTab'
import LessonsTab from './components/lessons/LessonsTab'
import PlanningTab from './components/planning/PlanningTab'

type Tab = 'opl' | 'bosch' | 'risks' | 'lessons' | 'planning'

const TABS: { id: Tab; label: string }[] = [
  { id: 'opl',      label: 'Local OPL' },
  { id: 'bosch',    label: 'Bosch Tasks' },
  { id: 'risks',    label: 'Risks' },
  { id: 'lessons',  label: 'Lessons Learned' },
  { id: 'planning', label: 'Planning / Gantt' },
]

export default function App() {
  const [active, setActive] = useState<Tab>('opl')

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{
        background: 'var(--bosch-blue)', color: '#fff',
        padding: '0 24px', display: 'flex', alignItems: 'center', gap: 24, height: 52,
      }}>
        <div style={{ fontWeight: 700, fontSize: 16, letterSpacing: '0.02em' }}>
          DMC VCCU D65P — PM Tool
        </div>
        <nav style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setActive(t.id)}
              style={{
                background: active === t.id ? 'rgba(255,255,255,0.2)' : 'transparent',
                color: '#fff', border: 'none', padding: '6px 14px',
                borderRadius: 4, fontWeight: active === t.id ? 700 : 400,
              }}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Content */}
      <main style={{ flex: 1, padding: 20, maxWidth: 1600, width: '100%', margin: '0 auto' }}>
        {active === 'opl'      && <OPLTab />}
        {active === 'bosch'    && <BoschTab />}
        {active === 'risks'    && <RisksTab />}
        {active === 'lessons'  && <LessonsTab />}
        {active === 'planning' && <PlanningTab />}
      </main>
    </div>
  )
}
