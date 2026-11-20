import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  describeApiError,
  type IndexingSnapshot,
  type KnowledgeItemResponse,
  type SourceType,
} from '../services/api'
import { EmptyState } from './EmptyState'
import { CloseIcon, SearchIcon } from './icons'
import { KnowledgeCard } from './KnowledgeCard'
import { Spinner } from './Spinner'

const SEARCH_LIMIT = 100

type SourceFilter = SourceType | 'ALL'

interface SearchPanelProps {
  query: string
  onQueryChange: (value: string) => void
  refreshToken: number
  indexingByItemId: Record<number, IndexingSnapshot>
  onAddKnowledge: () => void
}

export function SearchPanel({
  query,
  onQueryChange,
  refreshToken,
  indexingByItemId,
  onAddKnowledge,
}: SearchPanelProps) {
  const [items, setItems] = useState<KnowledgeItemResponse[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('ALL')
  const requestIdRef = useRef(0)

  const loadItems = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setLoading(true)
    setError(null)

    try {
      const page = await api.listItems({ limit: SEARCH_LIMIT })
      if (requestId !== requestIdRef.current) {
        return
      }
      setItems(page.items)
      setTotal(page.total)
    } catch (cause) {
      if (requestId !== requestIdRef.current) {
        return
      }
      setError(describeApiError(cause, 'Search could not load your vault.'))
      setItems([])
      setTotal(0)
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    // Fetch is an external-system sync; state is set only after the await.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadItems()
    return () => {
      requestIdRef.current += 1
    }
  }, [loadItems, refreshToken])

  const normalized = query.trim().toLowerCase()
  const filtered = items.filter((item) => {
    if (sourceFilter !== 'ALL' && item.source_type !== sourceFilter) {
      return false
    }
    if (!normalized) {
      return true
    }
    return [item.title, item.content, item.source_url, `#${item.id}`].some((value) =>
      value?.toLowerCase().includes(normalized),
    )
  })

  return (
    <section className="surface p-5 sm:p-7">
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-ink">Search your vault</h2>
        <p className="mt-1 text-sm leading-6 text-muted">
          Filters saved titles, content, and URLs in your vault. Answers from the AI workspace are
          semantic and use the same indexed knowledge.
        </p>
      </div>

      <div className="relative mt-6">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-faint" />
        <input
          type="search"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Try a topic, a title, or a domain…"
          aria-label="Search knowledge"
          className="field py-3 pl-10 pr-10"
        />
        {query && (
          <button
            type="button"
            onClick={() => onQueryChange('')}
            aria-label="Clear search"
            className="btn btn-ghost absolute top-1/2 right-2 h-7 w-7 -translate-y-1/2 p-0"
          >
            <CloseIcon className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {(
          [
            { id: 'ALL', label: 'All sources' },
            { id: 'NOTE', label: 'Notes' },
            { id: 'URL', label: 'Web pages' },
          ] as const
        ).map((filter) => {
          const active = sourceFilter === filter.id
          return (
            <button
              key={filter.id}
              type="button"
              onClick={() => setSourceFilter(filter.id)}
              aria-pressed={active}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                active
                  ? 'border-accent/30 bg-accent-wash text-accent'
                  : 'border-line text-muted hover:border-line-strong hover:text-ink'
              }`}
            >
              {filter.label}
            </button>
          )
        })}
        <span className="ml-auto text-xs text-faint">
          {loading
            ? 'Loading…'
            : normalized || sourceFilter !== 'ALL'
              ? `${filtered.length} of ${Math.min(total, SEARCH_LIMIT)} shown`
              : `${Math.min(total, SEARCH_LIMIT)} most recent items`}
        </span>
      </div>

      {error && (
        <div
          role="alert"
          className="mt-5 rounded-xl border border-bad/25 bg-bad/10 px-4 py-3 text-sm leading-6 text-bad"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div className="mt-6 flex items-center gap-3 rounded-xl border border-line bg-sunken px-4 py-8 text-sm text-muted" role="status">
          <Spinner />
          Loading your vault…
        </div>
      ) : total === 0 ? (
        <div className="mt-6">
          <EmptyState
            icon={<SearchIcon className="h-5 w-5" />}
            title="Your vault is empty"
            description="Save a note or URL first, then come back to search across everything you've captured."
            action={
              <button type="button" onClick={onAddKnowledge} className="btn btn-primary px-4 py-2.5">
                Add knowledge
              </button>
            }
          />
        </div>
      ) : filtered.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            icon={<SearchIcon className="h-5 w-5" />}
            title="No matches found"
            description="Nothing matched those terms. Try a broader word or clear the source filter."
            action={
              <button
                type="button"
                onClick={() => {
                  onQueryChange('')
                  setSourceFilter('ALL')
                }}
                className="btn btn-secondary px-4 py-2.5"
              >
                Clear filters
              </button>
            }
          />
        </div>
      ) : (
        <ul className="mt-6 grid gap-4 lg:grid-cols-2">
          {filtered.map((item) => (
            <li key={item.id}>
              <KnowledgeCard item={item} indexing={indexingByItemId[item.id]} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
