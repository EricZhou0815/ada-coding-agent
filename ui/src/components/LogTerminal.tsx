"use client"

import React, { useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
    Terminal,
    CheckCircle2,
    XCircle,
    Info,
    Brain,
    ChevronRight,
    Settings,
    GitBranch,
    Cpu,
    AlertTriangle,
    Eye
} from "lucide-react"
import { format } from "date-fns"
import { LogEntry } from "@/types"
import { cn } from "@/lib/utils"

interface LogTerminalProps {
    logs: LogEntry[]
}

const LogLine: React.FC<{ log: LogEntry; isLast: boolean }> = ({ log, isLast }) => {
    const isNow = log.timestamp === "now" || !log.timestamp
    const timeStr = isNow ? "Queue" : format(new Date(log.timestamp), "HH:mm:ss")

    // Determine Icon and Color based on Level and Prefix
    const getLevelData = () => {
        const level = log.level || 'info'
        const prefix = (log.prefix || '').toLowerCase()

        if (level === 'thought') return { icon: <Brain className="w-3.5 h-3.5" />, color: "text-purple-400", bg: "bg-purple-500/5", border: "border-purple-500/20" }
        if (level === 'tool') return { icon: <Settings className="w-3.5 h-3.5" />, color: "text-amber-400", bg: "bg-amber-500/5", border: "border-amber-500/20" }
        if (level === 'tool_result') {
            const success = log.metadata?.success
            return {
                icon: success ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />,
                color: success ? "text-emerald-400" : "text-rose-400",
                bg: success ? "bg-emerald-500/5" : "bg-rose-500/5",
                border: success ? "border-emerald-500/20" : "border-rose-500/20"
            }
        }
        if (level === 'error') return { icon: <AlertTriangle className="w-3.5 h-3.5" />, color: "text-rose-400", bg: "bg-rose-500/10", border: "border-rose-500/30" }
        if (level === 'warning') return { icon: <AlertTriangle className="w-3.5 h-3.5" />, color: "text-amber-400", bg: "bg-amber-500/5", border: "border-amber-500/20" }
        if (level === 'success') return { icon: <CheckCircle2 className="w-3.5 h-3.5" />, color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/30" }

        // Fallback by Prefix
        if (prefix.includes('git')) return { icon: <GitBranch className="w-3.5 h-3.5" />, color: "text-blue-400" }
        if (prefix.includes('coder') || prefix.includes('agent')) return { icon: <Cpu className="w-3.5 h-3.5" />, color: "text-cyan-400" }
        if (prefix.includes('sandbox')) return { icon: <Eye className="w-3.5 h-3.5" />, color: "text-indigo-400" }

        return { icon: <Info className="w-3.5 h-3.5" />, color: "text-slate-400" }
    }

    const { icon, color, bg, border } = getLevelData()

    if (log.level === 'thought') {
        return (
            <motion.div
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className={cn("my-4 p-4 rounded-lg border", bg, border)}
            >
                <div className="flex items-center gap-2 mb-2">
                    <Brain className="w-4 h-4 text-purple-400" />
                    <span className="text-[10px] font-bold uppercase tracking-widest text-purple-400/80">
                        {log.prefix || 'Coder'}'s Internal Monologue
                    </span>
                    <div className="flex-1 border-t border-purple-500/10 ml-2" />
                    <span className="text-[10px] text-slate-600 font-mono">{timeStr}</span>
                </div>
                <p className="text-sm text-slate-300 font-serif leading-relaxed italic">
                    "{log.message}"
                </p>
            </motion.div>
        )
    }

    if (log.level === 'tool') {
        return (
            <motion.div
                initial={{ opacity: 0, x: -5 }}
                animate={{ opacity: 1, x: 0 }}
                className={cn("flex items-center gap-3 py-2 px-3 rounded-md border text-sm font-mono", bg, border)}
            >
                <Settings className="w-4 h-4 text-amber-500 shrink-0" />
                <div className="flex-1 flex gap-2 overflow-hidden">
                    <span className="text-amber-500/50 select-none">$</span>
                    <span className="text-amber-300 font-bold truncate">calling {log.message}</span>
                    <span className="text-slate-500 opacity-60 truncate">({log.metadata?.args})</span>
                </div>
                <span className="text-[10px] text-slate-600 shrink-0">{timeStr}</span>
            </motion.div>
        )
    }

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={cn(
                "flex items-start gap-4 py-1.5 px-3 rounded hover.bg-white/5 transition-colors group",
                isLast && "bg-white/5 border-l-2 border-cyan-500"
            )}
        >
            <div className="flex-1 flex items-start gap-3">
                <span className="text-[10px] font-mono text-slate-600 mt-1 shrink-0 w-12 select-none">
                    {timeStr}
                </span>
                <span className={cn("mt-1 shrink-0", color)}>{icon}</span>
                <div className="flex-1 min-w-0">
                    {log.prefix && (
                        <span className={cn("text-[10px] font-bold uppercase tracking-tighter mr-2 select-none opacity-60", color)}>
                            [{log.prefix}]
                        </span>
                    )}
                    <span className={cn(
                        "text-sm font-mono break-words leading-relaxed",
                        log.level === 'error' ? "text-rose-300" : "text-slate-300",
                        log.level === 'tool_result' && (log.metadata?.success ? "text-emerald-300" : "text-rose-300")
                    )}>
                        {log.message}
                        {log.level === 'tool_result' && log.metadata?.success && (
                            <span className="text-[10px] ml-2 text-slate-600">
                                ({log.metadata.output_len} bytes)
                            </span>
                        )}
                    </span>
                </div>
            </div>
        </motion.div>
    )
}

export const LogTerminal: React.FC<LogTerminalProps> = ({ logs }) => {
    const scrollRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTo({
                top: scrollRef.current.scrollHeight,
                behavior: "smooth",
            })
        }
    }, [logs])

    return (
        <div className="flex flex-col h-[600px] bg-[#0d1117]/80 backdrop-blur-xl border border-slate-800 rounded-xl overflow-hidden shadow-2xl ring-1 ring-white/5">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 bg-slate-900/50 border-b border-white/5">
                <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                        <div className="w-2.5 h-2.5 rounded-full bg-rose-500" />
                        <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                        <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                        <Terminal className="w-3.5 h-3.5 text-slate-500" />
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                            Ada Runtime Audit
                        </span>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                        <span className="text-[9px] font-bold text-emerald-500/80 uppercase">Live Stream</span>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto p-6 space-y-1.5 scrollbar-none custom-scrollbar"
            >
                <AnimatePresence initial={false}>
                    {logs.map((log, idx) => (
                        <LogLine key={`${log.timestamp}-${idx}`} log={log} isLast={idx === logs.length - 1} />
                    ))}
                </AnimatePresence>
                {logs.length === 0 && (
                    <div className="h-full flex flex-col items-center justify-center text-slate-500 italic space-y-4 opacity-30">
                        <Terminal className="w-12 h-12" />
                        <div className="text-center">
                            <p className="text-sm font-bold uppercase tracking-tighter">Initializing Auditor</p>
                            <p className="text-xs">Awaiting data stream from Ada worker...</p>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
