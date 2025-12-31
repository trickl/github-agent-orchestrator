import { http, HttpResponse, delay } from 'msw';
import rulesFixture from './fixtures/rules.json';
import issuesFixture from './fixtures/issues.json';
import timelineFixture from './fixtures/timeline.json';
import docsFixture from './fixtures/docs.json';
import type { GenerationRule } from '../features/rules/ruleTypes';
import type { Issue } from '../features/issues/issueTypes';
import type { TimelineEvent } from '../features/timeline/timelineTypes';
import type { PlanningDoc } from '../features/planning/planningTypes';

type Health = { ok: true; version: string; repoName: string };

type DocsFixture = {
  goal: PlanningDoc;
  capabilities: PlanningDoc;
};

const rulesFixtureTyped = rulesFixture as unknown as GenerationRule[];
const issuesFixtureTyped = issuesFixture as unknown as Issue[];
const timelineFixtureTyped = timelineFixture as unknown as TimelineEvent[];
const docsFixtureTyped = docsFixture as unknown as DocsFixture;

let rules: GenerationRule[] = structuredClone(rulesFixtureTyped);
let issues: Issue[] = structuredClone(issuesFixtureTyped);
let timeline: TimelineEvent[] = structuredClone(timelineFixtureTyped);
let docs: DocsFixture = structuredClone(docsFixtureTyped);

export function resetMockState(): void {
  rules = structuredClone(rulesFixtureTyped);
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

  http.get('*/rules', async () => {
    await delay(150);
    return HttpResponse.json(rules);
  }),

  http.post('*/rules', async ({ request }) => {
    await delay(150);
    const body = (await request.json()) as Omit<GenerationRule, 'id' | 'lastRunIso' | 'nextEligibleIso' | 'editable'>;
    const created: GenerationRule = {
      ...body,
      id: id('rule'),
      editable: true,
    };
    rules = [created, ...rules];
    timeline = [
      {
        id: id('evt'),
        tsIso: nowIso(),
        kind: 'NOTE',
        summary: `Rule created: ${created.name}`,
        ruleId: created.id,
        typePath: created.targetFolder,
      },
      ...timeline,
    ];
    return HttpResponse.json(created, { status: 201 });
  }),

  http.put('*/rules/:id', async ({ params, request }) => {
    await delay(150);
    const idParam = String(params.id);
    const body = (await request.json()) as GenerationRule;
    rules = rules.map((r) => (r.id === idParam ? { ...body, id: idParam } : r));
    return HttpResponse.json(rules.find((r) => r.id === idParam));
  }),

  http.delete('*/rules/:id', async ({ params }) => {
    await delay(150);
    const idParam = String(params.id);
    rules = rules.filter((r) => r.id !== idParam);
    timeline = [
      {
        id: id('evt'),
        tsIso: nowIso(),
        kind: 'NOTE',
        summary: `Rule deleted: ${idParam}`,
        ruleId: idParam,
      },
      ...timeline,
    ];
    return HttpResponse.json({ ok: true });
  }),

  http.post('*/rules/:id/run', async ({ params }) => {
    await delay(250);
    const ruleId = String(params.id);
    const rule = rules.find((r) => r.id === ruleId);
    if (!rule) {
      return HttpResponse.json({ ok: false }, { status: 404 });
    }

    const createdIssueId = `pending/${id('dev')}.md`;
    const createdIssueTitle = `Dev: Generated by ${rule.name}`;

    const newIssue: Issue = {
      id: createdIssueId,
      title: createdIssueTitle,
      typePath: rule.targetFolder,
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
        summary: `Created issue for rule: ${rule.name}`,
        ruleId,
        issueId: createdIssueId,
        issueTitle: createdIssueTitle,
        typePath: rule.targetFolder,
      },
      ...timeline,
    ];

    rules = rules.map((r) => (r.id === ruleId ? { ...r, lastRunIso: nowIso() } : r));

    return HttpResponse.json({
      ok: true,
      createdIssueId,
      createdIssueTitle,
      timelineEventId: evtId,
    });
  }),
];
