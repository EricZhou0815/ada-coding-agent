"use client"

import React from "react"
import { JobSummary } from "@/types"
import { format } from "date-fns"
import { Clock, CheckCircle2, XCircle, Loader2, GitBranch, History } from "lucide-react"
import { cn } from "@/lib/utils"

interface JobSidebarProps {
    jobs: JobSummary[]
    activeJobId?: string
    onSelect: (jobId: string) => void
}

export const JobSidebar: React.FC<JobSidebarProps> = ({ jobs, activeJobId, onSelect }) => {
    const getStatusIcon = (status: JobSummary['status']) => {
        switch (status) {
            case 'SUCCESS': return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            case 'FAILED': return <XCircle className="w-3.5 h-3.5 text-rose-400" />
            case 'RUNNING': return <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
            default: return <Clock className="w-3.5 h-3.5 text-slate-500" />
        }
    }

    return (
        <div className="flex flex-col h-full bg-[#0d1117]/40 border-l border-slate-800 backdrop-blur-sm w-80">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <History className="w-4 h-4 text-slate-400" />
                    <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">
                        Job History
                    </h2>
                </div>
                <div className="px-1.5 py-0.5 rounded-full bg-slate-800 border border-slate-700">
                    <span className="text-[10px] font-mono text-slate-400">{jobs.length}</span>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar">
                {jobs.length === 0 ? (
                    <div className="p-8 text-center space-y-2 opacity-30">
                        <History className="w-8 h-8 mx-auto" />
                        <p className="text-xs italic">No jobs yet...</p>
                    </div>
                ) : (
                    <div className="divide-y divide-slate-800/50">
                        {jobs.map((job) => (
                            <button
                                key={job.job_id}
                                onClick={() => onSelect(job.job_id)}
                                className={cn(
                                    "w-full text-left p-4 transition-all duration-200 hover:bg-white/5 group relative",
                                    activeJobId === job.job_id ? "bg-cyan-500/5 ring-inset ring-1 ring-cyan-500/20" : ""
                                )}
                            >
                                {activeJobId === job.job_id && (
                                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-cyan-500" />
                                )}

                                <div className="space-y-2">
                                    <div className="flex items-start justify-between gap-2">
                                        <h3 className={cn(
                                            "text-sm font-semibold truncate",
                                            activeJobId === job.job_id ? "text-cyan-100" : "text-slate-300"
                                        )}>
                                            {job.story_title || 'Untitled Story'}
                                        </h3>
                                        <div className="shrink-0 mt-0.5">
                                            {getStatusIcon(job.status)}
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-3 text-[10px] text-slate-500 font-mono">
                                        <div className="flex items-center gap-1 shrink-0">
                                            <GitBranch className="w-3 h-3" />
                                            <span className="truncate max-w-[100px]">
                                                {job.repo_url.split('/').pop()}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-1 shrink-0">
                                            <Clock className="w-3 h-3" />
                                            <span>
                                                {format(new Date(job.created_at), "MMM d, HH:mm")}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
