"use client"

import React, { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Brain, Cpu, MessageSquare, Shield, Zap, ExternalLink, XCircle } from "lucide-react"
import { ExecutionForm } from "@/components/ExecutionForm"
import { LogTerminal } from "@/components/LogTerminal"
import { StatusBadge } from "@/components/StatusBadge"
import { JobSidebar } from "@/components/JobSidebar"
import { Job, JobSummary, ExecutionRequest } from "@/types"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function Home() {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [activeJob, setActiveJob] = useState<Job | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchJobs = async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/jobs`)
      if (resp.ok) {
        const data = await resp.json()
        setJobs(data)
      }
    } catch (err) {
      console.error("Failed to fetch jobs:", err)
    }
  }

  useEffect(() => {
    fetchJobs()
  }, [])

  const fetchJobStatus = async (jobId: string) => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`)
      if (!resp.ok) throw new Error("Could not fetch job status")
      const data = await resp.json()
      setActiveJob(data)

      // Stop polling if finished
      if (['SUCCESS', 'FAILED'].includes(data.status)) {
        return false
      }
      return true
    } catch (err) {
      console.error(err)
      return false
    }
  }

  // 1. Poll for general Status (SUCCESS/FAILED)
  useEffect(() => {
    if (!activeJob || ['SUCCESS', 'FAILED'].includes(activeJob.status)) return

    const interval = setInterval(async () => {
      // Just fetch status to update Badge, not logs (SSE handles logs)
      const shouldContinue = await fetchJobStatus(activeJob.job_id)
      if (!shouldContinue) clearInterval(interval)
    }, 5000)

    return () => clearInterval(interval)
  }, [activeJob?.job_id])

  // 2. SSE for Live Logs
  useEffect(() => {
    if (!activeJob?.job_id || ['SUCCESS', 'FAILED'].includes(activeJob.status)) return

    const eventSource = new EventSource(`${API_BASE}/api/v1/jobs/${activeJob.job_id}/stream`)

    eventSource.onmessage = (event) => {
      const newLog = JSON.parse(event.data)
      setActiveJob(prev => {
        if (!prev) return null
        // Prevent duplicate logs if initial fetch already got some
        const exists = prev.logs.some(l => l.timestamp === newLog.timestamp && l.message === newLog.message)
        if (exists) return prev

        return {
          ...prev,
          logs: [...prev.logs, newLog]
        }
      })
    }

    eventSource.onerror = (err) => {
      console.error("SSE Error:", err)
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }, [activeJob?.job_id])

  const handleDispatch = async (payload: ExecutionRequest) => {
    setIsSubmitting(true)
    setError(null)

    try {
      const resp = await fetch(`${API_BASE}/api/v1/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })

      if (!resp.ok) throw new Error("API request failed. Is the backend running?")

      const results = await resp.json()
      if (results.length > 0) {
        // Refresh the jobs list to show the new submission
        await fetchJobs()
        // Select the first new job
        await fetchJobStatus(results[0].job_id)
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSelectJob = async (jobId: string) => {
    setError(null)
    setActiveJob(null) // Reset while loading
    await fetchJobStatus(jobId)
  }

  return (
    <main className="min-h-screen bg-[#020617] text-slate-100 font-sans selection:bg-cyan-500/30">
      {/* Background Decor */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-cyan-900/10 blur-[120px] rounded-full" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] bg-blue-900/10 blur-[100px] rounded-full" />
      </div>

      {/* Navbar */}
      <nav className="relative z-10 border-b border-slate-800/60 bg-slate-950/40 backdrop-blur-md px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="absolute inset-0 bg-cyan-500/20 blur-lg rounded-full animate-pulse" />
            <Brain className="w-8 h-8 text-cyan-400 relative z-10" />
          </div>
          <h1 className="text-xl font-bold tracking-tighter text-slate-50">
            ADA <span className="text-cyan-400 font-medium">CONSOLE</span>
          </h1>
        </div>
        <div className="flex items-center gap-6 text-xs text-slate-400 font-medium uppercase tracking-widest hidden md:flex">
          <a href="#" className="hover:text-cyan-400 transition-colors flex items-center gap-1.5"><Shield className="w-3.5 h-3.5" /> Security</a>
          <a href="#" className="hover:text-cyan-400 transition-colors flex items-center gap-1.5"><Cpu className="w-3.5 h-3.5" /> Agents</a>
          <a href="#" className="hover:text-cyan-400 transition-colors flex items-center gap-1.5"><Zap className="w-3.5 h-3.5" /> Engine</a>
        </div>
      </nav>

      <div className="relative z-10 flex flex-col lg:flex-row h-[calc(100vh-73px)] overflow-hidden">
        {/* Main Workspace Area */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-6 lg:p-12">
          <div className="max-w-6xl mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">

              {/* Left Column: Form */}
              <div className="lg:col-span-5 space-y-8">
                <header className="space-y-3">
                  <h2 className="text-3xl font-extrabold tracking-tight text-white leading-none">
                    Dispatch <span className="bg-gradient-to-r from-cyan-400 to-blue-400 text-transparent bg-clip-text">Autonomous</span> Engineer
                  </h2>
                  <p className="text-slate-400 leading-relaxed text-sm">
                    Point Ada at any GitHub repository and define project requirements.
                    She explores, implements, and validates autonomously.
                  </p>
                </header>

                <div className="bg-slate-900/30 border border-slate-800 rounded-2xl p-6 backdrop-blur-sm shadow-xl ring-1 ring-white/5">
                  <ExecutionForm onSubmit={handleDispatch} isSubmitting={isSubmitting} />

                  {error && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mt-6 p-4 bg-rose-500/10 border border-rose-500/20 rounded-lg text-rose-400 text-sm flex gap-3"
                    >
                      <XCircle className="w-5 h-5 shrink-0" />
                      {error}
                    </motion.div>
                  )}
                </div>
              </div>

              {/* Right Column: Stream & Status */}
              <div className="lg:col-span-7 space-y-8 h-full">
                <AnimatePresence mode="wait">
                  {activeJob ? (
                    <motion.div
                      key={activeJob.job_id}
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      className="space-y-6"
                    >
                      <div className="flex items-center justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-3">
                            <h3 className="text-lg font-bold text-slate-100 italic truncate max-w-xs">
                              {activeJob.story_title || `Job #${activeJob.job_id.slice(0, 8)}`}
                            </h3>
                            <StatusBadge status={activeJob.status} />
                          </div>
                          <p className="text-xs text-slate-500 flex items-center gap-1 font-mono uppercase truncate">
                            <ExternalLink className="w-3 h-3" />
                            {activeJob.repo_url}
                          </p>
                        </div>
                      </div>

                      <LogTerminal logs={activeJob.logs} />
                    </motion.div>
                  ) : (
                    <motion.div
                      key="empty-state"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="h-[600px] flex flex-col items-center justify-center space-y-6 text-center"
                    >
                      <div className="relative">
                        <div className="absolute inset-0 bg-cyan-500/10 blur-3xl rounded-full" />
                        <MessageSquare className="w-20 h-20 text-slate-800 relative z-10" />
                      </div>
                      <div className="space-y-2 max-w-sm">
                        <h3 className="text-xl font-bold text-slate-300">Select or Dispatch a Story</h3>
                        <p className="text-slate-500 text-sm">
                          Logs will stream here in real-time once the worker picks up your story.
                        </p>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </div>
        </div>

        {/* Right Sidebar: History */}
        <div className="hidden lg:block">
          <JobSidebar
            jobs={jobs}
            activeJobId={activeJob?.job_id}
            onSelect={handleSelectJob}
          />
        </div>
      </div>

      {/* Footer Info */}
      <footer className="mt-auto border-t border-slate-800/40 py-8 px-6 text-center text-[10px] text-slate-600 uppercase tracking-widest font-mono relative z-10">
        <div className="flex items-center justify-center gap-4">
          <span>&copy; 2025 ADA | ALL RIGHTS RESERVED</span>
        </div>
      </footer>
    </main>
  )
}
