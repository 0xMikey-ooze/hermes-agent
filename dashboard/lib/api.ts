/**
 * Typed API client for the Hermes Web API.
 * All methods respect NEXT_PUBLIC_HERMES_API_URL (default: http://localhost:3001).
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_HERMES_API_URL || 'http://localhost:3001'

// ── Types ──────────────────────────────────────────────────────────────────

export interface HermesStatus {
  version: string
  uptime_seconds: number
  model: string
  platform: string
  gateway_running: boolean
}

export interface Goal {
  id?: string
  description: string
  repo?: string
  status?: 'pending' | 'running' | 'done' | 'failed'
  priority?: string
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface GoalsResponse {
  goals: Goal[]
}

export interface Repo {
  owner: string
  repo: string
}

export interface ReposResponse {
  repos: Repo[]
}

export interface Skill {
  name: string
  description: string
  score: number | null
  path: string
}

export interface SkillsResponse {
  skills: Skill[]
}

export interface Session {
  session_id: string
  platform: string
  user_id?: string
  [key: string]: unknown
}

export interface SessionsResponse {
  sessions: Session[]
}

export interface MemorySearchResponse {
  results: unknown[]
  query: string
}

// ── Fetch wrapper ──────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }

  const apiKey = process.env.NEXT_PUBLIC_HERMES_API_KEY
  if (apiKey) {
    headers['X-API-Key'] = apiKey
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || `HTTP ${res.status}`)
  }

  return res.json() as Promise<T>
}

// ── API Methods ────────────────────────────────────────────────────────────

export const api = {
  // Status
  getStatus(): Promise<HermesStatus> {
    return apiFetch<HermesStatus>('/api/status')
  },

  // Goals
  getGoals(): Promise<GoalsResponse> {
    return apiFetch<GoalsResponse>('/api/goals')
  },
  addGoal(data: { repo: string; description: string; priority?: string }): Promise<{ tasks: Goal[] }> {
    return apiFetch('/api/goals', { method: 'POST', body: JSON.stringify(data) })
  },
  deleteGoal(id: string): Promise<{ cancelled: string }> {
    return apiFetch(`/api/goals/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },

  // Repos
  getRepos(): Promise<ReposResponse> {
    return apiFetch<ReposResponse>('/api/repos')
  },
  addRepo(data: { owner: string; repo: string }): Promise<Repo> {
    return apiFetch('/api/repos', { method: 'POST', body: JSON.stringify(data) })
  },
  deleteRepo(owner: string, repo: string): Promise<{ deleted: string }> {
    return apiFetch(`/api/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`, {
      method: 'DELETE',
    })
  },

  // Skills
  getSkills(): Promise<SkillsResponse> {
    return apiFetch<SkillsResponse>('/api/skills')
  },

  // Sessions
  getSessions(): Promise<SessionsResponse> {
    return apiFetch<SessionsResponse>('/api/sessions')
  },

  // Memory search
  searchMemory(query: string): Promise<MemorySearchResponse> {
    return apiFetch<MemorySearchResponse>(
      `/api/memory/search?q=${encodeURIComponent(query)}`
    )
  },

  // SSE events URL
  eventsUrl(): string {
    return `${BASE_URL}/api/events`
  },
}
