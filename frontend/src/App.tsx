import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type IndexingStatus, type IngestResponse } from './services/api'
import { CaptureForm } from './components/CaptureForm'
import { ItemList } from './components/ItemList'
import { QueryPanel } from './components/QueryPanel'

type ConnectionState =
  | { kind: 'checking' }
  | { kind: 'connected'; application: string; version: string; status: string }
  | { kind: 'disconnected'; message: string }

type TabId = 'capture' | 'library' | 'ask'

interface IndexingSnapshot {
  status: IndexingStatus
  errorCode: string | null
}

const TABS: ReadonlyArray<{ id: TabId; label: string; hint: string }> = [
  { id: 'capture', label: 'Capture', hint: 'Save notes and URLs' },
  { id: 'library', label: 'Library', hint: 'Browse saved knowledge' },
  { id: 'ask', label: 'Ask', hint: 'Get cited answers' },
]

const VAULT_ICON = (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="h-6 w-6">
    <path
      d="M4 7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5v-9Z"
      stroke="currentColor"
      strokeWidth="1.6"
    />
    <circle cx="12" cy="12" r="3.1" stroke="currentColor" strokeWidth="1.6" />
    <path
      d="M12 8.9V7m0 10v-1.9M8.9 12H7m10 0h-1.9"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
    />
  </svg>
)

function StatusDot({ kind }: { kind: ConnectionState['kind'] }) {
  const color =
    kind === 'connected' ? 'bg-emerald-400' : kind === 'disconnected' ? 'bg-rose-400' : 'bg-amber-300'

  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0" aria-hidden="true">
      {kind === 'checking' && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-300 opacity-70" />
      )}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${color}`} />
    </span>
  )
}

function ConnectionPill({ connection }: { connection: ConnectionState }) {
  const label =
    connection.kind === 'checking'
      ? 'Checking connection'
      : connection.kind === 'connected'
        ? 'Backend connected'
        : 'Backend offline'

  const styles =
    connection.kind === 'connected'
      ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200'
      : connection.kind === 'disconnected'
        ? 'border-rose-400/25 bg-rose-400/10 text-rose-200'
        : 'border-amber-300/25 bg-amber-300/10 text-amber-100'

  return (
    <div
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-2.5 rounded-full border px-4 py-2 text-xs font-medium ${styles}`}
    >
      <StatusDot kind={connection.kind} />
      {label}
    </div>
  )
}

function ConnectionDetails({
  connection,
  onRetry,
}: {
  connection: ConnectionState
  onRetry: () => void
}) {
  return (
    <div className="mt-6 rounded-2xl border border-white/10 bg-slate-950/40 p-5">
      <div className="flex items-center justify-between gap-4">
        <p className="text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
          Connection status
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-indigo-400/50 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
        >
          Retry
        </button>
      </div>

      <div className="mt-4 flex items-center gap-2 text-sm font-medium text-white">
        <StatusDot kind={connection.kind} />
        {connection.kind === 'checking' && 'Contacting the API…'}
        {connection.kind === 'connected' && 'Connected to MindVault API'}
        {connection.kind === 'disconnected' && 'Unable to reach the MindVault API'}
      </div>

      {connection.kind === 'connected' ? (
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-xl bg-white/5 p-3">
            <dt className="text-xs text-slate-400">Application</dt>
            <dd className="mt-1 font-medium text-slate-100">{connection.application}</dd>
          </div>
          <div className="rounded-xl bg-white/5 p-3">
            <dt className="text-xs text-slate-400">Version</dt>
            <dd className="mt-1 font-medium text-slate-100">{connection.version}</dd>
          </div>
          <div className="col-span-2 rounded-xl bg-white/5 p-3">
            <dt className="text-xs text-slate-400">Health</dt>
            <dd className="mt-1 font-medium text-emerald-300">{connection.status}</dd>
          </div>
        </dl>
      ) : (
        <p className="mt-3 text-sm leading-6 text-slate-400">
          {connection.kind === 'checking'
            ? 'Waiting for GET /health to respond.'
            : `${connection.message} Start the backend and choose Retry.`}
        </p>
      )}
    </div>
  )
}

