import React from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Step,
  StepContent,
  StepLabel,
  Stepper,
  Typography,
} from '@mui/material';
import type { StepIconProps } from '@mui/material/StepIcon';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { Link as RouterLink } from 'react-router-dom';

import { apiFetch } from '../lib/apiClient';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { Timestamp } from '../components/Timestamp';

type LoopCounts = {
  pending: number;
  processed: number;
  complete: number;
  openIssues: number | null;
  openPullRequests: number | null;
  openGapAnalysisIssues: number | null;
  openGapAnalysisIssuesWithPr?: number | null;
  openGapAnalysisIssuesReadyForReview?: number | null;
  unpromotedPending: number | null;

  pendingDevelopment: number | null;
  pendingCapabilityUpdates: number | null;
  pendingExcluded: number | null;

  pendingDevelopmentWithoutPr: number | null;
  pendingDevelopmentWithPr: number | null;
  pendingDevelopmentReadyForReview: number | null;

  pendingCapabilityUpdatesWithoutPr: number | null;
  pendingCapabilityUpdatesWithPr: number | null;
  pendingCapabilityUpdatesReadyForReview: number | null;
};

type RunningJob = {
  jobId: string;
  issueNumber: number | null;
  status: 'running';
  updatedAt: string;
};

type LoopStatus = {
  nowIso: string;
  stage: '1a' | '1b' | '1c' | '2a' | '2b' | '2c' | '3a' | '3b' | '3c';
  stageLabel: string;
  activeStep: number;
  counts: LoopCounts;
  runningJob: RunningJob | null;
  lastAction: null | { tsIso: string; summary: string; kind: string };
  focus?: {
    kind: 'development' | 'capability' | 'gap';
    title?: string;
    sourceTitle?: string;
    issueNumber?: number | null;
    issueUrl?: string | null;
    pullNumber?: number | null;
    pullUrl?: string | null;
    sourcePullNumber?: number | null;
    sourcePullUrl?: string | null;
    queuePath?: string | null;
    queueId?: string | null;
  } | null;
  repo?: string | null;
  ref?: string | null;
  stageReason?: string;
  warnings?: string[];
};

type PromoteResult = {
  repo: string;
  branch: string;
  queuePath: string;
  processedPath: string;
  issueNumber: number;
  issueUrl: string | null;
  created: boolean;
  assigned: string[];
  summary: string;
};

type MergeResult = {
  repo: string;
  branch: string;
  merged: boolean;
  mergeCommitSha: string | null;
  queuePath: string | null;
  completePath: string | null;
  developmentIssueNumber: number | null;
  pullNumber: number;
  approved: boolean;
  approvalError: string | null;
  headBranchDeleted: boolean;
  capabilityIssueNumber: number;
  capabilityIssueCreated: boolean;
  capabilityIssueUrl: string | null;
  capabilityIssueAssigned: string[];
  capabilityIssueClosed?: boolean;
  summary: string;
};

const steps: Array<{
  key: string;
  title: string;
  subtitle: string;
  details: React.ReactNode;
}> = [
  {
    key: '1a',
    title: 'Step 1a — Gap analysis issue',
    subtitle: 'Deterministic: ensure a gap-analysis issue exists and is assigned.',
    details: (
      <>
        <Typography variant="body2" color="text.secondary">
          This stage ensures there is a live gap-analysis issue to work on.
        </Typography>
      </>
    ),
  },
  {
    key: '1b',
    title: 'Step 1b — Gap analysis execution',
    subtitle: 'Work happens on the gap-analysis issue; a PR may be opened.',
    details: (
      <Typography variant="body2" color="text.secondary">
        Operator/Copilot compares <code>goal.md</code> vs <code>system_capabilities.md</code> and produces the
        next actionable development artefact.
      </Typography>
    ),
  },
  {
    key: '1c',
    title: 'Step 1c — Gap analysis PR completion & merge',
    subtitle: 'Deterministic: merges the gap-analysis PR when it is ready and safe.',
    details: (
      <Typography variant="body2" color="text.secondary">
        The orchestrator refuses to merge until the PR is not WIP and a review has been requested.
      </Typography>
    ),
  },
  {
    key: '2a',
    title: 'Step 2a — Development issue creation',
    subtitle: 'Deterministic plumbing: pending file → GitHub issue → assign Copilot.',
    details: (
      <Typography variant="body2" color="text.secondary">
        The orchestrator promotes queued artefacts into GitHub issues. No AI. No decisions.
      </Typography>
    ),
  },
  {
    key: '2b',
    title: 'Step 2b — Development execution',
    subtitle: 'Copilot works the issue. PR created. Discussion happens.',
    details: (
      <Typography variant="body2" color="text.secondary">
        This is outside the orchestrator's intelligence.
      </Typography>
    ),
  },
  {
    key: '2c',
    title: 'Step 2c — Development PR completion & merge',
    subtitle: 'Deterministic job: checks status and merges (or refuses if unsafe).',
    details: (
      <Typography variant="body2" color="text.secondary">
        One job at a time. Reliable and boring.
      </Typography>
    ),
  },
  {
    key: '3a',
    title: 'Step 3a — Capability update issue',
    subtitle:
      'Triggered on merge: create a capability update issue containing PR description + comments; assign Copilot.',
    details: (
      <Typography variant="body2" color="text.secondary">
        This is the only place system self-knowledge is intentionally updated.
      </Typography>
    ),
  },
  {
    key: '3b',
    title: 'Step 3b — Capability update execution',
    subtitle: 'Copilot updates system_capabilities.md. Issue is closed.',
    details: (
      <Typography variant="body2" color="text.secondary">
        After this, declared capabilities match reality again.
      </Typography>
    ),
  },
  {
    key: '3c',
    title: 'Step 3c — Capability PR completion & merge',
    subtitle: 'Deterministic job: checks status and merges the capabilities update (then we’re back to Step 1a).',
    details: (
      <Typography variant="body2" color="text.secondary">
        One job at a time. Reliable and boring.
      </Typography>
    ),
  },
];

