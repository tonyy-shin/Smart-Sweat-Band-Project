import { useState, useEffect, useCallback } from 'react'

// Fetches GET /history once on mount. status is one of:
//   'loading' – request in flight
//   'error'   – backend unreachable or returned an unexpected error
//   'ready'   – data is populated (an empty array is a valid ready state —
//                /history returns 200 + [] for zero sessions, never 404)
export function useHistory() {
  const [status, setStatus] = useState('loading')
  const [sessions, setSessions] = useState([])

  const reload = useCallback(async () => {
    setStatus('loading')
    try {
      const res = await fetch('/api/history')
      if (!res.ok) {
        setStatus('error')
        return
      }
      setSessions(await res.json())
      setStatus('ready')
    } catch {
      setStatus('error')
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  return { status, sessions, reload }
}