import type { QueryResponse } from '../services/api'
import { EmptyState } from './EmptyState'
import { CloseIcon, ExternalLinkIcon, LayersIcon, QuoteIcon } from './icons'
import { StatusBadge } from './StatusBadge'
import { Spinner } from './Spinner'

interface SourcePanelProps {
  result: QueryResponse | null
  question: string | null
  submitting: boolean
  onClose?: () => void
}

export function SourcePanel({ result, question, submitting, onClose }: SourcePanelProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-panel text-accent">
            <LayersIcon className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-ink">Sources &amp; context</h2>
            <p className="text-[11px] text-faint">Grounding for the latest answer</p>
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close source panel"
            className="btn btn-ghost h-8 w-8 shrink-0 p-0"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="scroll-slim flex-1 overflow-y-auto p-4">
        {submitting ? (
          <div className="space-y-3" role="status" aria-label="Retrieving sources">
            <div className="h-20 animate-pulse rounded-xl border border-line bg-sunken" />
            <div className="flex items-center gap-2 text-xs text-muted">
              <Spinner className="h-3.5 w-3.5" />
              Retrieving relevant sources…
            </div>
            {[0, 1, 2].map((index) => (
              <div key={index} className="h-36 animate-pulse rounded-xl border border-line bg-sunken" />
            ))}
          </div>
        ) : !result ? (
          <EmptyState
            icon={<LayersIcon className="h-5 w-5" />}
            title="No active sources"
            description="Ask a question in the workspace and the retrieved documents, citations, and snippets will appear here."
          />
        ) : (
          <>
            {question && (
              <div className="surface-quiet p-3.5">
                <div className="flex items-center gap-2 text-accent">
                  <QuoteIcon className="h-4 w-4" />
                  <p className="eyebrow text-accent">Question</p>
                </div>
                <p className="mt-2 text-sm leading-6 text-ink">{question}</p>
              </div>
            )}

            <div className="mt-5 flex items-center justify-between gap-3">
              <p className="eyebrow">Retrieved sources</p>
              <span className="rounded-full border border-line bg-panel px-2 py-0.5 text-[11px] text-muted">
                {result.sources.length}
              </span>
            </div>

            {result.sources.length === 0 ? (
              <div className="mt-3">
                <EmptyState
                  compact
                  icon={<LayersIcon className="h-5 w-5" />}
                  title="No citations returned"
                  description="The answer was generated without matching indexed chunks. Save more relevant knowledge and try again."
                />
              </div>
            ) : (
              <ol className="mt-3 space-y-3">
                {result.sources.map((source) => (
                  <li key={`${source.citation_id}-${source.item_id}`} className="surface-quiet p-3.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone="indigo">{source.citation_id}</StatusBadge>
                      <span className="text-[11px] text-faint">
                        {source.source_type === 'NOTE' ? 'Note' : 'Web page'} · #{source.item_id}
                      </span>
                    </div>
                    <p className="mt-2.5 text-sm font-medium leading-5 text-ink">
                      {source.title || `Item #${source.item_id}`}
                    </p>
                    <blockquote className="mt-3 border-l-2 border-accent/40 pl-3 text-xs leading-6 text-muted">
                      {source.snippet}
                    </blockquote>
                    {source.source_url && (
                      <a
                        href={source.source_url}
                        target="_blank"
                        rel="noreferrer"
                        title={source.source_url}
                        className="mt-3 inline-flex items-center gap-1.5 text-xs text-accent underline-offset-4 transition hover:underline"
                      >
                        <ExternalLinkIcon className="h-3.5 w-3.5" />
                        Open original
                      </a>
                    )}
                  </li>
                ))}
              </ol>
            )}

            <p className="mt-5 text-[11px] leading-5 text-faint">
              Snippets are taken from indexed chunks of your saved items. Citation IDs match the
              references returned with the answer.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
