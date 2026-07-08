import { useState, useEffect, useCallback } from 'react'

// Fetches GET /results/samples once on mount. status is one of:
//   'loading'    – request in flight
//   'no-session' – backend answered 404 (no session processed yet)
//   'error'      – backend unreachable or returned an unexpected error
//   'ready'      – data is populated
export function useSamples() {
  const [status, setStatus] = useState('loading')
  const [samples, setSamples] = useState([])

  const reload = useCallback(async () => {
    setStatus('loading')
    try {
      const res = await fetch('/api/results/samples')
      if (res.status === 404) {
        setStatus('no-session')
        return
      }
      if (!res.ok) {
        setStatus('error')
        return
      }
      setSamples(await res.json())
      setStatus('ready')
    } catch {
      setStatus('error')
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  return { status, samples, reload }
}