'use client'

import { useEffect, useRef, useState, useCallback } from 'react'

export interface SSEEvent {
  id: string
  data: unknown
  timestamp: number
}

export interface UseEventStreamReturn {
  events: SSEEvent[]
  connected: boolean
  error: string | null
  clear: () => void
}

/**
 * React hook for consuming an SSE stream.
 *
 * @param url - Full URL of the SSE endpoint.
 * @param maxEvents - Max events to keep in memory (default: 100).
 */
export function useEventStream(
  url: string,
  maxEvents = 100
): UseEventStreamReturn {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const counterRef = useRef(0)

  const clear = useCallback(() => {
    setEvents([])
  }, [])

  useEffect(() => {
    if (!url) return

    let active = true

    const connect = () => {
      if (!active) return

      const es = new EventSource(url)
      esRef.current = es

      es.onopen = () => {
        if (!active) return
        setConnected(true)
        setError(null)
      }

      es.onmessage = (e: MessageEvent) => {
        if (!active) return
        let parsed: unknown
        try {
          parsed = JSON.parse(e.data)
        } catch {
          parsed = e.data
        }
        const event: SSEEvent = {
          id: String(++counterRef.current),
          data: parsed,
          timestamp: Date.now(),
        }
        setEvents((prev) => {
          const next = [event, ...prev]
          return next.slice(0, maxEvents)
        })
      }

      es.onerror = () => {
        if (!active) return
        setConnected(false)
        setError('Connection lost — retrying…')
        es.close()
        // Retry after 3s
        setTimeout(connect, 3000)
      }
    }

    connect()

    return () => {
      active = false
      esRef.current?.close()
      esRef.current = null
      setConnected(false)
    }
  }, [url, maxEvents])

  return { events, connected, error, clear }
}
