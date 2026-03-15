'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { api, type HermesStatus, type Goal } from '@/lib/api'
import StatusCard from '@/components/StatusCard'
import LiveFeed from '@/components/LiveFeed'

export default function HomePage() {
  const [status, setStatus] = useState<HermesStatus | null>(null)
  const [goals, setGoals] = useState<Goal[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    async function load() {
      try {
        const [s, g] = await Promise.all([api.getStatus(), api.getGoals()])
        if (!mounted) return
        setStatus(s)
        setGoals(g.goals)
      } catch {
        // API not reachable
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 10_000)
    return () => { mounted = false; clearInterval(interval) }
  }, [])

  const pending = goals.filter(g => g.status === 'pending' || !g.status).length
  const running = goals.filter(g => g.status === 'running').length
  const done = goals.filter(g => g.status === 'done').length
  const failed = goals.filter(g => g.status === 'failed').length

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h1 className="text-xl font-bold text-gray-100">Overview</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatusCard status={status} loading={loading} />

        {/* Task queue stats */}
        <div className="rounded-xl border border-[#1e1e2e] bg-[#12121a] p-5 space-y-3">
          <h2 className="font-semibold text-gray-100">Task Queue</h2>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Pending', count: pending, color: 'text-yellow-400' },
              { label: 'Running', count: running, color: 'text-blue-400' },
              { label: 'Done', count: done, color: 'text-emerald-400' },
              { label: 'Failed', count: failed, color: 'text-red-400' },
            ].map(({ label, count, color }) => (
              <div key={label} className="bg-[#0a0a0f] rounded-lg p-3">
                <div className={`text-2xl font-bold ${color}`}>{count}</div>
                <div className="text-xs text-gray-500 mt-0.5">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <LiveFeed />
    </div>
  )
}
