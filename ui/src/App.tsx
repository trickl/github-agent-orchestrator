import React, { useEffect, useMemo, useState } from 'react';
import type { ApiIssue, MonitorJob } from './api';
import { getIssue, getJob, listIssues, refreshPRs, startMonitorPRs } from './api';

export function App(): React.JSX.Element {
  const [issues, setIssues] = useState<ApiIssue[]>([]);
  const [selectedIssueNumber, setSelectedIssueNumber] = useState<number | null>(null);
  const [selectedIssue, setSelectedIssue] = useState<ApiIssue | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [job, setJob] = useState<MonitorJob | null>(null);

  const selected = useMemo(
    () => issues.find((i) => i.issue_number === selectedIssueNumber) ?? null,
    [issues, selectedIssueNumber]
  );

  async function loadIssues(): Promise<void> {
    setError(null);
    setLoading(true);
    try {
      const data = await listIssues();
      setIssues(data);
      if (selectedIssueNumber === null && data.length > 0) {
        setSelectedIssueNumber(data[0].issue_number);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadSelectedIssue(issueNumber: number): Promise<void> {
    setError(null);
    setLoading(true);
    try {
      const data = await getIssue(issueNumber);
      setSelectedIssue(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadIssues();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedIssueNumber === null) return;
    void loadSelectedIssue(selectedIssueNumber);
  }, [selectedIssueNumber]);

  useEffect(() => {
    if (!job) return;
    if (job.status === 'succeeded' || job.status === 'failed') return;

    const timer = window.setInterval(async () => {
      try {
        const updated = await getJob(job.job_id);
        setJob(updated);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }, 2000);

    return () => window.clearInterval(timer);
  }, [job]);

  return (
    <div className="container">
      <header className="header">
        <div>
          <h1>GitHub Agent Orchestrator</h1>
          <p className="subtitle">Monitor issues and linked PRs (local state + REST)</p>
        </div>
        <button className="button" onClick={() => void loadIssues()} disabled={loading}>
          Refresh issues
        </button>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <div className="grid">
        <section className="panel">
          <h2>Issues</h2>
          {loading && issues.length === 0 ? <div>Loading…</div> : null}
          <ul className="list">
            {issues.map((issue) => (
              <li key={issue.issue_number}>
                <button
                  className={
                    issue.issue_number === selectedIssueNumber ? 'listItem active' : 'listItem'
                  }
                  onClick={() => setSelectedIssueNumber(issue.issue_number)}
                >
                  <div className="listTitle">#{issue.issue_number} {issue.title}</div>
                  <div className="meta">status={issue.status} assignees={issue.assignees.join(', ') || '—'}</div>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>Details</h2>
          {selected ? (
            <div className="details">
              <div className="row"><strong>Issue:</strong> #{selected.issue_number} {selected.title}</div>
              <div className="row"><strong>Status:</strong> {selected.status}</div>
              <div className="row"><strong>Assignees:</strong> {selected.assignees.join(', ') || '—'}</div>
              <div className="row"><strong>PR completion:</strong> {selectedIssue?.pr_completion ?? '—'}</div>
              <div className="row"><strong>Last checked:</strong> {selectedIssue?.pr_last_checked_at ?? '—'}</div>

              <div className="actions">
                <button
                  className="button"
                  onClick={async () => {
                    if (!selectedIssueNumber) return;
                    const updated = await refreshPRs(selectedIssueNumber);
                    setSelectedIssue(updated);
                    // refresh list too
                    await loadIssues();
                  }}
                  disabled={loading}
                >
                  Refresh linked PRs
                </button>
                <button
                  className="button primary"
                  onClick={async () => {
                    if (!selectedIssueNumber) return;
                    setError(null);
                    try {
                      const j = await startMonitorPRs(selectedIssueNumber);
                      setJob(j);
                    } catch (e) {
                      setError(e instanceof Error ? e.message : String(e));
                    }
                  }}
                  disabled={loading}
                >
                  Start monitor job
                </button>
              </div>

              <h3>Linked PRs (from local state)</h3>
              {selectedIssue?.linked_pull_requests?.length ? (
                <ul className="prList">
                  {selectedIssue.linked_pull_requests.map((pr, idx) => (
                    <li key={idx} className="prItem">
                      <div>
                        <strong>#{String(pr.number ?? '—')}</strong> {String(pr.title ?? '')}
                      </div>
                      <div className="meta">
                        state={String(pr.state ?? '—')} merged={String(pr.merged ?? '—')}
                      </div>
                      {pr.url ? (
                        <a href={String(pr.url)} target="_blank" rel="noreferrer">
                          Open on GitHub
                        </a>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="meta">No linked PRs persisted yet.</div>
              )}

              <h3>Monitor job</h3>
              {job ? (
                <div className="job">
                  <div className="row"><strong>ID:</strong> {job.job_id}</div>
                  <div className="row"><strong>Status:</strong> {job.status}</div>
                  <div className="row"><strong>Completion:</strong> {job.completion ?? '—'}</div>
                  <div className="row"><strong>PRs:</strong> {job.pull_request_numbers.join(', ') || '—'}</div>
                  {job.error ? <div className="error">{job.error}</div> : null}
                </div>
              ) : (
                <div className="meta">No job running.</div>
              )}
            </div>
          ) : (
            <div className="meta">Select an issue.</div>
          )}
        </section>
      </div>

      <footer className="footer">
        Backend: <code>/api/v1</code> (see <code>/docs</code> for OpenAPI)
      </footer>
    </div>
  );
}
