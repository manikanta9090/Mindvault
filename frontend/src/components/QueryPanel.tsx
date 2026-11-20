import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  api,
  ApiError,
  describeApiError,
  type QueryResponse,
  type SourceType,
} from '../services/api'
import { StatusBadge } from './StatusBadge'

const QUESTION_MAX_LENGTH = 2000

const SOURCE_TONES: Record<SourceType, 'emerald' | 'indigo'> = {
  NOTE: 'indigo',
  URL: 'emerald',
}

function queryErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 503) {
    return 'The AI service is unavailable. Check that the backend has a Groq API key configured.'
  }
  if (error instanceof ApiError && error.status === 502) {
    return 'The language model provider could not complete the request. Please try again.'
  }
  return describeApiError(error, 'Your question could not be answered.')
}

export function QueryPanel() {
  const [question, setQuestion] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<QueryResponse | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) {
      return
    }

    const trimmed = question.trim()
    if (!trimmed) {
      setError('Enter a question before asking.')
      setResult(null)
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const answer = await api.queryKnowledge({ question: trimmed })
      setResult(answer)
    } catch (cause) {
      setError(queryErrorMessage(cause))
      setResult(null)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur-sm sm:p-8">
      <div>
        <h2 className="text-xl font-semibold text-white">Ask your knowledge</h2>
        <p className="mt-1 text-sm text-slate-400">
          Answers are grounded in indexed items and include source citations.
        </p>
      </div>

      <form className="mt-6" onSubmit={handleSubmit} noValidate>
        <label className="block text-xs font-semibold tracking-wide text-slate-300 uppercase" htmlFor="question">
          Question
        </label>
        <textarea
          id="question"
          value={question}
          maxLength={QUESTION_MAX_LENGTH}
          rows={4}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="What did I save about Node.js?"
          disabled={submitting}
          className="mt-2 w-full resize-y rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 transition focus:border-indigo-400/60 focus:outline-none focus:ring-2 focus:ring-indigo-400/20"
        />
        <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
          <span>Natural language questions work best.</span>
          <span>
            {question.length}/{QUESTION_MAX_LENGTH}
          </span>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-4 rounded-xl border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm leading-6 text-rose-100"
          >
            {error}
          </div>
        )}

        <div className="mt-5 flex items-center gap-3">
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
            {submitting ? 'Thinking…' : 'Ask MindVault'}
          </button>
          {submitting && <span className="text-xs text-slate-500">Searching your vault…</span>}
        </div>
      </form>

      {result && (
        <div className="mt-7 space-y-5" role="status">
          <article className="rounded-2xl border border-indigo-400/20 bg-indigo-400/5 p-5">
            <p className="text-xs font-semibold tracking-[0.16em] text-indigo-200 uppercase">Answer</p>
            <p className="mt-3 text-sm leading-7 text-slate-100 whitespace-pre-wrap">{result.answer}</p>
          </article>

          <div>
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-white">Sources</h3>
              <span className="text-xs text-slate-500">{result.sources.length} returned</span>
            </div>

            {result.sources.length === 0 ? (
              <p className="mt-3 rounded-xl border border-white/10 bg-slate-950/40 px-4 py-4 text-sm leading-6 text-slate-400">
                No source citations were returned. This usually means no relevant indexed chunks
                were found.
              </p>
            ) : (
              <ol className="mt-3 grid gap-3">
                {result.sources.map((source) => (
                  <li
                    key={`${source.citation_id}-${source.item_id}`}
                    className="rounded-xl border border-white/10 bg-slate-950/40 p-4"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone="indigo">{source.citation_id}</StatusBadge>
                      <StatusBadge tone={SOURCE_TONES[source.source_type]}>{source.source_type}</StatusBadge>
                      <span className="truncate text-sm font-medium text-slate-100" title={source.title ?? undefined}>
                        {source.title || `Item #${source.item_id}`}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-400">{source.snippet}</p>
                    {source.source_url && (
                      <a
                        href={source.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-3 block truncate text-xs text-indigo-300 underline-offset-4 hover:underline"
                      >
                        {source.source_url}
                      </a>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
