import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError, describeApiError, type QueryResponse } from '../services/api'
import { PanelRightIcon, SparkleIcon } from './icons'
import { Spinner } from './Spinner'

const QUESTION_MAX_LENGTH = 2000

function queryErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 503) {
    return 'The AI service is unavailable. Check that the backend has a Groq API key configured.'
  }
  if (error instanceof ApiError && error.status === 502) {
    return 'The language model provider could not complete the request. Please try again.'
  }
  return describeApiError(error, 'Your question could not be answered.')
}

interface QueryPanelProps {
  result: QueryResponse | null
  onResultChange: (result: QueryResponse | null) => void
  onQuestionAsked?: (question: string) => void
  onSubmittingChange?: (submitting: boolean) => void
  onViewSources?: () => void
}

export function QueryPanel({
  result,
  onResultChange,
  onQuestionAsked,
  onSubmittingChange,
  onViewSources,
}: QueryPanelProps) {
  const [question, setQuestion] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) {
      return
    }

    const trimmed = question.trim()
    if (!trimmed) {
      setError('Enter a question before asking.')
      onResultChange(null)
      onQuestionAsked?.('')
      return
    }

    setSubmitting(true)
    setError(null)
    onSubmittingChange?.(true)

    try {
      const answer = await api.queryKnowledge({ question: trimmed })
      onResultChange(answer)
      onQuestionAsked?.(trimmed)
    } catch (cause) {
      setError(queryErrorMessage(cause))
      onResultChange(null)
      onQuestionAsked?.('')
    } finally {
      setSubmitting(false)
      onSubmittingChange?.(false)
    }
  }

  return (
    <section className="surface p-5 sm:p-7">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-accent/25 bg-accent-wash text-accent">
          <SparkleIcon className="h-4.5 w-4.5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-ink">Ask your knowledge</h2>
          <p className="mt-1 text-sm leading-6 text-muted">
            Answers are grounded in indexed items and include citations back to your sources.
          </p>
        </div>
      </div>

      <form className="mt-6" onSubmit={handleSubmit} noValidate>
        <label className="block text-xs font-semibold tracking-wide text-muted uppercase" htmlFor="question">
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
          className="field mt-2 resize-y"
        />
        <div className="mt-2 flex items-center justify-between gap-3 text-xs text-faint">
          <span>Natural language questions work best.</span>
          <span className="tabular-nums">
            {question.length}/{QUESTION_MAX_LENGTH}
          </span>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-4 rounded-xl border border-bad/25 bg-bad/10 px-4 py-3 text-sm leading-6 text-bad"
          >
            {error}
          </div>
        )}

        <div className="mt-5 flex items-center gap-3">
          <button
            type="submit"
            disabled={submitting}
            aria-busy={submitting}
            className="btn btn-primary px-5 py-3"
          >
            {submitting ? <Spinner /> : <SparkleIcon className="h-4 w-4" />}
            {submitting ? 'Thinking…' : 'Ask MindVault'}
          </button>
          {submitting && <span className="text-xs text-faint">Searching your vault…</span>}
        </div>
      </form>

      {result && (
        <div className="mt-7 space-y-4" role="status">
          <article className="rounded-xl border border-accent/20 bg-accent-wash/40 p-4 sm:p-5">
            <div className="flex items-center gap-2">
              <SparkleIcon className="h-4 w-4 text-accent" />
              <p className="eyebrow text-accent">Answer</p>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-ink">{result.answer}</p>

            {result.sources.length > 0 && (
              <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-accent/15 pt-4">
                {result.sources.slice(0, 6).map((source) => (
                  <span
                    key={`${source.citation_id}-${source.item_id}`}
                    className="inline-flex max-w-[220px] items-center gap-1.5 rounded-md border border-line bg-panel px-2 py-1 text-[11px] text-muted"
                    title={source.title ?? `Item #${source.item_id}`}
                  >
                    <span className="font-semibold text-accent">{source.citation_id}</span>
                    <span className="truncate">{source.title || `Item #${source.item_id}`}</span>
                  </span>
                ))}
                {result.sources.length > 6 && (
                  <span className="text-[11px] text-faint">+{result.sources.length - 6} more</span>
                )}
                {onViewSources && (
                  <button
                    type="button"
                    onClick={onViewSources}
                    className="btn btn-ghost ml-auto gap-1.5 px-2 py-1 text-xs xl:hidden"
                  >
                    <PanelRightIcon className="h-3.5 w-3.5" />
                    Sources
                  </button>
                )}
              </div>
            )}
          </article>

          {result.sources.length === 0 && (
            <p className="rounded-xl border border-line bg-sunken px-4 py-4 text-sm leading-6 text-muted">
              No source citations were returned. This usually means no relevant indexed chunks were
              found.
            </p>
          )}
        </div>
      )}
    </section>
  )
}
