import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  ApiError,
  type IndexingSnapshot,
  type IngestResponse,
  type QueryResponse,
  type SourceType,
} from './services/api'
import type { ConnectionState, ViewId } from './navigation'
import { CaptureForm } from './components/CaptureForm'
import { HomeView } from './components/HomeView'
import { ItemList } from './components/ItemList'
import { MenuIcon, PanelRightIcon, VaultIcon } from './components/icons'
import { Modal } from './components/Modal'
import { QueryPanel } from './components/QueryPanel'
import { SearchPanel } from './components/SearchPanel'
import { SettingsPanel } from './components/SettingsPanel'
import { Sidebar } from './components/Sidebar'
import { SourcePanel } from './components/SourcePanel'

function App() {
  const [view, setView] = useState<ViewId>('home')
  const [connection, setConnection] = useState<ConnectionState>({ kind: 'checking' })
  const [itemCount, setItemCount] = useState<number | null>(null)
  const [refreshToken, setRefreshToken] = useState(0)
  const [indexingByItemId, setIndexingByItemId] = useState<Record<number, IndexingSnapshot>>({})
  const [captureOpen, setCaptureOpen] = useState(false)
  const [captureMode, setCaptureMode] = useState<SourceType>('NOTE')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [queryResult, setQueryResult] = useState<QueryResponse | null>(null)
  const [askedQuestion, setAskedQuestion] = useState<string | null>(null)
  const [querySubmitting, setQuerySubmitting] = useState(false)
  const countRequestIdRef = useRef(0)

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

  const changeView = useCallback((next: ViewId) => {
    setView(next)
    setSidebarOpen(false)
    setSourcesOpen(false)
  }, [])

  const openCapture = useCallback((mode: SourceType = 'NOTE') => {
    setCaptureMode(mode)
    setCaptureOpen(true)
    setSidebarOpen(false)
  }, [])

  useEffect(() => {
    // Async fetch updates state after the request settles.
    // oxlint-disable-next-line react/set-state-in-effect
    void checkConnection()
  }, [checkConnection])

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setSidebarOpen(false)
        setSourcesOpen(false)
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [])

  useEffect(() => {
    // Async fetch updates state after the request settles.
    // oxlint-disable-next-line react/set-state-in-effect
    const requestId = ++countRequestIdRef.current
    void api
      .listItems({ limit: 1 })
      .then((page) => {
        if (requestId === countRequestIdRef.current) {
          setItemCount(page.total)
        }
      })
      .catch(() => {
        if (requestId === countRequestIdRef.current) {
          setItemCount(null)
        }
      })
    return () => {
      countRequestIdRef.current += 1
    }
  }, [refreshToken])

  const askPanel = (
    <QueryPanel
      result={queryResult}
      onResultChange={setQueryResult}
      onQuestionAsked={setAskedQuestion}
      onSubmittingChange={setQuerySubmitting}
      onViewSources={() => setSourcesOpen(true)}
    />
  )

  const sidebar = (
    <Sidebar
      view={view}
      onViewChange={changeView}
      onAddKnowledge={openCapture}
      connection={connection}
      itemCount={itemCount}
    />
  )

  const sourcePanel = (
    <SourcePanel
      result={queryResult}
      question={askedQuestion}
      submitting={querySubmitting}
    />
  )

  function renderView() {
    switch (view) {
      case 'home':
        return (
          <HomeView
            connection={connection}
            onAddKnowledge={openCapture}
            onNavigate={changeView}
            searchQuery={searchQuery}
            onSearchQueryChange={setSearchQuery}
            refreshToken={refreshToken}
            indexingByItemId={indexingByItemId}
            askPanel={askPanel}
          />
        )
      case 'all':
        return (
          <ItemList
            key="all"
            refreshToken={refreshToken}
            indexingByItemId={indexingByItemId}
          />
        )
      case 'notes':
        return (
          <ItemList
            key="notes"
            refreshToken={refreshToken}
            indexingByItemId={indexingByItemId}
            initialSourceType="NOTE"
            title="Notes"
            description="Text notes you've saved and indexed."
          />
        )
      case 'urls':
        return (
          <ItemList
            key="urls"
            refreshToken={refreshToken}
            indexingByItemId={indexingByItemId}
            initialSourceType="URL"
            title="Web pages"
            description="Links you've saved for later retrieval."
          />
        )
      case 'search':
        return (
          <SearchPanel
            query={searchQuery}
            onQueryChange={setSearchQuery}
            refreshToken={refreshToken}
            indexingByItemId={indexingByItemId}
            onAddKnowledge={() => openCapture()}
          />
        )
      case 'settings':
        return <SettingsPanel connection={connection} onRetryConnection={retryConnection} />
    }
  }

  return (
    <div className="flex min-h-screen bg-canvas text-ink">
      <div className="sticky top-0 hidden h-screen w-[260px] shrink-0 border-r border-line bg-rail xl:block">
        {sidebar}
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-line bg-canvas/95 px-4 backdrop-blur-sm xl:hidden">
          <div className="flex min-w-0 items-center gap-2.5">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation"
              className="btn btn-ghost h-9 w-9 shrink-0 p-0"
            >
              <MenuIcon className="h-5 w-5" />
            </button>
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-accent/25 bg-accent-wash text-accent">
              <VaultIcon className="h-4 w-4" />
            </div>
            <span className="truncate text-sm font-semibold">MindVault</span>
          </div>
          <button
            type="button"
            onClick={() => setSourcesOpen(true)}
            className="btn btn-secondary shrink-0 gap-2 px-3 py-2 text-xs"
          >
            <PanelRightIcon className="h-4 w-4" />
            Sources
            {queryResult && queryResult.sources.length > 0 && (
              <span className="rounded-full bg-accent-wash px-1.5 py-0.5 text-[10px] text-accent">
                {queryResult.sources.length}
              </span>
            )}
          </button>
        </header>

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 sm:py-8 xl:px-10 xl:py-10">
          <div className="mx-auto w-full max-w-[1100px]">{renderView()}</div>
          <footer className="mx-auto mt-12 w-full max-w-[1100px] border-t border-line pt-5 text-[11px] text-faint">
            MindVault · Capture, retrieve, and ask with sources
          </footer>
        </main>
      </div>

      <aside className="sticky top-0 hidden h-screen w-[350px] shrink-0 border-l border-line bg-rail xl:block">
        {sourcePanel}
      </aside>

      {sidebarOpen && (
        <div className="fixed inset-0 z-50 xl:hidden">
          <div
            className="absolute inset-0 bg-black/70"
            aria-hidden="true"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-[280px] max-w-[85vw] border-r border-line bg-rail shadow-2xl shadow-black/60">
            <Sidebar
              view={view}
              onViewChange={changeView}
              onAddKnowledge={openCapture}
              connection={connection}
              itemCount={itemCount}
              onClose={() => setSidebarOpen(false)}
            />
          </div>
        </div>
      )}

      {sourcesOpen && (
        <div className="fixed inset-0 z-50 xl:hidden">
          <div
            className="absolute inset-0 bg-black/70"
            aria-hidden="true"
            onClick={() => setSourcesOpen(false)}
          />
          <div className="absolute inset-y-0 right-0 w-[380px] max-w-[92vw] border-l border-line bg-rail shadow-2xl shadow-black/60">
            <SourcePanel
              result={queryResult}
              question={askedQuestion}
              submitting={querySubmitting}
              onClose={() => setSourcesOpen(false)}
            />
          </div>
        </div>
      )}

      <Modal
        open={captureOpen}
        onClose={() => setCaptureOpen(false)}
        title="Add knowledge"
        description="Save a note or a web page to your vault."
      >
        <CaptureForm
          key={captureMode}
          initialMode={captureMode}
          onIngested={handleIngested}
        />
      </Modal>
    </div>
  )
}

export default App