function App() {
  const [connection, setConnection] = useState<ConnectionState>({ kind: 'checking' })
  const [activeTab, setActiveTab] = useState<TabId>('capture')
  const [refreshToken, setRefreshToken] = useState(0)
  const [indexingByItemId, setIndexingByItemId] = useState<Record<number, IndexingSnapshot>>({})

  const checkConnection = useCallback(async () => {
    try {
      const health = await api.getHealth()
      setConnection({
        kind: 'connected',
        application: health.application,
        version: health.version,
        status: health.status,
      })
    } catch (error) {
      setConnection({
        kind: 'disconnected',
        message:
          error instanceof ApiError
            ? error.message
            : 'An unexpected error occurred while checking the backend.',
      })
    }
  }, [])

  const retryConnection = useCallback(() => {
    setConnection({ kind: 'checking' })
    void checkConnection()
  }, [checkConnection])

  const handleIngested = useCallback((result: IngestResponse) => {
    setIndexingByItemId((current) => ({
      ...current,
      [result.id]: {
        status: result.indexing_status,
        errorCode: result.indexing_error_code,
      },
    }))
    setRefreshToken((value) => value + 1)
  }, [])

  useEffect(() => {
    // Initial health fetch is an external-system sync; state is only set after the await.
    // oxlint-disable-next-line react/set-state-in-effect
    void checkConnection()
  }, [checkConnection])

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-slate-100">
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_-10%,rgba(99,102,241,0.22),transparent_45%),radial-gradient(circle_at_90%_10%,rgba(217,70,239,0.14),transparent_40%)]"
        aria-hidden="true"
      />

      <div className="relative">
        <header className="border-b border-white/10">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-400 to-violet-600 text-white shadow-lg shadow-indigo-500/20">
                {VAULT_ICON}
              </div>
              <div>
                <p className="text-base font-semibold tracking-tight text-white">MindVault</p>
                <p className="text-xs text-slate-400">Your personal knowledge layer</p>
              </div>
            </div>
            <ConnectionPill connection={connection} />
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-6 pb-20 pt-12 lg:pt-16">
          <div className="grid items-start gap-10 lg:grid-cols-[1.15fr_0.85fr] lg:gap-14">
            <section>
              <span className="inline-flex items-center gap-2 rounded-full border border-indigo-400/25 bg-indigo-400/10 px-3 py-1 text-xs font-medium text-indigo-200">
                <span className="h-1.5 w-1.5 rounded-full bg-indigo-300" />
                Phase 4 · RAG workspace
              </span>

              <h1 className="mt-6 max-w-3xl text-4xl leading-[1.1] font-semibold tracking-tight text-white sm:text-5xl">
                Your knowledge.{' '}
                <span className="bg-gradient-to-r from-indigo-300 via-violet-300 to-fuchsia-300 bg-clip-text text-transparent">
                  Always within reach.
                </span>
              </h1>

              <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
                Save notes and URLs, browse your library, and ask questions grounded in your own
                knowledge — with citations back to the sources you saved.
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                {['Notes & links', 'Automatic indexing', 'Answers with citations'].map((item) => (
                  <span
                    key={item}
                    className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300"
                  >
                    {item}
                  </span>
                ))}
              </div>
            </section>

            <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur-sm sm:p-8">
              <h2 className="text-lg font-semibold text-white">Workspace ready</h2>
              <p className="mt-2 text-sm leading-7 text-slate-300">
                Capture content, review what has been indexed, then ask MindVault a question.
                Indexing status is reported separately from successful saving.
              </p>
              <ConnectionDetails connection={connection} onRetry={retryConnection} />
            </section>
          </div>

          <div className="mt-14">
            <div
              role="tablist"
              aria-label="MindVault workspace"
              className="grid gap-3 sm:grid-cols-3"
            >
              {TABS.map((tab) => {
                const active = activeTab === tab.id
                return (
                  <button
                    key={tab.id}
                    id={`tab-${tab.id}`}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    aria-controls="workspace-panel"
                    onClick={() => setActiveTab(tab.id)}
                    className={`rounded-2xl border px-5 py-4 text-left transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 ${
                      active
                        ? 'border-indigo-400/40 bg-indigo-500/10'
                        : 'border-white/10 bg-white/[0.03] hover:border-white/20 hover:bg-white/[0.06]'
                    }`}
                  >
                    <span className={`block text-sm font-semibold ${active ? 'text-white' : 'text-slate-200'}`}>
                      {tab.label}
                    </span>
                    <span className="mt-1 block text-xs text-slate-500">{tab.hint}</span>
                  </button>
                )
              })}
            </div>

            <div
              id="workspace-panel"
              role="tabpanel"
              aria-labelledby={`tab-${activeTab}`}
              className="mt-6"
            >
              {activeTab === 'capture' && <CaptureForm onIngested={handleIngested} />}
              {activeTab === 'library' && (
                <ItemList refreshToken={refreshToken} indexingByItemId={indexingByItemId} />
              )}
              {activeTab === 'ask' && <QueryPanel />}
            </div>
          </div>
        </main>

        <footer className="border-t border-white/10">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-6 text-xs text-slate-500">
            <span>MindVault · Capture, retrieve, and ask with sources</span>
            <span>React · TypeScript · Vite · Tailwind CSS · FastAPI</span>
          </div>
        </footer>
      </div>
    </div>
  )
}

export default App
