import { http, HttpResponse, delay } from 'msw';
import rulesFixture from './fixtures/rules.json';
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

const rulesFixtureTyped = rulesFixture as unknown as CognitiveTask[];
const issuesFixtureTyped = issuesFixture as unknown as Issue[];
const timelineFixtureTyped = timelineFixture as unknown as TimelineEvent[];
const docsFixtureTyped = docsFixture as unknown as DocsFixture;

let tasks: CognitiveTask[] = structuredClone(rulesFixtureTyped);
let issues: Issue[] = structuredClone(issuesFixtureTyped);
let timeline: TimelineEvent[] = structuredClone(timelineFixtureTyped);
let docs: DocsFixture = structuredClone(docsFixtureTyped);

export function resetMockState(): void {
  tasks = structuredClone(rulesFixtureTyped);
  issues = structuredClone(issuesFixtureTyped);
  timeline = structuredClone(timelineFixtureTyped);
  docs = structuredClone(docsFixtureTyped);
}

function nowIso(): string {
  return new Date().toISOString();
}

function id(prefix: string): string {
  return `${prefix}-${Math.random().toString(16).slice(2, 10)}`;
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
    const openCapabilityUpdateIssues = issues.filter((i) =>
      i.title.startsWith('Update system capabilities based on merged PR')
    ).length;

    let stage: 'A' | 'B' | 'C' | 'D' | 'F' = 'A';
    let stageLabel = 'Gap analysis';
    let activeStep = 0;

    // Mock jobs are not currently simulated.
    if (openCapabilityUpdateIssues > 0) {
      stage = 'F';
      stageLabel = 'Capability update execution';
      activeStep = 5;
    } else if (openIssues > 0) {
      stage = 'C';
      stageLabel = 'Development (Copilot)';
      activeStep = 2;
    } else if (pending > 0) {
      stage = 'B';
      stageLabel = 'Issue creation';
      activeStep = 1;
    }

    const first = timeline[0];
    const lastAction =
      first ? { tsIso: first.tsIso, summary: first.summary, kind: first.kind } : null;

    return HttpResponse.json({
      nowIso: nowIso(),
      stage,
      stageLabel,
      activeStep,
      counts: {
        pending,
        processed: 0,
        complete: 0,
        openIssues,
        openCapabilityUpdateIssues,
        unpromotedPending: pending,
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

  http.post('*/issues/refresh', () => {
    // In mocks we don't call GitHub; just report success.
    return HttpResponse.json({ updated: 0 });
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

  http.post('*/cognitive-tasks', async ({ request }) => {
    await delay(150);
    const body = (await request.json()) as Omit<CognitiveTask, 'id' | 'lastRunIso' | 'nextEligibleIso' | 'editable'>;
    const created: CognitiveTask = {
      ...body,
      id: id('task'),
      editable: true,
    };
    tasks = [created, ...tasks];
    timeline = [
      {
        id: id('evt'),
        tsIso: nowIso(),
        kind: 'NOTE',
        summary: `Cognitive task created: ${created.name}`,
        cognitiveTaskId: created.id,
        typePath: created.targetFolder,
      },
      ...timeline,
    ];
    return HttpResponse.json(created, { status: 201 });
  }),

  http.put('*/cognitive-tasks/:id', async ({ params, request }) => {
    await delay(150);
    const idParam = String(params.id);
    const body = (await request.json()) as CognitiveTask;
    tasks = tasks.map((t) => (t.id === idParam ? { ...body, id: idParam } : t));
    return HttpResponse.json(tasks.find((t) => t.id === idParam));
  }),

  http.delete('*/cognitive-tasks/:id', async ({ params }) => {
    await delay(150);
    const idParam = String(params.id);
    tasks = tasks.filter((t) => t.id !== idParam);
    timeline = [
      {
        id: id('evt'),
        tsIso: nowIso(),
        kind: 'NOTE',
        summary: `Cognitive task deleted: ${idParam}`,
        cognitiveTaskId: idParam,
      },
      ...timeline,
    ];
    return HttpResponse.json({ ok: true });
  }),

  http.post('*/cognitive-tasks/:id/run', async ({ params }) => {
    await delay(250);
    const taskId = String(params.id);
    const task = tasks.find((t) => t.id === taskId);
    if (!task) {
      return HttpResponse.json({ ok: false }, { status: 404 });
    }

    const createdIssueId = `pending/${id('dev')}.md`;
    const createdIssueTitle = `Dev: Generated by ${task.name}`;

    const newIssue: Issue = {
      id: createdIssueId,
      title: createdIssueTitle,
      typePath: task.targetFolder,
      status: 'PENDING',
      ageSeconds: 0,
      lastUpdatedIso: nowIso(),
      isActive: false,
    };
    issues = [newIssue, ...issues];

    const evtId = id('evt');
    timeline = [
      {
        id: evtId,
        tsIso: nowIso(),
        kind: 'ISSUE_FILE_CREATED',
        summary: `Created issue for cognitive task: ${task.name}`,
        cognitiveTaskId: taskId,
        issueId: createdIssueId,
        issueTitle: createdIssueTitle,
        typePath: task.targetFolder,
      },
      ...timeline,
    ];

    tasks = tasks.map((t) => (t.id === taskId ? { ...t, lastRunIso: nowIso() } : t));

    return HttpResponse.json({
      ok: true,
      createdIssueId,
      createdIssueTitle,
      timelineEventId: evtId,
    });
  }),
];
