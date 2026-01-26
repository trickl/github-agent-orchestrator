# Costing and premium request estimates

This project provides **conservative** cost estimates for GitHub Copilot premium
requests to help teams budget. Actual costs depend on your Copilot plan, model
multipliers, and billing policies. Always verify with GitHub's usage and billing
pages.

## Baseline assumptions (conservative)

- Each Copilot coding agent PR is treated as **one premium request**.
- Each iteration is assumed to produce **3 PRs**.
- Default premium request cost is **$0.04 USD**.

This yields a conservative estimate of:

$$
\text{cost per iteration} = 3 \times 1 \times 0.04 = 0.12\,\text{USD}
$$

## Configuration

Override the defaults using environment variables:

- `ORCHESTRATOR_PREMIUM_REQUEST_COST_USD` (default: `0.04`)
- `ORCHESTRATOR_ESTIMATED_PREMIUM_REQUESTS_PER_PR` (default: `1`)
- `ORCHESTRATOR_ESTIMATED_PRS_PER_ITERATION` (default: `3`)

## Check actual usage and set budgets

GitHub provides authoritative usage and billing information. Use these sources to
track actual costs and set limits:

- Premium request usage and analytics in GitHub billing settings
- Premium request analytics reports
- Budgets for Copilot premium requests

For details, see:

- https://docs.github.com/en/copilot/concepts/billing/copilot-requests
- https://docs.github.com/en/copilot/how-tos/manage-and-track-spending/monitor-premium-requests
- https://docs.github.com/en/billing/how-tos/products/view-productlicense-use
- https://docs.github.com/en/billing/managing-your-billing/using-budgets-control-spending
