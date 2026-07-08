import { useState, useEffect, useCallback } from 'react'

// Fetches GET /results once on mount. status is one of:
//   'loading'    – request in flight
//   'no-session' – backend answered 404 (no session processed yet)
//   'error'      – backend unreachable or returned an unexpected error
//   'ready'      – data is populated
export function useResults() {
  const [status, setStatus] = useState('loading')
  const [data, setData] = useState(null)

  const reload = useCallback(async () => {
    setStatus('loading')
    try {
      const res = await fetch('/api/results')
      if (res.status === 404) {
        setStatus('no-session')
        return
      }
      if (!res.ok) {
        setStatus('error')
        return
      }
      setData(await res.json())
      setStatus('ready')
    } catch {
      // fetch only throws on network failure — i.e. backend not running
      setStatus('error')
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  return { status, data, reload }
}
