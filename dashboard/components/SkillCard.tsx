'use client'

import type { Skill } from '@/lib/api'

interface SkillCardProps {
  skill: Skill
}

function scoreColor(score: number | null): string {
  if (score === null) return 'bg-gray-600'
  if (score >= 0.8) return 'bg-emerald-400'
  if (score >= 0.5) return 'bg-yellow-400'
  return 'bg-red-400'
}

function scoreLabel(score: number | null): string {
  if (score === null) return 'No data'
  return `${Math.round(score * 100)}%`
}

export default function SkillCard({ skill }: SkillCardProps) {
  const pct = skill.score !== null ? Math.min(Math.max(skill.score * 100, 0), 100) : 0

  return (
    <div className="rounded-xl border border-[#1e1e2e] bg-[#12121a] p-4 space-y-3 hover:border-violet-500/40 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-medium text-gray-100 text-sm leading-snug">{skill.name}</h3>
        <span className="text-xs font-mono text-gray-500 shrink-0">{scoreLabel(skill.score)}</span>
      </div>

      {skill.description && (
        <p className="text-xs text-gray-500 line-clamp-2">{skill.description}</p>
      )}

      {/* Effectiveness progress bar */}
      <div>
        <div className="h-1.5 bg-[#1e1e2e] rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${scoreColor(skill.score)}`}
            style={{ width: `${skill.score !== null ? pct : 0}%` }}
          />
        </div>
        {skill.score === null && (
          <p className="text-xs text-gray-600 mt-1">Effectiveness not measured yet</p>
        )}
      </div>
    </div>
  )
}
