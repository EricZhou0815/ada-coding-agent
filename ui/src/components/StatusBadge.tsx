"use client"

import React from "react"
import { motion } from "framer-motion"
import { CheckCircle2, XCircle, Loader2, Clock, Play } from "lucide-react"
import { cn } from "@/lib/utils"

interface StatusBadgeProps {
    status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'QUEUED'
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
    const configs = {
        PENDING: {
            label: "Pending",
            icon: Clock,
            className: "bg-slate-500/10 text-slate-400 border-slate-500/20",
        },
        QUEUED: {
            label: "Queued",
            icon: Play,
            className: "bg-blue-500/10 text-blue-400 border-blue-500/20",
        },
        RUNNING: {
            label: "Running",
            icon: Loader2,
            className: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20 animate-pulse",
        },
        SUCCESS: {
            label: "Success",
            icon: CheckCircle2,
            className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
        },
        FAILED: {
            label: "Failed",
            icon: XCircle,
            className: "bg-rose-500/10 text-rose-400 border-rose-500/20",
        },
    }

    const { label, icon: Icon, className } = configs[status] || configs.PENDING

    return (
        <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className={cn(
                "px-2.5 py-1 rounded-full border text-[10px] font-bold uppercase tracking-widest flex items-center gap-1.5",
                className
            )}
        >
            <Icon className={cn("w-3.5 h-3.5", status === "RUNNING" && "animate-spin")} />
            {label}
        </motion.div>
    )
}
