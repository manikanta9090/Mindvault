import type { IndexingSnapshot, ItemStatus, KnowledgeItemResponse, SourceType } from '../services/api'
import { formatDateShort } from '../format'
import { ExternalLinkIcon, GlobeIcon, NoteIcon } from './icons'
import { StatusBadge } from './StatusBadge'

const SOURCE_TONES: Record<SourceType, 'indigo' | 'emerald'> = {
  NOTE: 'indigo',
  URL: 'emerald',
}

const STATUS_TONES: Record<ItemStatus, 'amber' | 'emerald' | 'rose'> = {
  PROCESSING: 'amber',
  COMPLETED: 'emerald',
  FAILED: 'rose',
}

const INDEXING_TONES: Record<IndexingSnapshot['status'], 'emerald' | 'rose' | 'amber' | 'slate'> = {
  indexed: 'emerald',
  failed: 'rose',
  unavailable: 'amber',
}

const INDEXING_LABELS: Record<IndexingSnapshot['status'], string> = {
  indexed: 'Indexed',
  failed: 'Index failed',
  unavailable: 'Index unavailable',
}

function displayUrl(value: string): string {
  try {
    return new URL(value).hostname.replace(/^www\./, '')
  } catch {
    return value
  }
}

interface KnowledgeCardProps {
  item: KnowledgeItemResponse
  indexing?: IndexingSnapshot
}

export function KnowledgeCard({ item, indexing }: KnowledgeCardProps) {
  const isNote = item.source_type === 'NOTE'

  return (
    <article className="surface-quiet group flex flex-col p-4 transition hover:border-line-strong hover:bg-raised/50">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line bg-panel text-faint transition group-hover:text-accent">
          {isNote ? <NoteIcon className="h-4 w-4" /> : <GlobeIcon className="h-4 w-4" />}
        </div>
        <div className="min-w-0 flex-1">
          <h3
            className="truncate text-sm font-semibold text-ink"
            title={item.title ?? undefined}
          >
            {item.title || (isNote ? 'Untitled note' : 'Untitled link')}
          </h3>
          <p className="mt-0.5 text-[11px] text-faint">
            #{item.id} · {formatDateShort(item.created_at)}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        <StatusBadge tone={SOURCE_TONES[item.source_type]} dot>
          {isNote ? 'Note' : 'Web page'}
        </StatusBadge>
        <StatusBadge tone={STATUS_TONES[item.status]}>{item.status.toLowerCase()}</StatusBadge>
        <StatusBadge
          tone={indexing ? INDEXING_TONES[indexing.status] : 'slate'}
          title={
            indexing
              ? undefined
              : 'GET /items does not expose indexing status. Recent captures are shown here.'
          }
        >
          {indexing ? INDEXING_LABELS[indexing.status] : 'Index unknown'}
        </StatusBadge>
      </div>

      <p className="mt-3 line-clamp-3 text-xs leading-6 text-muted">
        {item.content || 'No content stored for this item.'}
      </p>

      <div className="mt-auto pt-4">
        {item.source_url && (
          <a
            href={item.source_url}
            target="_blank"
            rel="noreferrer"
            title={item.source_url}
            className="inline-flex max-w-full items-center gap-1.5 text-xs text-accent underline-offset-4 transition hover:underline"
          >
            <ExternalLinkIcon className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{displayUrl(item.source_url)}</span>
          </a>
        )}
        {indexing?.errorCode && (
          <p className="mt-2 text-[11px] text-faint">
            Indexing error: <code className="text-muted">{indexing.errorCode}</code>
          </p>
        )}
      </div>
    </article>
  )
}
