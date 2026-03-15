'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, type Repo } from '@/lib/api'
import AddRepoModal from '@/components/AddRepoModal'

export default function ReposPage() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)

  async function load() {
    try {
      const data = await api.getRepos()
      setRepos(data.repos)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleDelete(owner: string, repo: string) {
    if (!confirm(`Remove ${owner}/${repo}?`)) return
    try {
      await api.deleteRepo(owner, repo)
      setRepos(r => r.filter(x => !(x.owner === owner && x.repo === repo)))
    } catch (err) {
      alert(String(err))
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-100">Repositories</h1>
        <button
          onClick={() => setShowAdd(true)}
          className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          + Add Repo
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="rounded-xl border border-[#1e1e2e] bg-[#12121a] p-4 animate-pulse h-24" />
          ))}
        </div>
      ) : repos.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <p>No repos watched yet.</p>
          <button
            onClick={() => setShowAdd(true)}
            className="mt-3 text-violet-400 hover:text-violet-300 text-sm"
          >
            Add your first repo →
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          {repos.map(r => (
            <div
              key={`${r.owner}/${r.repo}`}
              className="rounded-xl border border-[#1e1e2e] bg-[#12121a] p-4 hover:border-violet-500/40 transition-colors group"
            >
              <div className="flex items-start justify-between">
                <Link
                  href={`/repos/${r.owner}/${r.repo}`}
                  className="font-mono text-sm text-violet-400 hover:text-violet-300 leading-snug"
                >
                  <span className="text-gray-500">{r.owner}/</span>
                  <span className="text-gray-200">{r.repo}</span>
                </Link>
                <button
                  onClick={() => handleDelete(r.owner, r.repo)}
                  className="text-gray-600 hover:text-red-400 text-xs opacity-0 group-hover:opacity-100 transition-all"
                  title="Remove"
                >
                  ✕
                </button>
              </div>
              <Link
                href={`/repos/${r.owner}/${r.repo}`}
                className="mt-2 block text-xs text-gray-500 hover:text-gray-400"
              >
                View tasks →
              </Link>
            </div>
          ))}
        </div>
      )}

      {showAdd && (
        <AddRepoModal
          onClose={() => setShowAdd(false)}
          onAdded={() => load()}
        />
      )}
    </div>
  )
}
