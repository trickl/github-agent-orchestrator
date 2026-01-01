import { test, expect } from '@playwright/test';

test('App loads and sidebar navigation works', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Orchestrator Dashboard')).toBeVisible();

  await page.getByRole('link', { name: 'Loop' }).click();
  await expect(page.getByRole('heading', { name: 'Loop' })).toBeVisible();

  await page.getByRole('link', { name: 'Timeline' }).click();
  await expect(page.getByRole('heading', { name: 'Timeline' })).toBeVisible();

  await page.getByRole('link', { name: 'Active Work' }).click();
  await expect(page.getByRole('heading', { name: 'Active Work' })).toBeVisible();

  await page.getByRole('link', { name: 'Issues' }).click();
  await expect(page.getByRole('heading', { name: 'Issues' })).toBeVisible();

  await page.getByRole('link', { name: 'Cognitive Tasks' }).click();
  await expect(page.getByRole('heading', { name: 'Cognitive Tasks' })).toBeVisible();

  await page.getByRole('link', { name: 'Planning Docs' }).click();
  await expect(page.getByRole('heading', { name: 'Planning Docs' })).toBeVisible();
});

test('Rules page: edit rule, run now, verify timeline event appears', async ({ page }) => {
  await page.goto('/cognitive-tasks');
  await expect(page.getByText('Gap analysis: observability')).toBeVisible();

  const row = page.locator('tr', { hasText: 'Gap analysis: observability' });

  await row.getByLabel('Edit').click();
  await expect(page.getByText('Edit rule')).toBeVisible();

  const name = page.getByLabel('Name');
  await name.fill('Gap analysis: observability (e2e)');
  await page.getByRole('button', { name: 'Save' }).click();

  await expect(page.getByText('Gap analysis: observability (e2e)')).toBeVisible();

  const updatedRow = page.locator('tr', { hasText: 'Gap analysis: observability (e2e)' });
  await updatedRow.getByRole('button', { name: 'Run now' }).click();
  await expect(page.getByText('Run rule now?')).toBeVisible();
  await page.getByRole('button', { name: 'Run now' }).click();

  await expect(page.getByText(/Created issue:/i)).toBeVisible();

  await page.getByRole('link', { name: 'Timeline' }).click();
  await expect(page.getByText(/Created issue for rule:/i)).toBeVisible();
});

test('Issues page: active issue row marked', async ({ page }) => {
  await page.goto('/issues');
  await expect(page.getByText('Dev: Improve timeline event persistence')).toBeVisible();

  const activeRow = page.locator('[data-testid="issue-row"][data-active="true"]');
  await expect(activeRow).toHaveCount(1);
});

test('Docs page renders goal and capabilities', async ({ page }) => {
  await page.goto('/docs');
  await expect(page.getByText('planning/vision/goal.md')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Goal', level: 1 })).toBeVisible();

  await page.getByRole('tab', { name: 'Capabilities' }).click();
  await expect(page.getByText('planning/state/system_capabilities.md')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'System Capabilities', level: 1 })).toBeVisible();
});
