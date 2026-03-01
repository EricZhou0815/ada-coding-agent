"use client"

import React, { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Brain, Cpu, MessageSquare, Shield, Zap, ExternalLink, XCircle } from "lucide-react"
import { ExecutionForm } from "@/components/ExecutionForm"
import { LogTerminal } from "@/components/LogTerminal"
import { StatusBadge } from "@/components/StatusBadge"
import { Job, ExecutionRequest } from "@/types"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function Home() {
  const [activeJob, setActiveJob] = useState<Job | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  useEffect(() => {
    if (!activeJob || ['SUCCESS', 'FAILED'].includes(activeJob.status)) return

    const interval = setInterval(async () => {
      const shouldContinue = await fetchJobStatus(activeJob.job_id)
      if (!shouldContinue) clearInterval(interval)
    }, 2000)

    return () => clearInterval(interval)
  }, [activeJob?.job_id])

  const handleDispatch = async (payload: ExecutionRequest) => {
    setIsSubmitting(true)
    setError(null)
    setActiveJob(null)

    try {
      const resp = await fetch(`${API_BASE}/api/v1/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })

      if (!resp.ok) throw new Error("API request failed. Is the backend running?")

      const jobs = await resp.json()
      if (jobs.length > 0) {
        // Initial setup for polling
        await fetchJobStatus(jobs[0].job_id)
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setIsSubmitting(false)
    }
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

      <div className="relative z-10 container max-w-7xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">

          {/* Left Column: Form */}
          <div className="lg:col-span-5 space-y-8">
            <header className="space-y-3">
              <h2 className="text-3xl font-extrabold tracking-tight text-white leading-none">
                Dispatch <span className="bg-gradient-to-r from-cyan-400 to-blue-400 text-transparent bg-clip-text">Autonomous</span> Engineer
              </h2>
              <p className="text-slate-400 leading-relaxed text-sm">
                Point Ada at any GitHub repository and define project requirements.
                She explores, implementation, and validates autonomously.
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
          <div className="lg:col-span-1 space-y-8 hidden lg:block" />

          <div className="lg:col-span-6 space-y-8 h-full">
            <AnimatePresence mode="wait">
              {activeJob ? (
                <motion.div
                  key="active-job"
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className="space-y-6"
                >
                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center gap-3">
                        <h3 className="text-lg font-bold text-slate-100 italic">Job #{activeJob.job_id.slice(0, 8)}</h3>
                        <StatusBadge status={activeJob.status} />
                      </div>
                      <p className="text-xs text-slate-500 flex items-center gap-1 font-mono uppercase">
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
                    <h3 className="text-xl font-bold text-slate-300">Awaiting Submissions</h3>
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

      {/* Footer Info */}
      <footer className="mt-auto border-t border-slate-800/40 py-8 px-6 text-center text-[10px] text-slate-600 uppercase tracking-widest font-mono relative z-10">
        <div className="flex items-center justify-center gap-4">
          <span>&copy; 2025 ADA | ALL RIGHTS RESERVED</span>
        </div>
      </footer>
    </main>
  )
}
