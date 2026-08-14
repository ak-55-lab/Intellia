# Intellia Semantic Layer

## Purpose

This semantic layer defines the core business objects, table relationships, column meanings, and SaaS revenue metrics used by Intellia.

The goal is to make analytics consistent across dashboards, agents, and GTM workflows.

## Core Tables

### accounts

Definition: Companies in the GTM universe. An account may be a customer or prospect.

Grain: One row per account.

Primary key: `account_id`

Columns:

- `account_id`: Unique account identifier.
- `account_name`: Company name.
- `domain`: Company web domain.
- `industry`: Industry category.
- `arr`: Current annual recurring revenue for customer accounts. Prospects have `0`.
- `employee_count`: Approximate company employee count.
- `tier`: Account tier based on employee count and ARR. Values: `Tier 1`, `Tier 2`, `Tier 3`.
- `status`: Account lifecycle status. Values: `Customer`, `Prospect`.
- `created_at`: Date the account was created.

Common uses:

- Account segmentation
- ICP scoring
- Customer versus prospect analysis
- Industry and tier reporting
- ARR-based account prioritization

### contacts

Definition: People associated with accounts.

Grain: One row per contact.

Primary key: `contact_id`

Foreign keys:

- `account_id` joins to `accounts.account_id`

Columns:

- `contact_id`: Unique contact identifier.
- `account_id`: Account the contact belongs to.
- `first_name`: Contact first name.
- `last_name`: Contact last name.
- `email`: Contact email address.
- `title`: Job title.
- `persona_role`: Buying committee role. Examples: `Economic Buyer`, `Champion`, `Executive Sponsor`, `Technical Evaluator`.
- `is_champion`: Boolean flag for whether the contact is a known champion.
- `created_at`: Date the contact was created.

Common uses:

- Buying committee mapping
- Champion identification
- Persona-based outreach
- Account engagement analysis

### users

Definition: Internal Intellia users and GTM team members.

Grain: One row per user.

Primary key: `user_id`

Columns:

- `user_id`: Unique internal user identifier.
- `full_name`: User full name.
- `email`: User work email.
- `role`: User role, such as `AE`, `Senior AE`, `Sales Manager`, `RevOps Lead`, or `CSM`.
- `department`: User department.
- `quota_annual`: Annual quota amount. Non-quota roles may have `0`.
- `hire_date`: User hire date.

Common uses:

- Owner reporting
- Sales capacity analysis
- Quota coverage
- Department-level GTM reporting

### deals

Definition: Revenue opportunities associated with accounts.

Grain: One row per deal or opportunity.

Primary key: `deal_id`

Foreign keys:

- `account_id` joins to `accounts.account_id`
- `owner_id` joins to `users.user_id`

Columns:

- `deal_id`: Unique deal identifier.
- `account_id`: Account associated with the deal.
- `owner_id`: Internal owner of the deal.
- `deal_name`: Human-readable deal name.
- `deal_type`: Deal category. Values include `New Logo`, `Upsell`, and `Renewal`. The current dummy data may not contain every allowed value.
- `stage`: Current or final deal stage. Stage order is Discovery, Qualification, Evaluation, Proposal, Closed Won or Closed Lost.
- `amount`: Deal amount in dollars.
- `close_date`: Expected or actual close date.
- `created_date`: Date the deal was created.
- `win_loss_reason`: Reason for closed-won or closed-lost outcome when available.

Common uses:

- Pipeline analysis
- Bookings reporting
- Win-rate reporting
- Forecasting
- Pipeline generation
- Deal velocity and conversion analysis

### emails

Definition: Email interactions between contacts and internal users.

Grain: One row per email.

Primary key: `email_id`

Foreign keys:

- `account_id` joins to `accounts.account_id`
- `contact_id` joins to `contacts.contact_id`

Columns:

- `email_id`: Unique email identifier.
- `account_id`: Account associated with the email.
- `contact_id`: Contact associated with the email.
- `sender_email`: Email sender.
- `recipient_email`: Email recipient.
- `direction`: Email direction. Values: `Inbound`, `Outbound`.
- `subject`: Email subject.
- `sent_at`: Email sent timestamp.
- `sentiment_score`: Sentiment score from `-1.0` to `1.0`, where higher is more positive.

Common uses:

- Engagement analysis
- Sentiment tracking
- Account activity scoring
- Deal risk and momentum detection

### meetings

Definition: Meetings between Intellia users and accounts.

Grain: One row per meeting.

Primary key: `meeting_id`

Foreign keys:

- `account_id` joins to `accounts.account_id`
- `organizer_id` joins to `users.user_id`

Columns:

