import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  api,
  describeApiError,
  type IndexingStatus,
  type IngestRequest,
  type IngestResponse,
  type SourceType,
} from '../services/api'
import { StatusBadge } from './StatusBadge'

const INPUT_CLASS =
  'mt-2 w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 transition focus:border-indigo-400/60 focus:outline-none focus:ring-2 focus:ring-indigo-400/20'
const LABEL_CLASS = 'block text-xs font-semibold tracking-wide text-slate-300 uppercase'

const INDEXING_TONES: Record<IndexingStatus, 'emerald' | 'rose' | 'amber'> = {
  indexed: 'emerald',
  failed: 'rose',
  unavailable: 'amber',
}

function indexingLabel(result: IngestResponse): string {
  if (result.indexing_status === 'indexed') {
    const count = result.indexed_chunk_count
    return count === null ? 'Searchable now' : `Searchable now · ${count} chunk${count === 1 ? '' : 's'}`
  }
  if (result.indexing_status === 'failed') {
    return 'Saved but not searchable'
  }
  return 'Saved; indexing unavailable'
}

interface CaptureFormProps {
  onIngested: (result: IngestResponse) => void
}

export function CaptureForm({ onIngested }: CaptureFormProps) {
  const [mode, setMode] = useState<SourceType>('NOTE')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<IngestResponse | null>(null)

  function changeMode(next: SourceType) {
    if (next === mode) {
      return
    }
    setMode(next)
    setError(null)
    setResult(null)
  }

  function validate(): string | null {
    if (title.trim().length > 512) {
      return 'Title must be 512 characters or fewer.'
    }

    if (mode === 'NOTE') {
      return content.trim() ? null : 'Note content is required.'
    }

    const candidate = sourceUrl.trim()
    if (!candidate) {
      return 'A URL is required.'
    }
    if (candidate.length > 2048) {
      return 'URL must be 2048 characters or fewer.'
    }

    try {
      const parsed = new URL(candidate)
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
        return 'URL must use http or https.'
      }
    } catch {
      return 'Enter a valid URL, for example https://example.com/article.'
    }

    return null
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) {
      return
    }

    const validationMessage = validate()
    if (validationMessage) {
      setError(validationMessage)
      setResult(null)
      return
    }

    setSubmitting(true)
    setError(null)

    const payload: IngestRequest = {
      title: title.trim() || null,
      content: mode === 'NOTE' ? content : '',
      source_type: mode,
      source_url: mode === 'URL' ? sourceUrl.trim() : null,
    }

    try {
      const saved = await api.ingestItem(payload)
      setResult(saved)
      setTitle('')
      setContent('')
      setSourceUrl('')
      onIngested(saved)
    } catch (cause) {
      setError(describeApiError(cause, 'The item could not be saved.'))
      setResult(null)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur-sm sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">Capture knowledge</h2>
          <p className="mt-1 text-sm text-slate-400">
            Save a note or link. Indexing starts automatically after the item is stored.
          </p>
        </div>
        <div className="inline-flex rounded-xl border border-white/10 bg-slate-950/50 p-1" role="group" aria-label="Source type">
          {(['NOTE', 'URL'] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={mode === option}
              onClick={() => changeMode(option)}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 ${
                mode === option
                  ? 'bg-indigo-500/20 text-indigo-100 shadow-sm'
                  : 'text-slate-400 hover:text-slate-100'
              }`}
            >
              {option === 'NOTE' ? 'Text note' : 'URL'}
            </button>
          ))}
        </div>
      </div>

      <form className="mt-6 space-y-5" onSubmit={handleSubmit} noValidate>
        <div>
          <label className={LABEL_CLASS} htmlFor="capture-title">
            Title <span className="font-normal normal-case text-slate-500">(optional)</span>
          </label>
          <input
            id="capture-title"
            className={INPUT_CLASS}
            value={title}
            maxLength={512}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={mode === 'NOTE' ? 'What is this note about?' : 'Optional page title'}
            disabled={submitting}
          />
        </div>

        {mode === 'NOTE' ? (
          <div>
            <label className={LABEL_CLASS} htmlFor="capture-content">
              Content
            </label>
            <textarea
              id="capture-content"
              className={`${INPUT_CLASS} min-h-40 resize-y`}
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="Paste the text you want to remember…"
              disabled={submitting}
            />
          </div>
        ) : (
          <div>
            <label className={LABEL_CLASS} htmlFor="capture-url">
              URL
            </label>
            <input
              id="capture-url"
              className={INPUT_CLASS}
              value={sourceUrl}
              maxLength={2048}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="https://example.com/article"
              inputMode="url"
              disabled={submitting}
            />
            <p className="mt-2 text-xs leading-5 text-slate-500">
              MindVault fetches the page and extracts readable text. Pasted content is ignored.
            </p>
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="rounded-xl border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm leading-6 text-rose-100"
          >
            {error}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={submitting}
            aria-busy={submitting}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:from-indigo-400 hover:to-violet-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting && (
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.3" strokeWidth="3" />
                <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              </svg>
            )}
            {submitting ? 'Saving…' : mode === 'NOTE' ? 'Save note' : 'Save URL'}
          </button>
          {submitting && <span className="text-xs text-slate-500">Please wait…</span>}
        </div>
      </form>

      {result && (
        <div
          role="status"
          className="mt-6 rounded-2xl border border-emerald-400/20 bg-emerald-400/5 p-5"
        >
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone="emerald">Item saved</StatusBadge>
            <StatusBadge tone={INDEXING_TONES[result.indexing_status]}>
              {indexingLabel(result)}
            </StatusBadge>
          </div>
          <p className="mt-3 text-sm text-slate-300">
            <span className="font-medium text-white">
              {result.title || (result.source_type === 'NOTE' ? 'Untitled note' : 'Untitled link')}
            </span>{' '}
            was stored as item #{result.id}.
          </p>
          {result.indexing_status !== 'indexed' && result.indexing_error_code && (
            <p className="mt-2 text-xs text-slate-400">
              Indexing error code: <code className="text-slate-200">{result.indexing_error_code}</code>
            </p>
          )}
          <p className="mt-2 text-xs leading-5 text-slate-500">
            {result.indexing_status === 'indexed'
              ? 'The item is available to semantic retrieval and /query.'
              : 'The content is saved but is not searchable yet. There is no retry endpoint in the API; re-submitting creates a new item.'}
          </p>
        </div>
      )}
    </section>
  )
}
