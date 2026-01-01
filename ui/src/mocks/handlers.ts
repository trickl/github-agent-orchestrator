import { http, HttpResponse, delay } from 'msw';
import cognitiveTasksFixture from './fixtures/cognitive_tasks.json';
import issuesFixture from './fixtures/issues.json';
import timelineFixture from './fixtures/timeline.json';
import docsFixture from './fixtures/docs.json';
import type { CognitiveTask } from '../features/cognitiveTasks/cognitiveTaskTypes';
import type { Issue } from '../features/issues/issueTypes';
import type { TimelineEvent } from '../features/timeline/timelineTypes';
import type { PlanningDoc } from '../features/planning/planningTypes';

type Health = { ok: true; version: string; repoName: string };

type DocsFixture = {
  goal: PlanningDoc;
  capabilities: PlanningDoc;
};

const cognitiveTasksFixtureTyped = cognitiveTasksFixture as unknown as CognitiveTask[];
const issuesFixtureTyped = issuesFixture as unknown as Issue[];
const timelineFixtureTyped = timelineFixture as unknown as TimelineEvent[];
const docsFixtureTyped = docsFixture as unknown as DocsFixture;

let tasks: CognitiveTask[] = structuredClone(cognitiveTasksFixtureTyped);
let issues: Issue[] = structuredClone(issuesFixtureTyped);
let timeline: TimelineEvent[] = structuredClone(timelineFixtureTyped);
let docs: DocsFixture = structuredClone(docsFixtureTyped);

export function resetMockState(): void {
  tasks = structuredClone(cognitiveTasksFixtureTyped);
  issues = structuredClone(issuesFixtureTyped);
  timeline = structuredClone(timelineFixtureTyped);
  docs = structuredClone(docsFixtureTyped);
}

function nowIso(): string {
  return new Date().toISOString();
}

export const handlers = [
  http.get('*/health', async () => {
    await delay(150);
    const resp: Health = { ok: true, version: 'dev', repoName: 'github-agent-orchestrator' };
    return HttpResponse.json(resp);
  }),

  http.get('*/overview', async () => {
    await delay(150);
    const openIssueCount = issues.filter((i) => i.status !== 'CLOSED').length;
    const activeIssueId = issues.find((i) => i.isActive)?.id ?? null;
    const first = timeline[0];
    const lastEventIso = first ? first.tsIso : nowIso();

    return HttpResponse.json({ activeIssueId, openIssueCount, lastEventIso });
  }),

  http.get('*/loop', async () => {
    await delay(150);

    const pending = issues.filter((i) => i.status === 'PENDING').length;
    const openIssues = issues.filter((i) => !['CLOSED', 'MERGED'].includes(i.status)).length;
    const openGapAnalysisIssues = issues.filter(
      (i) => i.title.toLowerCase().trim() === 'identify the next most important development gap'
    ).length;

    // The mock data doesn't currently model PR objects. Approximate with prUrl presence.
    const openPullRequests = issues.filter((i) => i.prUrl && !['MERGED', 'CLOSED'].includes(i.status)).length;

    // In mocks, treat all pending as development tasks unless explicitly prefixed.
    const pendingDevelopment = issues.filter(
      (i) => i.status === 'PENDING' && !i.title.toLowerCase().startsWith('system:')
    ).length;
    const pendingCapabilityUpdates = issues.filter(
      (i) => i.status === 'PENDING' && i.title.toLowerCase().startsWith('system:')
    ).length;

    const pendingDevelopmentWithoutPr = issues.filter(
      (i) => i.status === 'PENDING' && !i.prUrl && !i.title.toLowerCase().startsWith('system:')
    ).length;
    const pendingDevelopmentWithPr = issues.filter(
      (i) => i.status === 'PENDING' && Boolean(i.prUrl) && !i.title.toLowerCase().startsWith('system:')
    ).length;

    let stage: 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' = 'A';
    let stageLabel = 'Gap analysis';
    let activeStep = 0;

    // Follow the backend stage priority using the available mock signals.
    if (openGapAnalysisIssues > 0) {
      stage = 'A';
      stageLabel = 'Gap analysis';
      activeStep = 0;
    } else if (pendingDevelopment > 0) {
      if (pendingDevelopmentWithoutPr > 0) {
        stage = 'B';
        stageLabel = 'Issue creation';
        activeStep = 1;
      } else if (pendingDevelopmentWithPr > 0) {
        stage = 'C';
        stageLabel = 'Development (Copilot)';
        activeStep = 2;
      }
    } else if (pendingCapabilityUpdates > 0) {
      stage = 'E';
      stageLabel = 'Capability update queued';
      activeStep = 4;
    }

    const first = timeline[0];
    const lastAction =
      first ? { tsIso: first.tsIso, summary: first.summary, kind: first.kind } : null;

    return HttpResponse.json({
      nowIso: nowIso(),
      stage,
      stageLabel,
      activeStep,
      stageReason: 'mock backend',
      counts: {
        pending,
        processed: 0,
        complete: 0,
        openIssues,
        openPullRequests,
        openGapAnalysisIssues,
        unpromotedPending: pending,

        pendingDevelopment,
        pendingCapabilityUpdates,
        pendingExcluded: 0,

        pendingDevelopmentWithoutPr,
        pendingDevelopmentWithPr,
        pendingDevelopmentReadyForReview: 0,

        pendingCapabilityUpdatesWithoutPr: pendingCapabilityUpdates,
        pendingCapabilityUpdatesWithPr: 0,
        pendingCapabilityUpdatesReadyForReview: 0,
      },
      runningJob: null,
      lastAction,
    });
  }),

  http.get('*/issues', async ({ request }) => {
    await delay(150);
    const url = new URL(request.url);
    const status = url.searchParams.get('status') ?? 'open';
    const out =
      status === 'all'
        ? issues
        : issues.filter((i) => ['PENDING', 'OPEN', 'ASSIGNED', 'PR_OPEN', 'BLOCKED', 'FAILED'].includes(i.status));
    return HttpResponse.json(out);
  }),

  http.get('*/active', async () => {
    await delay(150);
    const activeIssue = issues.find((i) => i.isActive) ?? null;
    const first = timeline[0];
    const lastAction = first ? { tsIso: first.tsIso, summary: first.summary } : null;
    return HttpResponse.json({ activeIssue, lastAction });
  }),

  http.get('*/timeline', async ({ request }) => {
    await delay(150);
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get('limit') ?? '200');
    return HttpResponse.json(timeline.slice(0, Number.isFinite(limit) ? limit : 200));
  }),

  http.get('*/docs/goal', async () => {
    await delay(150);
    return HttpResponse.json(docs.goal);
  }),

  http.get('*/docs/capabilities', async () => {
    await delay(150);
    return HttpResponse.json(docs.capabilities);
  }),

  http.get('*/cognitive-tasks', async () => {
    await delay(150);
    return HttpResponse.json(tasks);
  }),
];
