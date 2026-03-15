'use client'

import { useEventStream } from '@/lib/sse'
import { api } from '@/lib/api'

interface LiveFeedProps {
  className?: string
}

export default function LiveFeed({ className = '' }: LiveFeedProps) {
  const { events, connected, error, clear } = useEventStream(api.eventsUrl(), 50)

  return (
    <div className={`rounded-xl border border-[#1e1e2e] bg-[#12121a] ${className}`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e1e2e]">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600'}`} />
          <span className="text-sm font-medium text-gray-300">Live Feed</span>
          {error && <span className="text-xs text-yellow-400">{error}</span>}
        </div>
        <button
          onClick={clear}
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          Clear
        </button>
      </div>

      <div className="h-64 overflow-y-auto p-3 space-y-1.5 font-mono text-xs">
        {events.length === 0 ? (
          <p className="text-gray-600 text-center py-8">
            {connected ? 'Waiting for events…' : 'Connecting…'}
          </p>
        ) : (
          events.map((e) => (
            <div key={e.id} className="flex gap-2 text-gray-400 hover:text-gray-200">
              <span className="text-gray-600 shrink-0">
                {new Date(e.timestamp).toLocaleTimeString()}
              </span>
              <span className="truncate">
                {typeof e.data === 'string'
                  ? e.data
                  : JSON.stringify(e.data)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
