"use client"

import React, { useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Terminal, CheckCircle2, XCircle, Info, Brain, ChevronRight } from "lucide-react"
import { format } from "date-fns"
import { LogEntry } from "@/types"

interface LogTerminalProps {
    logs: LogEntry[]
}

const LogLine: React.FC<{ log: LogEntry; isLast: boolean }> = ({ log, isLast }) => {
    const getIcon = (message: string) => {
        const m = message.toLowerCase()
        if (m.includes("successfully") || m.includes("completed")) return <CheckCircle2 className="w-4 h-4 text-emerald-400" />
        if (m.includes("error") || m.includes("failed")) return <XCircle className="w-4 h-4 text-rose-400" />
        if (m.includes("thought") || m.includes("planning")) return <Brain className="w-4 h-4 text-cyan-400" />
        if (m.includes("executing") || m.includes("running")) return <ChevronRight className="w-4 h-4 text-blue-400 animate-pulse" />
        return <Info className="w-4 h-4 text-slate-400" />
    }

    return (
        <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className={`flex items-start gap-3 py-1 font-mono text-sm leading-relaxed ${isLast ? "text-cyan-50 bg-cyan-950/20" : "text-slate-300"}`}
        >
            <span className="text-slate-500 shrink-0 select-none">
                {log.timestamp !== "now" ? format(new Date(log.timestamp), "HH:mm:ss") : "Queued"}
            </span>
            <span className="shrink-0 mt-0.5">{getIcon(log.message)}</span>
            <span className="break-words whitespace-pre-wrap">{log.message}</span>
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
        <div className="flex flex-col h-[500px] bg-[#0d1117] border border-slate-800 rounded-xl overflow-hidden shadow-2xl ring-1 ring-white/5">
            <div className="flex items-center justify-between px-4 py-2 bg-slate-900/50 border-b border-slate-800">
                <div className="flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-slate-400" />
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-widest px-1">
                        Execution Logs
                    </span>
                </div>
                <div className="flex gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-rose-500/20 border border-rose-500/30" />
                    <div className="w-2.5 h-2.5 rounded-full bg-amber-500/20 border border-amber-500/30" />
                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/20 border border-emerald-500/30" />
                </div>
            </div>

            <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto p-4 space-y-1 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent custom-scrollbar"
            >
                <AnimatePresence initial={false}>
                    {logs.map((log, idx) => (
                        <LogLine key={`${log.timestamp}-${idx}`} log={log} isLast={idx === logs.length - 1} />
                    ))}
                </AnimatePresence>
                {logs.length === 0 && (
                    <div className="h-full flex flex-col items-center justify-center text-slate-500 italic space-y-2 opacity-50">
                        <Terminal className="w-8 h-8" />
                        <p>Awaiting execution stream...</p>
                    </div>
                )}
            </div>
        </div>
    )
}
