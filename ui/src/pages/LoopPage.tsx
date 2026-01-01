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
import { Link as RouterLink } from 'react-router-dom';

import { apiFetch } from '../lib/apiClient';
import { endpoints } from '../lib/endpoints';
import { useApiResource } from '../lib/useApiResource';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { Timestamp } from '../components/Timestamp';

type LoopCounts = {
  pending: number;
  processed: number;
  complete: number;
  openIssues: number;
  openCapabilityUpdateIssues: number;
  unpromotedPending: number;
};

type RunningJob = {
  jobId: string;
  issueNumber: number | null;
  status: 'running';
  updatedAt: string;
};

type LoopStatus = {
  nowIso: string;
  stage: 'A' | 'B' | 'C' | 'D' | 'F';
  stageLabel: string;
  activeStep: number;
  counts: LoopCounts;
  runningJob: RunningJob | null;
  lastAction: null | { tsIso: string; summary: string; kind: string };
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

export function LoopPage(): React.JSX.Element {
  const res = useApiResource(() => apiFetch<LoopStatus>(endpoints.loop()), []);

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Loop
      </Typography>

      {res.loading ? <LoadingState /> : null}
      {res.error ? <ErrorState message={res.error} onRetry={res.reload} /> : null}

      {!res.loading && !res.error && res.data ? (
        <Stack spacing={2}>
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1.5}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
                  <Typography variant="h6" sx={{ flex: 1 }}>
                    Current stage: {res.data.stageLabel}
                  </Typography>
                  <Chip label={`Stage ${res.data.stage}`} variant="outlined" />
                </Stack>

                <Divider />

                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Issue queue
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Pending: <strong>{res.data.counts.pending}</strong> (unpromoted:{' '}
                      <strong>{res.data.counts.unpromotedPending}</strong>)
                      <br />
                      Processed: <strong>{res.data.counts.processed}</strong>
                      <br />
                      Complete: <strong>{res.data.counts.complete}</strong>
                    </Typography>
                  </Box>

                  <Box sx={{ flex: 1 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Issues
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Open: <strong>{res.data.counts.openIssues}</strong>
                      <br />
                      Capability updates open: <strong>{res.data.counts.openCapabilityUpdateIssues}</strong>
                    </Typography>
                  </Box>

                  <Box sx={{ flex: 1 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Last action
                    </Typography>
                    {res.data.lastAction ? (
                      <Typography variant="body2" color="text.secondary">
                        <Timestamp iso={res.data.lastAction.tsIso} /> — {res.data.lastAction.summary}
                      </Typography>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        —
                      </Typography>
                    )}
                  </Box>
                </Stack>

                {res.data.runningJob ? (
                  <Box>
                    <Typography variant="subtitle2" color="text.secondary">
                      Running job
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Job <code>{res.data.runningJob.jobId}</code>
                      {res.data.runningJob.issueNumber ? (
                        <>
                          {' '}
                          (issue #{res.data.runningJob.issueNumber})
                        </>
                      ) : null}
                    </Typography>
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
              </Stack>
            </CardContent>
          </Card>

          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                The loop (A–G)
              </Typography>
              <Stepper activeStep={res.data.activeStep} orientation="vertical">
                {steps.map((s) => (
                  <Step key={s.key}>
                    <StepLabel>
                      <Typography variant="subtitle2">{s.title}</Typography>
                      <Typography variant="body2" color="text.secondary">
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
      ) : null}
    </div>
  );
}
