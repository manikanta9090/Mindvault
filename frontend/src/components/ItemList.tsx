import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  describeApiError,
  type IndexingStatus,
  type ItemStatus,
  type KnowledgeItemResponse,
  type SourceType,
} from '../services/api'
import { StatusBadge } from './StatusBadge'

const PAGE_SIZE = 10

type BadgeTone = 'emerald' | 'rose' | 'amber' | 'indigo' | 'slate'

const SOURCE_TONES: Record<SourceType, BadgeTone> = {
  NOTE: 'indigo',
  URL: 'emerald',
}

const ITEM_STATUS_TONES: Record<ItemStatus, BadgeTone> = {
  PROCESSING: 'amber',
  COMPLETED: 'emerald',
  FAILED: 'rose',
}

const INDEXING_TONES: Record<IndexingStatus, BadgeTone> = {
  indexed: 'emerald',
  failed: 'rose',
  unavailable: 'amber',
}

const INDEXING_LABELS: Record<IndexingStatus, string> = {
  indexed: 'Indexed',
  failed: 'Index failed',
  unavailable: 'Index unavailable',
}

interface IndexingSnapshot {
  status: IndexingStatus
  errorCode: string | null
}

interface ItemListProps {
  refreshToken: number
  indexingByItemId: Record<number, IndexingSnapshot>
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString()
}

export function ItemList({ refreshToken, indexingByItemId }: ItemListProps) {
  const [items, setItems] = useState<KnowledgeItemResponse[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sourceType, setSourceType] = useState<SourceType | ''>('')
  const [status, setStatus] = useState<ItemStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const [reloadToken, setReloadToken] = useState(0)
  const requestIdRef = useRef(0)

  const loadItems = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setLoading(true)
    setError(null)

    try {
      const page = await api.listItems({
        limit: PAGE_SIZE,
        offset,
        source_type: sourceType || undefined,
        status: status || undefined,
      })
      if (requestId !== requestIdRef.current) {
        return
      }
      setItems(page.items)
      setTotal(page.total)
    } catch (cause) {
      if (requestId !== requestIdRef.current) {
        return
      }
      setError(describeApiError(cause, 'The library could not be loaded.'))
      setItems([])
      setTotal(0)
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
      }
    }
  }, [offset, sourceType, status])

  useEffect(() => {
    // Fetch is an external-system sync; state is set only after the await.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadItems()
    return () => {
      requestIdRef.current += 1
    }
  }, [loadItems, refreshToken, reloadToken])

  function changeSourceType(next: SourceType | '') {
    setSourceType(next)
    setOffset(0)
  }

  function changeStatus(next: ItemStatus | '') {
    setStatus(next)
    setOffset(0)
  }

  const firstItem = total === 0 ? 0 : offset + 1
  const lastItem = Math.min(offset + items.length, total)
  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur-sm sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">Knowledge library</h2>
          <p className="mt-1 text-sm text-slate-400">
            {total === 0 ? 'No saved items yet.' : `${total} saved item${total === 1 ? '' : 's'}`}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setReloadToken((value) => value + 1)}
          disabled={loading}
          className="rounded-lg border border-white/10 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-indigo-400/50 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <div>
          <label className="block text-xs font-semibold tracking-wide text-slate-400 uppercase" htmlFor="filter-source">
            Source type
          </label>
          <select
            id="filter-source"
            value={sourceType}
            onChange={(event) => changeSourceType(event.target.value as SourceType | '')}
            disabled={loading}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 focus:border-indigo-400/60 focus:outline-none focus:ring-2 focus:ring-indigo-400/20"
          >
            <option value="">All sources</option>
            <option value="NOTE">Text notes</option>
            <option value="URL">URLs</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold tracking-wide text-slate-400 uppercase" htmlFor="filter-status">
            Item status
          </label>
          <select
            id="filter-status"
            value={status}
            onChange={(event) => changeStatus(event.target.value as ItemStatus | '')}
            disabled={loading}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 focus:border-indigo-400/60 focus:outline-none focus:ring-2 focus:ring-indigo-400/20"
          >
            <option value="">All statuses</option>
            <option value="COMPLETED">Completed</option>
            <option value="PROCESSING">Processing</option>
            <option value="FAILED">Failed</option>
          </select>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="mt-5 rounded-xl border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm leading-6 text-rose-100"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div className="mt-6 flex items-center gap-3 rounded-2xl border border-white/10 bg-slate-950/40 px-5 py-10 text-sm text-slate-400" role="status">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.3" strokeWidth="3" />
            <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
          </svg>
          Loading your library…
        </div>
      ) : items.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-white/15 bg-slate-950/30 px-5 py-12 text-center">
          <p className="text-sm font-medium text-slate-200">No items match these filters</p>
          <p className="mt-2 text-sm text-slate-500">
            Save a note or URL from the Capture tab to see it here.
          </p>
        </div>
      ) : (
        <ul className="mt-6 grid gap-4 lg:grid-cols-2">
          {items.map((item) => {
            const indexing = indexingByItemId[item.id]
            return (
              <li
                key={item.id}
                className="rounded-2xl border border-white/10 bg-slate-950/40 p-5 transition hover:border-indigo-400/25"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-semibold text-white" title={item.title ?? undefined}>
                      {item.title || 'Untitled item'}
                    </h3>
                    <p className="mt-1 text-xs text-slate-500">Created {formatDate(item.created_at)}</p>
                  </div>
                  <span className="text-xs font-medium text-slate-500">#{item.id}</span>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <StatusBadge tone={SOURCE_TONES[item.source_type]}>{item.source_type}</StatusBadge>
                  <StatusBadge tone={ITEM_STATUS_TONES[item.status]}>{item.status}</StatusBadge>
                  <StatusBadge
                    tone={indexing ? INDEXING_TONES[indexing.status] : 'slate'}
                    title="GET /items does not expose indexing status. Recent captures are shown here."
                  >
                    {indexing ? INDEXING_LABELS[indexing.status] : 'Index unknown'}
                  </StatusBadge>
                </div>

                {item.source_url && (
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-4 block truncate text-xs text-indigo-300 underline-offset-4 hover:underline"
                  >
                    {item.source_url}
                  </a>
                )}

                <p className="mt-4 line-clamp-3 text-xs leading-6 text-slate-400">{item.content}</p>

                {indexing?.errorCode && (
                  <p className="mt-3 text-xs text-slate-500">
                    Indexing error: <code className="text-slate-300">{indexing.errorCode}</code>
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {!loading && total > 0 && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-5">
          <p className="text-xs text-slate-500">
            Showing {firstItem}–{lastItem} of {total}
          </p>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">
              Page {pageNumber} of {pageCount}
            </span>
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0 || loading}
              className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-indigo-400/50 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total || loading}
              className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-indigo-400/50 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
