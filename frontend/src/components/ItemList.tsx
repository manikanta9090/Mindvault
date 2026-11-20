import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  describeApiError,
  type IndexingSnapshot,
  type ItemStatus,
  type KnowledgeItemResponse,
  type SourceType,
} from '../services/api'
import { EmptyState } from './EmptyState'
import { FilterIcon, InboxIcon, RefreshIcon } from './icons'
import { KnowledgeCard } from './KnowledgeCard'
import { Spinner } from './Spinner'

const PAGE_SIZE = 10

interface ItemListProps {
  refreshToken: number
  indexingByItemId: Record<number, IndexingSnapshot>
  initialSourceType?: SourceType | ''
  title?: string
  description?: string
}

export function ItemList({
  refreshToken,
  indexingByItemId,
  initialSourceType = '',
  title = 'Knowledge library',
  description,
}: ItemListProps) {
  const [items, setItems] = useState<KnowledgeItemResponse[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sourceType, setSourceType] = useState<SourceType | ''>(initialSourceType)
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
    <section className="surface p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-ink">{title}</h2>
          <p className="mt-1 text-sm text-muted">
            {description ??
              (total === 0
                ? 'No saved items yet.'
                : `${total} saved item${total === 1 ? '' : 's'} in your vault`)}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setReloadToken((value) => value + 1)}
          disabled={loading}
          className="btn btn-secondary px-3 py-2 text-xs"
        >
          <RefreshIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <div>
          <label
            className="block text-xs font-semibold tracking-wide text-faint uppercase"
            htmlFor="filter-source"
          >
            Source type
          </label>
          <select
            id="filter-source"
            className="field mt-2"
            value={sourceType}
            onChange={(event) => changeSourceType(event.target.value as SourceType | '')}
            disabled={loading}
          >
            <option value="">All sources</option>
            <option value="NOTE">Text notes</option>
            <option value="URL">Web pages</option>
          </select>
        </div>
        <div>
          <label
            className="block text-xs font-semibold tracking-wide text-faint uppercase"
            htmlFor="filter-status"
          >
            Item status
          </label>
          <select
            id="filter-status"
            className="field mt-2"
            value={status}
            onChange={(event) => changeStatus(event.target.value as ItemStatus | '')}
            disabled={loading}
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
          className="mt-5 rounded-xl border border-bad/25 bg-bad/10 px-4 py-3 text-sm leading-6 text-bad"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div
          className="mt-6 grid gap-4 lg:grid-cols-2"
          role="status"
          aria-label="Loading your library"
        >
          {Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="surface-quiet h-52 animate-pulse p-4">
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-line" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 w-2/3 rounded bg-line" />
                  <div className="h-2.5 w-1/3 rounded bg-line/70" />
                </div>
              </div>
              <div className="mt-5 h-5 w-3/4 rounded-full bg-line/80" />
              <div className="mt-4 space-y-2">
                <div className="h-2.5 w-full rounded bg-line/70" />
                <div className="h-2.5 w-11/12 rounded bg-line/70" />
                <div className="h-2.5 w-4/6 rounded bg-line/70" />
              </div>
            </div>
          ))}
          <span className="sr-only">
            <Spinner /> Loading your library…
          </span>
        </div>
      ) : items.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            icon={<InboxIcon className="h-5 w-5" />}
            title="Nothing here yet"
            description={
              sourceType || status
                ? 'No items match these filters. Try a different source type or status.'
                : 'Save a note or URL to start building your knowledge library.'
            }
          />
        </div>
      ) : (
        <ul className="mt-6 grid gap-4 lg:grid-cols-2">
          {items.map((item) => (
            <li key={item.id}>
              <KnowledgeCard item={item} indexing={indexingByItemId[item.id]} />
            </li>
          ))}
        </ul>
      )}

      {!loading && total > 0 && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
          <p className="inline-flex items-center gap-2 text-xs text-faint">
            <FilterIcon className="h-3.5 w-3.5" />
            Showing {firstItem}–{lastItem} of {total}
          </p>
          <div className="flex items-center gap-2">
            <span className="mr-1 text-xs text-faint">
              Page {pageNumber} of {pageCount}
            </span>
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0 || loading}
              className="btn btn-secondary px-3 py-1.5 text-xs"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total || loading}
              className="btn btn-secondary px-3 py-1.5 text-xs"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
