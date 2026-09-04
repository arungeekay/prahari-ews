import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Spinner } from './ui'

/**
 * Document modal with a subtle progressive "typing" reveal - the signature
 * demo moment (brief §"Document generation"). Header reads "Draft - for
 * officer review". The officer-review disclaimer itself comes from the API text.
 * `footnote` (e.g. the LLM provider that drafted it) renders small under the document.
 * `onFile` enables the maker-checker "Approve and file" action; `filedBy` shows the outcome.
 */
export function DocumentModal({
  open, title, subtitle, text, loading, footnote, onClose,
  onFile, filing = false, filedBy = null, fileError = null,
}: {
  open: boolean
  title: string
  subtitle?: string
  text: string | null
  loading: boolean
  footnote?: string
  onClose: () => void
  onFile?: () => void
  filing?: boolean
  filedBy?: string | null
  fileError?: string | null
}) {
  const [shown, setShown] = useState(0)

  useEffect(() => {
    setShown(0)
  }, [text])

  useEffect(() => {
    if (!text) return
    let raf = 0
    const total = text.length
    const start = performance.now()
    const perChar = Math.max(6, Math.min(14, 4200 / total)) // faster for long docs
    const step = (t: number) => {
      const n = Math.min(total, Math.floor((t - start) / perChar))
      setShown(n)
      if (n < total) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [text])

  const typing = text != null && shown < text.length
  const ready = text != null && !loading
  const canFile = onFile != null && ready && !filedBy

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-6"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        >
          <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={onClose} />
          <motion.div
            className="relative bg-card rounded-2xl shadow-card border border-line w-full max-w-2xl max-h-[85vh] flex flex-col"
            initial={{ y: 24, scale: 0.98, opacity: 0 }}
            animate={{ y: 0, scale: 1, opacity: 1 }}
            exit={{ y: 12, scale: 0.98, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 320, damping: 28 }}
          >
            <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-line">
              <div>
                <div className="inline-flex items-center gap-2 text-[11px] font-semibold text-teal uppercase tracking-wide">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal" />
                  {filedBy ? 'Filed to the credit file' : 'Draft - for officer review'}
                </div>
                <h3 className="text-ink font-semibold text-lg mt-1">{title}</h3>
                {subtitle && <p className="text-muted text-xs mt-0.5">{subtitle}</p>}
              </div>
              <button
                onClick={onClose}
                className="text-muted hover:text-ink transition-colors rounded-lg px-2 py-1 -mr-2"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <div className="px-6 py-5 overflow-y-auto">
              {loading || text == null ? (
                <Spinner label="PRAHARI is drafting the document…" />
              ) : (
                <>
                  <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-slate-700">
                    {text.slice(0, shown)}
                    {typing && <span className="caret-blink text-brand">▍</span>}
                  </pre>
                  {footnote && !typing && (
                    <p className="text-[11px] text-muted mt-4 pt-3 border-t border-line">{footnote}</p>
                  )}
                </>
              )}
            </div>

            <div className="px-6 py-3 border-t border-line flex items-center justify-between gap-3 bg-paper/60 rounded-b-2xl">
              <div className="text-xs min-w-0">
                {filedBy ? (
                  <span className="inline-flex items-center gap-1.5 font-semibold text-rag-green">
                    <span className="w-1.5 h-1.5 rounded-full bg-rag-green" /> Filed by {filedBy}
                  </span>
                ) : fileError ? (
                  <span className="text-rag-red">{fileError}</span>
                ) : canFile ? (
                  <span className="text-muted">Maker-checker: filing records the named officer's approval in the review log.</span>
                ) : null}
              </div>
              <div className="flex gap-2 shrink-0">
                {canFile && (
                  <button
                    onClick={onFile}
                    disabled={filing}
                    className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-rag-green hover:bg-[#25804A] transition-colors disabled:opacity-50"
                  >
                    {filing ? 'Filing…' : 'Approve and file'}
                  </button>
                )}
                <button
                  onClick={onClose}
                  className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-brand hover:bg-ink transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