- `meeting_id`: Unique meeting identifier.
- `account_id`: Account associated with the meeting.
- `organizer_id`: Internal meeting organizer.
- `title`: Meeting title.
- `scheduled_start`: Meeting start timestamp.
- `scheduled_end`: Meeting end timestamp.
- `status`: Meeting status. Values include `Scheduled` and `Completed`.
- `agenda`: Meeting agenda or purpose.

Common uses:

- Account engagement tracking
- Upcoming meeting visibility
- Completed activity reporting
- Sales and customer success follow-up workflows

### signals

Definition: External or derived GTM signals detected for an account or contact.

Grain: One row per signal.

Primary key: `signal_id`

Foreign keys:

- `account_id` joins to `accounts.account_id`
- `contact_id` joins to `contacts.contact_id` when populated

Columns:

- `signal_id`: Unique signal identifier.
- `account_id`: Account associated with the signal.
- `contact_id`: Contact associated with the signal, if applicable.
- `signal_type`: Signal category. Examples: `Champion Movement`, `Intent Score`, `M&A Event`, `Executive Departure`.
- `signal_title`: Short signal description.
- `score`: Signal strength or priority score from `0` to `100`.
- `detected_at`: Timestamp when the signal was detected.
- `action_recommended`: Recommended next action.

Common uses:

- Account prioritization
- Next-best-action recommendations
- Trigger-based outreach
- Risk and opportunity detection

### tasks

Definition: Outstanding work items owned by an internal user, sourced from meetings, emails,
signals, or created manually.

Grain: One row per task. Primary key: `task_id`.

Foreign keys: `account_id` to `accounts`, `deal_id` to `deals`, `owner_id` to `users`.

Columns: `title`, `description`, `due_date`, `priority` (`High`/`Medium`/`Low`),
`status` (`Open`/`In Progress`/`Done`), `source` (`meeting`/`email`/`signal`/`manual`),
`created_at`, `completed_at`.

Common uses: action queue, overdue follow-up detection, rep workload.

### targets

Definition: Revenue targets per user and period. Replaces dividing annual quota by four.

Grain: One row per user, period and metric. Primary key: `target_id`.

Foreign key: `user_id` to `users`.

Columns: `period_type` (`quarter`/`year`), `period_start`, `period_end`,
`metric` (`bookings`), `target_amount`.

Common uses: quota attainment, forecast vs target, pipeline coverage.

## Enriched Columns

Beyond the base columns described above, the following support the My Day experience:

- `users`: `manager_id` (self-referencing -- the team hierarchy), `region`, `is_active`.
- `accounts`: `region`, `segment`, `owner_id`, `renewal_date`, `health_score`.
- `contacts`: `seniority`, `influence`, `last_contacted_at`. `is_champion` is stored as
  integer `1`/`0`.
- `deals`: `probability`, `forecast_category` (`Commit`/`Best Case`/`Pipeline`/`Omitted`/`Closed`),
  `stage_entered_at` (drives stalled-deal detection), `last_activity_date`, `next_step`,
  `next_step_due_date`, `competitor`, `source`.
- `emails`: `thread_id`, `body`, `snippet`, `is_reply`, `has_attachment`, `deal_id`.
- `meetings`: `deal_id`, `meeting_type`, `duration_minutes`, `location`, `summary`,
  `key_points` (JSON array), `next_steps` (JSON array), `outcome`,
  `attendee_contact_ids` (JSON), `attendee_user_ids` (JSON).
- `signals`: `owner_id`, `playbook` (maps to the outreach playbooks in `brain.md`), `severity`,
  `status` (`New`/`Actioned`/`Dismissed`), `expires_at`, `source_url`.

## Relationships

Core joins:

- `accounts.account_id` to `contacts.account_id`
- `accounts.account_id` to `deals.account_id`
- `accounts.account_id` to `emails.account_id`
- `accounts.account_id` to `meetings.account_id`
- `accounts.account_id` to `signals.account_id`
- `contacts.contact_id` to `emails.contact_id`
- `contacts.contact_id` to `signals.contact_id`
- `users.user_id` to `deals.owner_id`
- `users.user_id` to `meetings.organizer_id`
- `users.user_id` to `users.manager_id` (self-referencing team hierarchy)
- `users.user_id` to `tasks.owner_id`
- `users.user_id` to `targets.user_id`
- `accounts.account_id` to `tasks.account_id`
- `deals.deal_id` to `tasks.deal_id`, `emails.deal_id`, `meetings.deal_id`

Recommended model shape:

- `accounts` is the central account dimension.
- `deals` is the primary revenue fact table.
- `emails`, `meetings`, and `signals` are activity and signal fact tables.
- `contacts` and `users` are supporting dimensions.

## Standard Filters

Closed-won deals:

- `stage = 'Stage 5 - Closed Won'`

