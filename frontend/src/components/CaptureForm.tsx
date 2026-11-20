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
import { CheckIcon, GlobeIcon, NoteIcon } from './icons'
import { Spinner } from './Spinner'
import { StatusBadge } from './StatusBadge'

const INPUT_CLASS = 'field'
const LABEL_CLASS = 'block text-xs font-semibold tracking-wide text-muted uppercase'

const INDEXING_TONES: Record<IndexingStatus, 'emerald' | 'rose' | 'amber'> = {
  indexed: 'emerald',
  failed: 'rose',
  unavailable: 'amber',
}

function indexingLabel(result: IngestResponse): string {
  if (result.indexing_status === 'indexed') {
    const count = result.indexed_chunk_count
    return count === null
      ? 'Searchable now'
      : `Searchable now · ${count} chunk${count === 1 ? '' : 's'}`
  }
  if (result.indexing_status === 'failed') {
    return 'Saved but not searchable'
  }
  return 'Saved; indexing unavailable'
}

interface CaptureFormProps {
  onIngested: (result: IngestResponse) => void
  initialMode?: SourceType
}

export function CaptureForm({ onIngested, initialMode = 'NOTE' }: CaptureFormProps) {
  const [mode, setMode] = useState<SourceType>(initialMode)
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
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-ink">Capture knowledge</h2>
          <p className="mt-1 text-xs leading-5 text-muted">
            Save a note or link. Indexing starts automatically after the item is stored.
          </p>
        </div>
        <div
          className="inline-flex rounded-lg border border-line bg-sunken p-1"
          role="group"
          aria-label="Source type"
        >
          {(['NOTE', 'URL'] as const).map((option) => {
            const active = mode === option
            return (
              <button
                key={option}
                type="button"
                aria-pressed={active}
                onClick={() => changeMode(option)}
                className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  active ? 'bg-accent-wash text-accent' : 'text-faint hover:text-ink'
                }`}
              >
                {option === 'NOTE' ? (
                  <NoteIcon className="h-3.5 w-3.5" />
                ) : (
                  <GlobeIcon className="h-3.5 w-3.5" />
                )}
                {option === 'NOTE' ? 'Text note' : 'URL'}
              </button>
            )
          })}
        </div>
      </div>

      <form className="mt-6 space-y-5" onSubmit={handleSubmit} noValidate>
        <div>
          <label className={LABEL_CLASS} htmlFor="capture-title">
            Title <span className="font-normal normal-case text-faint">(optional)</span>
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
            <p className="mt-2 text-xs leading-5 text-faint">
              MindVault fetches the page and extracts readable text. Pasted content is ignored.
            </p>
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="rounded-xl border border-bad/25 bg-bad/10 px-4 py-3 text-sm leading-6 text-bad"
          >
            {error}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={submitting}
            aria-busy={submitting}
            className="btn btn-primary px-5 py-3"
          >
            {submitting ? <Spinner /> : <CheckIcon className="h-4 w-4" />}
            {submitting ? 'Saving…' : mode === 'NOTE' ? 'Save note' : 'Save URL'}
          </button>
          {submitting && <span className="text-xs text-faint">Please wait…</span>}
        </div>
      </form>

      {result && (
        <div role="status" className="mt-6 rounded-xl border border-good/20 bg-good/[0.06] p-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone="emerald" dot>
              Item saved
            </StatusBadge>
            <StatusBadge tone={INDEXING_TONES[result.indexing_status]}>
              {indexingLabel(result)}
            </StatusBadge>
          </div>
          <p className="mt-3 text-sm text-muted">
            <span className="font-medium text-ink">
              {result.title || (result.source_type === 'NOTE' ? 'Untitled note' : 'Untitled link')}
            </span>{' '}
            was stored as item #{result.id}.
          </p>
          {result.indexing_status !== 'indexed' && result.indexing_error_code && (
            <p className="mt-2 text-xs text-faint">
              Indexing error code: <code className="text-muted">{result.indexing_error_code}</code>
            </p>
          )}
          <p className="mt-2 text-xs leading-5 text-faint">
            {result.indexing_status === 'indexed'
              ? 'The item is available to semantic retrieval and /query.'
              : 'The content is saved but is not searchable yet. There is no retry endpoint in the API; re-submitting creates a new item.'}
          </p>
        </div>
      )}
    </div>
  )
}
