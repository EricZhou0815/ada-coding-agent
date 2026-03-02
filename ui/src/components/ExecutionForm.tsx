"use client"

import React, { useState } from "react"
import { motion } from "framer-motion"
import { GitBranch, Plus, X, ArrowRight, Play, Loader2, Target, Type, AlignLeft } from "lucide-react"
import { StoryPayload, ExecutionRequest } from "@/types"
import { cn } from "@/lib/utils"

interface ExecutionFormProps {
    onSubmit: (data: ExecutionRequest) => Promise<void>
    isSubmitting: boolean
}

export const ExecutionForm: React.FC<ExecutionFormProps> = ({ onSubmit, isSubmitting }) => {
    const [repoUrl, setRepoUrl] = useState("")
    const [title, setTitle] = useState("")
    const [description, setDescription] = useState("")
    const [criteria, setCriteria] = useState<string[]>([""])
    const [useMock, setUseMock] = useState(false)

    const handleAddCriteria = () => setCriteria([...criteria, ""])
    const handleRemoveCriteria = (idx: number) => {
        const newCriteria = criteria.filter((_, i) => i !== idx)
        setCriteria(newCriteria.length ? newCriteria : [""])
    }

    const handleCriteriaChange = (idx: number, val: string) => {
        const newCriteria = [...criteria]
        newCriteria[idx] = val
        setCriteria(newCriteria)
    }

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        if (!repoUrl || !title) return

        const story: StoryPayload = {
            story_id: `STORY-${Math.floor(Math.random() * 1000)}`,
            title,
            description,
            acceptance_criteria: criteria.filter(c => c.trim()),
        }

        onSubmit({
            repo_url: repoUrl,
            stories: [story],
            use_mock: useMock,
        })
    }

    const inputClass = cn(
        "flex h-10 w-full rounded-md border border-slate-700 bg-slate-900/50 px-3 py-2 text-sm",
        "ring-offset-slate-950 file:border-0 file:bg-transparent file:text-sm file:font-medium",
        "placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-cyan-500/50 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        "transition-all duration-200"
    )

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-4">
                {/* Repo URL */}
                <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                        <GitBranch className="w-3.5 h-3.5" />
                        GitHub Repository URL
                    </label>
                    <input
                        type="url"
                        placeholder="https://github.com/username/repo"
                        className={inputClass}
                        value={repoUrl}
                        onChange={(e) => setRepoUrl(e.target.value)}
                        required
                        disabled={isSubmitting}
                    />
                </div>

                {/* Story Title */}
                <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                        <Target className="w-3.5 h-3.5" />
                        Story Title
                    </label>
                    <input
                        type="text"
                        placeholder="As a user, I want..."
                        className={inputClass}
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        required
                        disabled={isSubmitting}
                    />
                </div>

                {/* Story Description */}
                <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                        <AlignLeft className="w-3.5 h-3.5" />
                        Description (Optional)
                    </label>
                    <textarea
                        placeholder="Provide context for Ada..."
                        className={cn(inputClass, "h-24 resize-none")}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        disabled={isSubmitting}
                    />
                </div>

                {/* Acceptance Criteria */}
                <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                        <ArrowRight className="w-3.5 h-3.5" />
                        Acceptance Criteria
                    </label>
                    <div className="space-y-3">
                        {criteria.map((c, idx) => (
                            <div key={idx} className="flex gap-2 group">
                                <input
                                    type="text"
                                    placeholder={`Criterion #${idx + 1}`}
                                    className={inputClass}
                                    value={c}
                                    onChange={(e) => handleCriteriaChange(idx, e.target.value)}
                                    disabled={isSubmitting}
                                />
                                <button
                                    type="button"
                                    onClick={() => handleRemoveCriteria(idx)}
                                    className="p-2.5 rounded-md hover:bg-rose-500/10 text-slate-500 hover:text-rose-400 transition-colors"
                                    disabled={isSubmitting}
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                        ))}
                        <button
                            type="button"
                            onClick={handleAddCriteria}
                            className="w-full py-2 flex items-center justify-center gap-2 text-xs font-medium border border-dashed border-slate-700 rounded-md text-slate-400 hover:text-slate-100 hover:border-slate-500 transition-all"
                            disabled={isSubmitting}
                        >
                            <Plus className="w-4 h-4" />
                            Add Criterion
                        </button>
                    </div>
                    {/* Mock Mode Toggle */}
                    <div className="flex items-center justify-between p-3 rounded-lg border border-slate-700 bg-slate-900/40 hover:bg-slate-900/60 transition-colors">
                        <div className="space-y-0.5">
                            <label className="text-xs font-semibold text-slate-200 flex items-center gap-2 uppercase tracking-wider">
                                <Loader2 className={cn("w-3.5 h-3.5", useMock && "animate-spin text-cyan-400")} />
                                Mock Mode (Demo)
                            </label>
                            <p className="text-[10px] text-slate-500">
                                Use pre-recorded reasoning without consuming LLM credits
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={() => setUseMock(!useMock)}
                            className={cn(
                                "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-2 focus:ring-offset-slate-950",
                                useMock ? "bg-cyan-600" : "bg-slate-700"
                            )}
                            disabled={isSubmitting}
                        >
                            <span
                                className={cn(
                                    "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out",
                                    useMock ? "translate-x-4" : "translate-x-0"
                                )}
                            />
                        </button>
                    </div>

                    <button
                        type="submit"
                        disabled={isSubmitting || !repoUrl || !title}
                        className={cn(
                            "w-full py-3 px-4 flex items-center justify-center gap-2 font-bold text-sm tracking-widest uppercase transition-all duration-300 rounded-lg group shadow-lg",
                            isSubmitting
                                ? "bg-slate-800 text-slate-400 cursor-not-allowed"
                                : "bg-cyan-600 hover:bg-cyan-500 text-white shadow-cyan-950/20 hover:shadow-cyan-500/10 active:scale-95"
                        )}
                    >
                        {isSubmitting ? (
                            <Loader2 className="w-5 h-5 animate-spin" />
                        ) : (
                            <>
                                <Play className="w-4 h-4 fill-current group-hover:scale-110 transition-transform" />
                                Dispatch Ada
                            </>
                        )}
                    </button>
                </div>
            </div>
        </form>
    )
}