function LoopStepIcon(props: StepIconProps): React.JSX.Element {
  const iconNumber = typeof props.icon === 'number' ? props.icon : Number(props.icon);
  const idx = Number.isFinite(iconNumber) ? iconNumber - 1 : -1;
  const stageKey = idx >= 0 && idx < steps.length ? steps[idx]?.key ?? '?' : '?';

  if (props.completed) {
    return <CheckCircleIcon sx={{ color: 'success.main' }} />;
  }

  return (
    <Box
      sx={{
        width: 24,
        height: 24,
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 12,
        fontWeight: 800,
        border: '2px solid',
        borderColor: props.active ? 'primary.main' : 'divider',
        bgcolor: props.active ? 'primary.main' : 'transparent',
        color: props.active ? 'primary.contrastText' : 'text.secondary',
      }}
    >
      {stageKey}
    </Box>
  );
}

export function LoopPage(): React.JSX.Element {
  const res = useApiResource(() => apiFetch<LoopStatus>('/loop'), []);
  const [promoteBusy, setPromoteBusy] = React.useState(false);
  const [promoteError, setPromoteError] = React.useState<string | null>(null);
  const [promoteResult, setPromoteResult] = React.useState<PromoteResult | null>(null);
  const [mergeBusy, setMergeBusy] = React.useState(false);
  const [mergeError, setMergeError] = React.useState<string | null>(null);
  const [mergeResult, setMergeResult] = React.useState<MergeResult | null>(null);

  if (res.loading) {
    return (
      <div>
        <Typography variant="h5" gutterBottom>
          Loop
        </Typography>
        <LoadingState />
      </div>
    );
  }

  if (res.error) {
    return (
      <div>
        <Typography variant="h5" gutterBottom>
          Loop
        </Typography>
        <ErrorState message={res.error} onRetry={res.reload} />
      </div>
    );
  }

  if (!res.data) {
    return (
      <div>
        <Typography variant="h5" gutterBottom>
          Loop
        </Typography>
      </div>
    );
  }

  const data = res.data;
  const fmt = (v: number | null | undefined): string => (typeof v === 'number' ? String(v) : '—');

  const canPromote = data.stage === '2a';
  const canMerge = data.stage.endsWith('c');

  const onPromote = (): void => {
    setPromoteBusy(true);
    setPromoteError(null);
    setPromoteResult(null);

    void apiFetch<PromoteResult>('/loop/promote', { method: 'POST' })
      .then((out) => {
        setPromoteResult(out);
        res.reload();
      })
      .catch((e: unknown) => {
        setPromoteError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        setPromoteBusy(false);
      });
  };

  const onMerge = (): void => {
    setMergeBusy(true);
    setMergeError(null);
    setMergeResult(null);

    void apiFetch<MergeResult>('/loop/merge', { method: 'POST' })
      .then((out) => {
        setMergeResult(out);
        res.reload();
      })
      .catch((e: unknown) => {
        setMergeError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        setMergeBusy(false);
      });
  };

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Loop
      </Typography>

      <Stack spacing={2}>
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1.5}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
                  <Typography variant="h6" sx={{ flex: 1 }}>
                    Current stage: {data.stageLabel}
                  </Typography>
                  <Chip label={`Stage ${data.stage}`} variant="outlined" />
                </Stack>

                <Divider />

                {data.focus && (data.focus.title || data.focus.issueNumber || data.focus.pullNumber) ? (
                  <Box>
                    <Typography variant="subtitle2" color="text.secondary">
                      Current work
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      <strong>
                        {(() => {
                          const capSourceTitle =
                            data.focus.kind === 'capability' &&
                            typeof data.focus.sourceTitle === 'string' &&
                            data.focus.sourceTitle.trim().length > 0
                              ? data.focus.sourceTitle
                              : null;

                          if (capSourceTitle) return capSourceTitle;
                          if (data.focus.title && data.focus.title.trim().length > 0) return data.focus.title;
                          if (data.focus.kind === 'capability') return 'Capability update';
                          if (data.focus.kind === 'gap') return 'Gap analysis';
                          return 'Development';
                        })()}
                      </strong>
                      {typeof data.focus.issueNumber === 'number'
                        ? data.focus.kind === 'capability'
                          ? ` (capability issue #${data.focus.issueNumber})`
                          : data.focus.kind === 'gap'
                            ? ` (gap issue #${data.focus.issueNumber})`
                            : ` (issue #${data.focus.issueNumber})`
                        : ''}

                      {data.focus.kind === 'capability' && typeof data.focus.sourcePullNumber === 'number'
                        ? ` — source PR #${data.focus.sourcePullNumber}`
                        : typeof data.focus.pullNumber === 'number'
                          ? ` — PR #${data.focus.pullNumber}`
                          : ''}

                      {data.focus.kind === 'capability' &&
                      typeof data.focus.pullNumber === 'number' &&
                      typeof data.focus.sourcePullNumber === 'number' &&
                      data.focus.pullNumber !== data.focus.sourcePullNumber
                        ? ` — cap PR #${data.focus.pullNumber}`
                        : data.focus.kind === 'capability' &&
                            typeof data.focus.pullNumber === 'number' &&
                            typeof data.focus.sourcePullNumber !== 'number'
                          ? ` — cap PR #${data.focus.pullNumber}`
                          : ''}
                      {data.focus.issueUrl ? (
                        <>
                          {' '}
                          —{' '}
                          <a href={data.focus.issueUrl} target="_blank" rel="noreferrer">
                            issue
                          </a>
                        </>
                      ) : null}

                      {data.focus.kind === 'capability' ? (
                        <>
                          {data.focus.sourcePullUrl ? (
                            <>
                              {' '}
                              —{' '}
                              <a href={data.focus.sourcePullUrl} target="_blank" rel="noreferrer">
                                source pr
                              </a>
                            </>
                          ) : null}
                          {data.focus.pullUrl ? (
                            <>
                              {' '}
                              —{' '}
                              <a href={data.focus.pullUrl} target="_blank" rel="noreferrer">
                                cap pr
                              </a>
                            </>
                          ) : null}
                        </>
                      ) : data.focus.pullUrl ? (
                        <>
                          {' '}
                          —{' '}
                          <a href={data.focus.pullUrl} target="_blank" rel="noreferrer">
                            pr
                          </a>
                        </>
                      ) : null}
                    </Typography>
                  </Box>
                ) : null}

                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Issue queue
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Pending: <strong>{data.counts.pending}</strong> (unpromoted:{' '}
                      <strong>{fmt(data.counts.unpromotedPending)}</strong>)
                      <br />
                      Processed: <strong>{data.counts.processed}</strong>
                      <br />
                      Complete: <strong>{data.counts.complete}</strong>
                      <br />
                      Dev pending: <strong>{fmt(data.counts.pendingDevelopment)}</strong>
                      <br />
                      Capability pending: <strong>{fmt(data.counts.pendingCapabilityUpdates)}</strong>
                      <br />
                      Excluded pending: <strong>{fmt(data.counts.pendingExcluded)}</strong>
                    </Typography>
                  </Box>

                  <Box sx={{ flex: 1 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Issues
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Open: <strong>{fmt(data.counts.openIssues)}</strong>
                      <br />
                      Open PRs: <strong>{fmt(data.counts.openPullRequests)}</strong>
                      <br />
                      Gap analysis open: <strong>{fmt(data.counts.openGapAnalysisIssues)}</strong>
                    </Typography>
                  </Box>

                  <Box sx={{ flex: 1 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Last action
                    </Typography>
                    {data.lastAction ? (
                      <Typography variant="body2" color="text.secondary">
                        <Timestamp iso={data.lastAction.tsIso} /> — {data.lastAction.summary}
                      </Typography>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        —
                      </Typography>
                    )}
                  </Box>
                </Stack>

                {data.runningJob ? (
                  <Box>
                    <Typography variant="subtitle2" color="text.secondary">
                      Running job
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Job <code>{data.runningJob.jobId}</code>
                      {data.runningJob.issueNumber ? (
                        <>
                          {' '}
                          (issue #{data.runningJob.issueNumber})
                        </>
                      ) : null}
                    </Typography>
                  </Box>
                ) : null}

                {data.stageReason || (data.warnings && data.warnings.length) ? (
                  <Box>
                    <Typography variant="subtitle2" color="text.secondary">
                      Notes
                    </Typography>
                    {data.stageReason ? (
                      <Typography variant="body2" color="text.secondary">
                        Stage reason: {data.stageReason}
                      </Typography>
                    ) : null}
                    {data.warnings?.map((w) => (
                      <Typography key={w} variant="body2" color="text.secondary">
                        {w}
                      </Typography>
                    ))}
                  </Box>
                ) : null}

                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Button component={RouterLink} to="/cognitive-tasks" variant="outlined" size="small">
                    Cognitive Tasks
                  </Button>
                  <Button component={RouterLink} to="/issues" variant="outlined" size="small">
                    Issues
                  </Button>
                  <Button component={RouterLink} to="/timeline" variant="outlined" size="small">
                    Timeline
                  </Button>
                  <Button component={RouterLink} to="/docs" variant="outlined" size="small">
                    Planning Docs
                  </Button>
                </Stack>

                {canPromote ? (
                  <Box>
                    <Divider sx={{ my: 1.5 }} />
                    <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                      Step 2a actions
                    </Typography>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                      <Button
                        variant="contained"
                        size="small"
                        onClick={onPromote}
                        disabled={promoteBusy}
                      >
                        {promoteBusy ? 'Promoting…' : 'Promote next queue item'}
                      </Button>
                      <Typography variant="body2" color="text.secondary">
                        Creates the GitHub issue, assigns Copilot, and moves the file to <code>processed/</code>.
                      </Typography>
                    </Stack>

                    {promoteError ? (
                      <Typography sx={{ mt: 1 }} variant="body2" color="error">
                        {promoteError}
                      </Typography>
                    ) : null}

                    {promoteResult ? (
                      <Typography sx={{ mt: 1 }} variant="body2" color="text.secondary">
                        {promoteResult.summary}
                      </Typography>
                    ) : null}
                  </Box>
                ) : null}

                {canMerge ? (
                  <Box>
                    <Divider sx={{ my: 1.5 }} />
                    <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                      Merge actions
                    </Typography>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                      <Button
                        variant="contained"
                        size="small"
                        color="success"
                        onClick={onMerge}
                        disabled={mergeBusy}
                      >
                        {mergeBusy ? 'Merging…' : 'Approve + merge ready PR'}
                      </Button>
                      <Typography variant="body2" color="text.secondary">
                        Merges the next ready PR: capability-update PRs (Step 3c) take precedence; then gap-analysis PRs (Step 1c);
                        otherwise development PRs (Step 2c).
                      </Typography>
                    </Stack>

                    {mergeError ? (
                      <Typography sx={{ mt: 1 }} variant="body2" color="error">
                        {mergeError}
                      </Typography>
                    ) : null}

                    {mergeResult ? (
                      <Typography sx={{ mt: 1 }} variant="body2" color="text.secondary">
                        {mergeResult.summary}{' '}
                        {mergeResult.capabilityIssueUrl ? (
                          <>
                            —{' '}
                            <a href={mergeResult.capabilityIssueUrl} target="_blank" rel="noreferrer">
                              view issue
                            </a>
                          </>
                        ) : null}
                      </Typography>
                    ) : null}
                  </Box>
                ) : null}
              </Stack>
            </CardContent>
          </Card>

          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                The loop (1a–3c)
              </Typography>
              <Stepper activeStep={data.activeStep} orientation="vertical">
                {steps.map((s, idx) => (
                  <Step
                    key={s.key}
                    completed={idx < data.activeStep}
                    sx={{
                      '& .MuiStepLabel-root': {
                        borderRadius: 1,
                        px: 1,
                        py: 0.5,
                        ...(idx === data.activeStep ? { bgcolor: 'action.hover' } : null),
                      },
                    }}
                  >
                    <StepLabel StepIconComponent={LoopStepIcon}>
                      <Typography
                        variant="subtitle2"
                        sx={{
                          fontWeight: idx === data.activeStep ? 800 : 600,
                          color: idx === data.activeStep ? 'primary.main' : 'text.primary',
                        }}
                      >
                        {s.title}
                      </Typography>
                      <Typography
                        variant="body2"
                        color={idx === data.activeStep ? 'text.primary' : 'text.secondary'}
                      >
                        {s.subtitle}
                      </Typography>
                    </StepLabel>
                    <StepContent>{s.details}</StepContent>
                  </Step>
                ))}
              </Stepper>
            </CardContent>
          </Card>
        </Stack>
    </div>
  );
}
