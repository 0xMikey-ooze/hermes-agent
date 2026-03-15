'use client'

import type { HermesStatus } from '@/lib/api'

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

interface StatusCardProps {
  status: HermesStatus | null
  loading?: boolean
}

export default function StatusCard({ status, loading }: StatusCardProps) {
  if (loading) {
    return (
      <div className="rounded-xl border border-[#1e1e2e] bg-[#12121a] p-5 animate-pulse">
        <div className="h-4 bg-[#1e1e2e] rounded w-32 mb-4" />
        <div className="h-3 bg-[#1e1e2e] rounded w-24 mb-2" />
        <div className="h-3 bg-[#1e1e2e] rounded w-40" />
      </div>
    )
  }

  if (!status) {
    return (
      <div className="rounded-xl border border-red-900/40 bg-[#12121a] p-5">
        <p className="text-red-400 text-sm">⚠ Could not reach Hermes API</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-[#1e1e2e] bg-[#12121a] p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-gray-100">Gateway Status</h2>
        <span
          className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${
            status.gateway_running
              ? 'bg-emerald-900/40 text-emerald-400'
              : 'bg-red-900/40 text-red-400'
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${status.gateway_running ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
          {status.gateway_running ? 'Running' : 'Stopped'}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt className="text-gray-500">Version</dt>
        <dd className="text-gray-200 font-mono">{status.version}</dd>

        <dt className="text-gray-500">Model</dt>
        <dd className="text-gray-200 truncate">{status.model}</dd>

        <dt className="text-gray-500">Platform</dt>
        <dd className="text-gray-200">{status.platform}</dd>

        <dt className="text-gray-500">Uptime</dt>
        <dd className="text-gray-200">{formatUptime(status.uptime_seconds)}</dd>
      </dl>
    </div>
  )
}
