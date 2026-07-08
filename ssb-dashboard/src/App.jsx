import { useResults } from './hooks/useResults'

export default function App() {
  const { status, data, reload } = useResults()

  if (status === 'loading') {
    return <p>Loading results…</p>
  }

  if (status === 'no-session') {
    return <p>No session yet — process a workout session and refresh.</p>
  }

  if (status === 'error') {
    return (
      <p>
        Could not reach the backend. Is it running on localhost:8000?{' '}
        <button onClick={reload}>Retry</button>
      </p>
    )
  }

  // Placeholder: raw JSON dump. Panels replace this one at a time.
  return <pre>{JSON.stringify(data, null, 2)}</pre>
}
