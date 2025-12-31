export type ApiIssue = {
  issue_number: number;
  title: string;
  created_at: string;
  status: string;
  assignees: string[];
  linked_pull_requests: Array<Record<string, unknown>>;
  pr_last_checked_at: string | null;
  pr_completion: string | null;
};

export type MonitorJob = {
  job_id: string;
  issue_number: number;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  created_at: string;
  updated_at: string;
  completion: string | null;
  pull_request_numbers: number[];
  error: string | null;
};

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${text}`);
  }
  return (await resp.json()) as T;
}

export async function listIssues(): Promise<ApiIssue[]> {
  return http<ApiIssue[]>('/api/v1/issues');
}

export async function getIssue(issueNumber: number): Promise<ApiIssue> {
  return http<ApiIssue>(`/api/v1/issues/${issueNumber}`);
}

export async function refreshPRs(issueNumber: number): Promise<ApiIssue> {
  return http<ApiIssue>(`/api/v1/issues/${issueNumber}/refresh-prs`, {
    method: 'POST',
  });
}

export async function startMonitorPRs(issueNumber: number): Promise<MonitorJob> {
  return http<MonitorJob>(`/api/v1/issues/${issueNumber}/monitor-prs`, {
    method: 'POST',
    body: JSON.stringify({
      poll_seconds: 10,
      timeout_seconds: 3600,
      require_pr: true,
    }),
  });
}

export async function getJob(jobId: string): Promise<MonitorJob> {
  return http<MonitorJob>(`/api/v1/jobs/${jobId}`);
}
