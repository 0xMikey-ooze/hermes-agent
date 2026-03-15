'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { api, type Skill } from '@/lib/api'
import SkillCard from '@/components/SkillCard'

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  useEffect(() => {
    api.getSkills()
      .then(data => setSkills(data.skills))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = skills.filter(s =>
    search === '' ||
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.description.toLowerCase().includes(search.toLowerCase())
  )

  // Sort: highest score first, then alphabetical for nulls
  const sorted = [...filtered].sort((a, b) => {
    if (a.score === null && b.score === null) return a.name.localeCompare(b.name)
    if (a.score === null) return 1
    if (b.score === null) return -1
    return b.score - a.score
  })

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold text-gray-100">
          Skills
          <span className="ml-2 text-sm font-normal text-gray-500">{skills.length} total</span>
        </h1>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search skills…"
          className="bg-[#12121a] border border-[#1e1e2e] rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-violet-500 w-48"
        />
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="rounded-xl border border-[#1e1e2e] bg-[#12121a] p-4 animate-pulse h-28" />
          ))}
        </div>
      ) : sorted.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          {search ? 'No skills match your search.' : 'No skills found.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          {sorted.map(skill => (
            <SkillCard key={skill.name} skill={skill} />
          ))}
        </div>
      )}
    </div>
  )
}
