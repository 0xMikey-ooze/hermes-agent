'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { api, type Goal } from '@/lib/api'
import TaskTable from '@/components/TaskTable'
import AddTaskModal from '@/components/AddTaskModal'

type StatusFilter = 'all' | 'pending' | 'running' | 'done' | 'failed'

const TABS: StatusFilter[] = ['all', 'pending', 'running', 'done', 'failed']

const TAB_STYLES: Record<StatusFilter, string> = {
  all: 'border-violet-500 text-violet-400',
  pending: 'border-yellow-500 text-yellow-400',
  running: 'border-blue-500 text-blue-400',
  done: 'border-emerald-500 text-emerald-400',
  failed: 'border-red-500 text-red-400',
}

export default function TasksPage() {
  const [goals, setGoals] = useState<Goal[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [showAdd, setShowAdd] = useState(false)

  async function load() {
    try {
      const data = await api.getGoals()
      setGoals(data.goals)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const filtered = filter === 'all'
    ? goals
    : goals.filter(g => (g.status || 'pending') === filter)

  async function handleDelete(id: string) {
    try {
      await api.deleteGoal(id)
      setGoals(g => g.filter(x => x.id !== id))
    } catch (err) {
      alert(String(err))
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-100">All Tasks</h1>
        <button
          onClick={() => setShowAdd(true)}
          className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          + Add Task
        </button>
      </div>

      {/* Status filter tabs */}
      <div className="flex gap-1 border-b border-[#1e1e2e]">
        {TABS.map(tab => {
          const count = tab === 'all' ? goals.length : goals.filter(g => (g.status || 'pending') === tab).length
          const active = filter === tab
          return (
            <button
              key={tab}
              onClick={() => setFilter(tab)}
              className={`px-3 py-2 text-sm capitalize transition-colors border-b-2 -mb-px ${
                active
                  ? TAB_STYLES[tab]
                  : 'border-transparent text-gray-500 hover:text-gray-300'
              }`}
            >
              {tab} <span className="text-xs ml-1 opacity-60">{count}</span>
            </button>
          )
        })}
      </div>

      <div className="rounded-xl border border-[#1e1e2e] bg-[#12121a] p-5">
        {loading ? (
          <div className="animate-pulse space-y-2">
            {[1, 2, 3].map(i => <div key={i} className="h-8 bg-[#1e1e2e] rounded" />)}
          </div>
        ) : (
          <TaskTable goals={filtered} onDelete={handleDelete} />
        )}
      </div>

      {showAdd && (
        <AddTaskModal
          onClose={() => setShowAdd(false)}
          onAdded={() => load()}
        />
      )}
    </div>
  )
}
