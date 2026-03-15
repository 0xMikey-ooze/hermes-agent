'use client'

import { useState, useMemo } from 'react'
import type { Goal } from '@/lib/api'

type SortKey = 'repo' | 'description' | 'status' | 'priority'
type SortDir = 'asc' | 'desc'

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-900/40 text-yellow-400',
  running: 'bg-blue-900/40 text-blue-400',
  done: 'bg-emerald-900/40 text-emerald-400',
  failed: 'bg-red-900/40 text-red-400',
}

interface TaskTableProps {
  goals: Goal[]
  onDelete?: (id: string) => void
}

export default function TaskTable({ goals, onDelete }: TaskTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('status')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const sorted = useMemo(() => {
    return [...goals].sort((a, b) => {
      const av = String(a[sortKey] ?? '')
      const bv = String(b[sortKey] ?? '')
      return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    })
  }, [goals, sortKey, sortDir])

  const toggle = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''

  if (goals.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500 text-sm">
        No tasks found.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#1e1e2e] text-gray-500 text-left">
            {(['repo', 'description', 'status', 'priority'] as SortKey[]).map(
              (col) => (
                <th
                  key={col}
                  className="pb-2 pr-4 cursor-pointer hover:text-gray-300 capitalize select-none"
                  onClick={() => toggle(col)}
                >
                  {col}
                  {arrow(col)}
                </th>
              )
            )}
            {onDelete && <th className="pb-2" />}
          </tr>
        </thead>
        <tbody>
          {sorted.map((g, i) => (
            <tr
              key={g.id || i}
              className="border-b border-[#1e1e2e]/50 hover:bg-[#12121a] transition-colors"
            >
              <td className="py-2.5 pr-4 font-mono text-xs text-gray-400">
                {g.repo || '—'}
              </td>
              <td className="py-2.5 pr-4 text-gray-200 max-w-xs truncate">
                {g.description}
              </td>
              <td className="py-2.5 pr-4">
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    STATUS_COLORS[g.status || 'pending'] ?? STATUS_COLORS.pending
                  }`}
                >
                  {g.status || 'pending'}
                </span>
              </td>
              <td className="py-2.5 pr-4 text-gray-400 capitalize">
                {g.priority || 'normal'}
              </td>
              {onDelete && (
                <td className="py-2.5 text-right">
                  <button
                    onClick={() => g.id && onDelete(g.id)}
                    className="text-gray-600 hover:text-red-400 transition-colors text-xs"
                    title="Cancel task"
                  >
                    ✕
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
