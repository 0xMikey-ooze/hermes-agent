'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { api, type Goal } from '@/lib/api'
import TaskTable from '@/components/TaskTable'
import AddTaskModal from '@/components/AddTaskModal'
import LiveFeed from '@/components/LiveFeed'

export default function RepoDetailPage() {
  const params = useParams()
  const owner = decodeURIComponent(params.owner as string)
  const repo = decodeURIComponent(params.repo as string)
  const fullRepo = `${owner}/${repo}`

  const [goals, setGoals] = useState<Goal[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)

  async function load() {
    try {
      const data = await api.getGoals()
      // Filter tasks for this repo
      const filtered = data.goals.filter(g => g.repo === fullRepo)
      setGoals(filtered)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [fullRepo])

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
        <div>
          <p className="text-sm text-gray-500 mb-0.5">Repository</p>
          <h1 className="text-xl font-bold font-mono">
            <span className="text-gray-500">{owner}/</span>
            <span className="text-gray-100">{repo}</span>
          </h1>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          + Add Task
        </button>
      </div>

      <div className="rounded-xl border border-[#1e1e2e] bg-[#12121a] p-5">
        <h2 className="font-semibold text-gray-300 mb-4">Tasks</h2>
        {loading ? (
          <div className="animate-pulse space-y-2">
            {[1, 2, 3].map(i => <div key={i} className="h-8 bg-[#1e1e2e] rounded" />)}
          </div>
        ) : (
          <TaskTable goals={goals} onDelete={handleDelete} />
        )}
      </div>

      <LiveFeed />

      {showAdd && (
        <AddTaskModal
          defaultRepo={fullRepo}
          onClose={() => setShowAdd(false)}
          onAdded={() => load()}
        />
      )}
    </div>
  )
}