Closed-lost deals:

- `stage = 'Stage 5 - Closed Lost'`

Closed deals:

- `stage in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')`

Open deals:

- `stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')`

Pipeline deals:

- `stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')`
- Open Pipeline includes every non-closed stage (Stage 1 through Stage 4).
- Use `stage = 'Stage 1 - Discovery'` only when the user explicitly asks for early-stage or Discovery pipeline.

New logo deals:

- `deal_type = 'New Logo'`

Upsell deals:

- `deal_type = 'Upsell'`

Renewal deals:

- `deal_type = 'Renewal'`

Stage order:

- `Stage 1 - Discovery`
- `Stage 2 - Qualification`
- `Stage 3 - Evaluation`
- `Stage 4 - Proposal`
- `Stage 5 - Closed Won`
- `Stage 5 - Closed Lost`

## Date Fields

Use `close_date` when analyzing expected or actual revenue timing.

Use `created_date` when analyzing pipeline creation and demand generation performance.

Use `created_at` for account and contact creation analysis.

Use `sent_at`, `scheduled_start`, and `detected_at` for activity and signal timelines.

For examples in this project, assume the current reporting date is August 13, 2026.

Current calendar quarter:

- Q3 2026
- Start date: `2026-07-01`
- End date: `2026-09-30`

Current year-to-date period:

- Start date: `2026-01-01`
- End date: `2026-08-13`

## Core SaaS Metrics

### Bookings

Definition: Total value of closed-won deals based on close date.

Date basis: `deals.close_date`

Formula:

```sql
sum(case
  when stage = 'Stage 5 - Closed Won'
  then amount
  else 0
end)
```

Example interpretation:

Bookings for Q3 means the sum of `amount` for deals that were closed won with `close_date` in Q3.

### Open Pipeline

Definition: Total value of open (non-closed) deals based on close date.

Date basis: `deals.close_date`

Formula:

```sql
sum(case
  when stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  then amount
  else 0
end)
```

Example interpretation:

Open Pipeline for Q3 means the sum of `amount` for deals still open with `close_date` in Q3.

### Early-Stage Pipeline

Definition: Total value of Stage 1 Discovery deals only. Use when the user explicitly asks for
early-stage, Discovery, or top-of-funnel pipeline.

Formula:

```sql
sum(case
  when stage = 'Stage 1 - Discovery'
  then amount
  else 0
end)
```

### Pipeline Generation

Definition: Total value of deals created during a time period.

Date basis: `deals.created_date`

Formula:

```sql
sum(amount)
```

Recommended filter:

```sql
created_date between period_start and period_end
```

Example interpretation:

Pipeline Generation for July means the sum of `amount` for deals where `created_date` is in July, regardless of current stage.

Optional stricter version:

```sql
sum(case
  when stage != 'Stage 5 - Closed Lost'
  then amount
  else 0
end)
```

Use the stricter version only when the business wants generated pipeline to exclude deals that have already been disqualified or lost.

### Win Rate

Definition: Percentage of closed deal value that was won.

Date basis: `deals.close_date`

Cohort: Close date cohort. Include deals with `close_date` in the reporting period and final stage of closed won or closed lost.

Revenue win rate formula:

```sql
sum(case
  when stage = 'Stage 5 - Closed Won'
  then amount
  else 0
end)
/
nullif(sum(case
  when stage in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  then amount
  else 0
end), 0)
```

Count win rate formula:

```sql
count(case
  when stage = 'Stage 5 - Closed Won'
  then deal_id
end)
/
nullif(count(case
  when stage in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  then deal_id
end), 0)
```

Default metric:

Use revenue win rate unless the analysis explicitly asks for count win rate.

Alternative common SaaS definition:

Some sales teams use count win rate by default. If the user asks for "win rate by number of deals" or "logo win rate", use count win rate.

Example interpretation:

Win Rate for Q3 means closed-won amount divided by all closed deal amount for deals with `close_date` in Q3.

## Supporting Metrics

### Closed Lost Amount

Definition: Total value of closed-lost deals based on close date.

Formula:

```sql
sum(case
  when stage = 'Stage 5 - Closed Lost'
  then amount
  else 0
end)
```

### Closed Won Count

Definition: Count of closed-won deals based on close date.

Formula:

```sql
count(case
  when stage = 'Stage 5 - Closed Won'
  then deal_id
end)
```

### Open Deal Count

Definition: Count of open deals based on close date.

Formula:

```sql
count(case
  when stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  then deal_id
end)
```

### Average Deal Size

Definition: Average value of deals.

Formula:

```sql
avg(amount)
```

Common variants:

- Average closed-won deal size
- Average open pipeline deal size
- Average new logo deal size
- Average upsell deal size

