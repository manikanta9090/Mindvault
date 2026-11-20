import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  api,
  describeApiError,
  type IndexingSnapshot,
  type KnowledgeItemResponse,
  type SourceType,
} from '../services/api'
import { greetingForHour } from '../format'
import type { ConnectionState, ViewId } from '../navigation'
import { ConnectionPill } from './ConnectionStatus'
import { ArrowRightIcon, GlobeIcon, NoteIcon, RefreshIcon, SearchIcon, SparkleIcon } from './icons'
import { KnowledgeCard } from './KnowledgeCard'
import { StatusBadge } from './StatusBadge'

const GREETING = greetingForHour(new Date().getHours())

interface RecentCapturesProps {
  refreshToken: number
  indexingByItemId: Record<number, IndexingSnapshot>
  onViewAll: () => void
}

function RecentCaptures({ refreshToken, indexingByItemId, onViewAll }: RecentCapturesProps) {
  const [items, setItems] = useState<KnowledgeItemResponse[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const requestIdRef = useRef(0)

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setLoading(true)
    setError(null)

    try {
      const page = await api.listItems({ limit: 4 })
      if (requestId !== requestIdRef.current) {
        return
      }
      setItems(page.items)
      setTotal(page.total)
    } catch (cause) {
      if (requestId !== requestIdRef.current) {
        return
      }
      setError(describeApiError(cause, 'Recent items could not be loaded.'))
      setItems([])
      setTotal(null)
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    // Fetch is an external-system sync; state is set only after the await.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
    return () => {
      requestIdRef.current += 1
    }
  }, [load, refreshToken, reloadToken])

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Library</p>
          <h2 className="mt-1.5 text-lg font-semibold tracking-tight text-ink">
            Recently captured
          </h2>
        </div>
        <div className="flex items-center gap-3">
          {total !== null && (
            <StatusBadge tone="slate">
              {total} item{total === 1 ? '' : 's'} saved
            </StatusBadge>
          )}
          <button type="button" onClick={onViewAll} className="btn btn-ghost gap-1.5 text-xs">
            View all
            <ArrowRightIcon className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-bad/25 bg-bad/10 px-4 py-3 text-sm text-bad">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setReloadToken((value) => value + 1)}
            className="btn btn-ghost gap-1.5 px-2 py-1 text-xs text-bad"
          >
            <RefreshIcon className="h-3.5 w-3.5" />
            Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="mt-4 grid gap-4 sm:grid-cols-2" role="status" aria-label="Loading recent items">
          {[0, 1].map((index) => (
            <div key={index} className="surface-quiet h-52 animate-pulse p-4">
              <div className="h-8 w-8 rounded-lg bg-line" />
              <div className="mt-5 h-3 w-2/3 rounded bg-line" />
              <div className="mt-4 space-y-2">
                <div className="h-2.5 w-full rounded bg-line/70" />
                <div className="h-2.5 w-4/5 rounded bg-line/70" />
                <div className="h-2.5 w-3/5 rounded bg-line/70" />
              </div>
            </div>
          ))}
        </div>
      ) : items.length > 0 ? (
        <ul className="mt-4 grid gap-4 sm:grid-cols-2">
          {items.map((item) => (
            <li key={item.id}>
              <KnowledgeCard item={item} indexing={indexingByItemId[item.id]} />
            </li>
          ))}
        </ul>
      ) : !error ? (
        <div className="surface-quiet mt-4 px-6 py-10 text-center">
          <p className="text-sm font-medium text-ink">No recent captures</p>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted">
            Use Add knowledge to save your first note or URL. It will appear here and become
            available to questions once indexed.
          </p>
        </div>
      ) : null}
    </section>
  )
}

interface HomeViewProps {
  connection: ConnectionState
  onAddKnowledge: (mode: SourceType) => void
  onNavigate: (view: ViewId) => void
  searchQuery: string
  onSearchQueryChange: (value: string) => void
  refreshToken: number
  indexingByItemId: Record<number, IndexingSnapshot>
  askPanel: ReactNode
}

export function HomeView({
  connection,
  onAddKnowledge,
  onNavigate,
  searchQuery,
  onSearchQueryChange,
  refreshToken,
  indexingByItemId,
  askPanel,
}: HomeViewProps) {
  const quickActions = [
    {
      label: 'New note',
      hint: 'Capture a thought',
      icon: NoteIcon,
      onClick: () => onAddKnowledge('NOTE'),
    },
    {
      label: 'Save a URL',
      hint: 'Keep a page',
      icon: GlobeIcon,
      onClick: () => onAddKnowledge('URL'),
    },
    {
      label: 'Ask a question',
      hint: 'Answers with sources',
      icon: SparkleIcon,
      onClick: () =>
        document.getElementById('ask-workspace')?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
    },
  ]

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onNavigate('search')
  }

  return (
    <div className="space-y-10">
      <section className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <p className="eyebrow">MindVault workspace</p>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
            {GREETING}. Your knowledge is ready.
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-muted">
            Capture notes and links, browse what you&apos;ve saved, then ask questions grounded in
            your own knowledge — with citations you can trace back to the source.
          </p>
        </div>
        <ConnectionPill connection={connection} />
      </section>

      <section>
        <form onSubmit={handleSearch} className="surface flex flex-col gap-3 p-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-faint" />
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => onSearchQueryChange(event.target.value)}
              placeholder="Search your notes, links, and snippets…"
              aria-label="Search knowledge"
              className="field py-3 pl-10"
            />
          </div>
          <button type="submit" className="btn btn-secondary px-4 py-3">
            Search
            <ArrowRightIcon className="h-4 w-4" />
          </button>
        </form>

        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {quickActions.map((action) => {
            const Icon = action.icon
            return (
              <button
                key={action.label}
                type="button"
                onClick={action.onClick}
                className="surface flex items-center gap-3 p-3.5 text-left transition hover:border-line-strong hover:bg-panel/70"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-line bg-sunken text-muted">
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-ink">{action.label}</span>
                  <span className="block truncate text-[11px] text-faint">{action.hint}</span>
                </span>
              </button>
            )
          })}
        </div>
      </section>

      <RecentCaptures
        refreshToken={refreshToken}
        indexingByItemId={indexingByItemId}
        onViewAll={() => onNavigate('all')}
      />

      <section id="ask-workspace" className="scroll-mt-20">
        {askPanel}
      </section>
    </div>
  )
}
