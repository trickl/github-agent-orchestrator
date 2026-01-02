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
  stage: 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';
  stageLabel: string;
  activeStep: number;
  counts: LoopCounts;
  runningJob: RunningJob | null;
  lastAction: null | { tsIso: string; summary: string; kind: string };
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
  queuePath: string;
  completePath: string;
  developmentIssueNumber: number;
  pullNumber: number;
  approved: boolean;
  approvalError: string | null;
  headBranchDeleted: boolean;
  capabilityIssueNumber: number;
  capabilityIssueCreated: boolean;
  capabilityIssueUrl: string | null;
  capabilityIssueAssigned: string[];
  summary: string;
};

const steps: Array<{
  key: string;
  title: string;
  subtitle: string;
  details: React.ReactNode;
}> = [
  {
    key: 'A',
    title: 'Step A — Gap analysis (cognitive, explicit)',
    subtitle: 'Manual or semi-manual: compare goal vs capabilities; output one queue artefact.',
    details: (
      <>
        <Typography variant="body2" color="text.secondary">
          Produces exactly one file in <code>planning/issue_queue/pending/</code>. The file is the handoff
          artefact.
        </Typography>
      </>
    ),
  },
  {
    key: 'B',
    title: 'Step B — Issue creation (automatic, hardwired)',
    subtitle: 'Deterministic plumbing: pending file → GitHub issue → assign Copilot.',
    details: (
      <Typography variant="body2" color="text.secondary">
        The orchestrator promotes queued artefacts into GitHub issues. No AI. No decisions.
      </Typography>
    ),
  },
  {
    key: 'C',
    title: 'Step C — Development (external / Copilot)',
    subtitle: 'Copilot works the issue. PR created. Discussion happens.',
    details: (
      <Typography variant="body2" color="text.secondary">
        This is outside the orchestrator's intelligence.
      </Typography>
    ),
  },
  {
    key: 'D',
    title: 'Step D — PR completion & merge (automatic)',
    subtitle: 'Deterministic job: checks status and merges (or refuses if unsafe).',
    details: (
      <Typography variant="body2" color="text.secondary">
        One job at a time. Reliable and boring.
      </Typography>
    ),
  },
  {
    key: 'E',
    title: 'Step E — Capability update issue (cognitive, triggered)',
    subtitle: 'On merge: create a new issue containing PR description + comments; ask to update capabilities.',
    details: (
      <Typography variant="body2" color="text.secondary">
        This is the only place system self-knowledge is intentionally updated.
      </Typography>
    ),
  },
  {
    key: 'F',
    title: 'Step F — Capability update execution',
    subtitle: 'Copilot updates system_capabilities.md. Issue is closed.',
    details: (
      <Typography variant="body2" color="text.secondary">
        After this, declared capabilities match reality again.
      </Typography>
    ),
  },
  {
    key: 'G',
    title: 'Step G — Repeat',
    subtitle: 'With updated capabilities: run gap analysis again and continue the loop.',
    details: (
      <Typography variant="body2" color="text.secondary">
        Rinse, iterate, ship.
      </Typography>
    ),
  },
];

function LoopStepIcon(props: StepIconProps): React.JSX.Element {
  const iconNumber = typeof props.icon === 'number' ? props.icon : Number(props.icon);
  const idx = Number.isFinite(iconNumber) ? iconNumber - 1 : -1;
  const letter = idx >= 0 && idx < steps.length ? steps[idx]?.key ?? '?' : '?';

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
      {letter}
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

  const canPromote = data.stage === 'B';
  const canMerge = data.stage === 'D';

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
                      Step B actions
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
                      Step D actions
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
                        Attempts to approve and merge the next ready development PR, then creates a capability update issue.
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
                The loop (A–G)
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