### Pipeline Coverage

Definition: Open pipeline divided by target or quota for the same close-date period.

Formula:

```sql
open_pipeline / nullif(quota, 0)
```

Notes:

- Prefer the `targets` table: it holds an explicit `target_amount` per `user_id` and period.
  Join on `targets.user_id = deals.owner_id` and filter `targets.period_type = 'quarter'`
  with the period containing the close date.
- Use `users.quota_annual` only for annual quota reporting when no `targets` row applies.

### Sales Cycle Length

Definition: Number of days between deal creation and close.

Formula:

```sql
date_diff('day', created_date, close_date)
```

Recommended filter:

- Use closed-won deals by default.
- Use closed-won and closed-lost deals only when the user asks for all completed sales cycles.

### Bookings YTD

Definition: Total closed-won bookings from the start of the current year through the reporting date.

Date basis: `deals.close_date`

Formula:

```sql
sum(case
  when stage = 'Stage 5 - Closed Won'
   and close_date between '2026-01-01' and '2026-08-13'
  then amount
  else 0
end)
```

### Current Quarter Open Pipeline

Definition: Stage 1 pipeline deal value expected to close in the current calendar quarter.

Date basis: `deals.close_date`

Formula:

```sql
sum(case
  when stage = 'Stage 1 - Discovery'
   and close_date between '2026-07-01' and '2026-09-30'
  then amount
  else 0
end)
```

### Next Best Action

Definition: Recommended action for an account based on active high-priority signals, open pipeline, buyer role, sentiment, and upcoming meetings.

Default logic:

- Prioritize signals where `signals.score >= 75`.
- Join signals to accounts and Stage 1 pipeline deals.
- Prefer accounts with Stage 1 pipeline deals.
- Include `signals.action_recommended` as the action.
- Add contact context when `signals.contact_id` maps to a real `contacts.contact_id`.
- Include meeting context when a scheduled meeting exists in the next 30 days.

### Account Engagement

Definition: Count of emails and completed meetings for an account during a period.

Formula concept:

```sql
email_count + completed_meeting_count
```

Notes:

- Emails use `emails.sent_at`.
- Meetings use `meetings.scheduled_start`.
- Completed meetings should filter `meetings.status = 'Completed'`.

### Average Sentiment

Definition: Average email sentiment score during a period.

Formula:

```sql
avg(sentiment_score)
```

Recommended dimensions:

- Account
- Contact
- Direction
- Deal owner
- Time period

### High-Priority Signals

Definition: Count of signals with strong action priority.

Default threshold:

```sql
score >= 80
```

Formula:

```sql
count(case
  when score >= 80
  then signal_id
end)
```

## Default Dimensions

Deal dimensions:

- `deal_type`
- `stage`
- `owner_id`
- `account_id`
- `close_date`
- `created_date`

Account dimensions:

- `industry`
- `tier`
- `status`
- `employee_count`
- `arr`

User dimensions:

- `role`
- `department`
- `quota_annual`

Contact dimensions:

- `persona_role`
- `is_champion`
- `title`

Signal dimensions:

- `signal_type`
- `score`
- `detected_at`

Activity dimensions:

- `direction`
- `sentiment_score`
- `meeting status`

## Metric Rules

- Always state the date basis for revenue metrics.
- Use `close_date` for Bookings, Open Pipeline, Bookings YTD, and Win Rate.
- Use `created_date` for Pipeline Generation. Pipeline Generation questions are always created-date cohorts.
- Default Win Rate is revenue-weighted, not count-based.
- Exclude open deals from Win Rate denominator.
- Include only closed-won deals in Bookings.
- Include every non-closed stage in Open Pipeline (Stage 1 through Stage 4).
- Use `Stage 1 - Discovery` alone only when the user explicitly asks for early-stage or Discovery pipeline.
- Keep prospect ARR as `0`; ARR should not be confused with deal `amount`.
- Treat `amount` as opportunity value.
- Treat `arr` as current customer account ARR.

## Example Business Questions

Bookings:

- How much revenue did we close this quarter?
- Which owners drove the most closed-won bookings?
- What industries produced the most bookings?

Open Pipeline:

- How much pipeline is expected to close this quarter?
- Which accounts have the largest open opportunities?
- How much open pipeline exists by stage?

Pipeline Generation:

- How much new pipeline did we create this month?
- Which owners or account tiers created the most pipeline?
- Are we creating enough pipeline for future quarters?

Win Rate:

- What percentage of closed deal value did we win this quarter?
- Is win rate higher for Tier 1 accounts?
- Do champion-backed deals convert better?

Signals:

- Which accounts have high-priority signals?
- Are intent spikes leading to pipeline creation?
- Which signal types are most associated with closed-won deals?
