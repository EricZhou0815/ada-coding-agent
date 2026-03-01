export interface LogEntry {
    timestamp: string;
    level?: 'info' | 'thought' | 'tool' | 'tool_result' | 'success' | 'error' | 'warning';
    prefix?: string;
    message: string;
    metadata?: any;
}

export interface Job {
    job_id: string;
    repo_url: string;
    status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'QUEUED';
    logs: LogEntry[];
    created_at: string;
}

export interface StoryPayload {
    title: string;
    story_id: string;
    description?: string;
    acceptance_criteria: string[];
}

export interface ExecutionRequest {
    repo_url: string;
    stories: StoryPayload[];
    base_branch?: string;
    use_mock?: boolean;
}
