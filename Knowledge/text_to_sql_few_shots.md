# Intellia Text-to-SQL Few-Shot Examples

## Purpose

Use these examples to guide natural-language analytics questions into SQL over the Intellia CSV tables.

Assumptions:

- Current date: `2026-08-13`
- Current quarter: Q3 2026, from `2026-07-01` to `2026-09-30`
- Current YTD period: `2026-01-01` to `2026-08-13`
- Open Pipeline uses every non-closed stage: `stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')`
- Bookings use closed-won deals and `close_date`
- Pipeline Generation uses `created_date`
- Default Win Rate is revenue-weighted unless the user asks for count or logo win rate

## Example 1: Current Quarter Open Pipeline by Rep

User prompt:

What is our total open pipeline closing this quarter by rep?

SQL:

```sql
select
  u.full_name as sales_rep,
  sum(d.amount) as open_pipeline
from deals d
join users u
  on d.owner_id = u.user_id
where d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  and d.close_date between '2026-07-01' and '2026-09-30'
group by u.full_name
order by open_pipeline desc;
```

## Example 2: Bookings YTD by Rep

User prompt:

Show bookings YTD by sales rep.

SQL:

```sql
select
  u.full_name as sales_rep,
  sum(d.amount) as bookings_ytd
from deals d
join users u
  on d.owner_id = u.user_id
where d.stage = 'Stage 5 - Closed Won'
  and d.close_date between '2026-01-01' and '2026-08-13'
group by u.full_name
order by bookings_ytd desc;
```

## Example 3: Bookings YTD vs Annual Quota Attainment

User prompt:

Show YTD bookings and annual quota attainment percentage for each AE.

SQL:

```sql
select
  u.full_name as sales_rep,
  u.role,
  u.quota_annual,
  coalesce(sum(d.amount), 0) as bookings_ytd,
  round(
    coalesce(sum(d.amount), 0) * 100.0 / nullif(u.quota_annual, 0),
    2
  ) as quota_attainment_pct
from users u
left join deals d
  on u.user_id = d.owner_id
  and d.stage = 'Stage 5 - Closed Won'
  and d.close_date between '2026-01-01' and '2026-08-13'
where u.role in ('AE', 'Senior AE')
group by u.user_id, u.full_name, u.role, u.quota_annual
order by quota_attainment_pct desc;
```

## Example 4: Revenue Win Rate by Deal Type

User prompt:

What is our win rate by deal type?

SQL:

```sql
select
  deal_type,
  sum(case when stage = 'Stage 5 - Closed Won' then amount else 0 end) as won_amount,
  sum(case when stage in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost') then amount else 0 end) as closed_amount,
  round(
    sum(case when stage = 'Stage 5 - Closed Won' then amount else 0 end) * 100.0
    / nullif(sum(case when stage in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost') then amount else 0 end), 0),
    2
  ) as revenue_win_rate_pct
from deals
where stage in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
group by deal_type
order by revenue_win_rate_pct desc;
```

## Example 5: Count Win Rate and Sales Cycle by Deal Type

User prompt:

What is our historical logo win rate and average sales cycle in days for New Logo vs Upsell deals?

SQL:

```sql
select
  deal_type,
  count(case when stage = 'Stage 5 - Closed Won' then deal_id end) as won_deals,
  count(case when stage in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost') then deal_id end) as closed_deals,
  round(
    count(case when stage = 'Stage 5 - Closed Won' then deal_id end) * 100.0
    / nullif(count(case when stage in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost') then deal_id end), 0),
    2
  ) as count_win_rate_pct,
  round(
    avg(case
      when stage = 'Stage 5 - Closed Won'
      then julianday(close_date) - julianday(created_date)
    end),
    1
  ) as avg_won_sales_cycle_days
from deals
where deal_type in ('New Logo', 'Upsell')
group by deal_type
order by deal_type;
```

## Example 6: Pipeline Generation by Month

User prompt:

How much pipeline did we generate each month this year?

SQL:

```sql
select
  strftime('%Y-%m', created_date) as created_month,
  sum(amount) as pipeline_generated
from deals
where created_date between '2026-01-01' and '2026-08-13'
group by strftime('%Y-%m', created_date)
order by created_month;
```

## Example 7: Pipeline Generation by Owner and Account Tier

User prompt:

Which reps generated the most Tier 1 pipeline this year?

SQL:

```sql
select
  u.full_name as sales_rep,
  a.tier,
  sum(d.amount) as pipeline_generated
from deals d
join users u
  on d.owner_id = u.user_id
join accounts a
  on d.account_id = a.account_id
where d.created_date between '2026-01-01' and '2026-08-13'
  and a.tier = 'Tier 1'
group by u.full_name, a.tier
order by pipeline_generated desc;
```

## Example 8: Open Pipeline by Stage

User prompt:

How much open pipeline do we have by stage for this quarter?

SQL:

```sql
select
  stage,
  count(deal_id) as open_deal_count,
  sum(amount) as open_pipeline
from deals
where stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  and close_date between '2026-07-01' and '2026-09-30'
group by stage
order by
  case stage
    when 'Stage 1 - Discovery' then 1
    else 99
  end;
```

## Example 9: Largest Open Pipeline Accounts

User prompt:

Which accounts have the largest open opportunities this quarter?

SQL:

```sql
select
  a.account_name,
  a.industry,
  a.tier,
  count(d.deal_id) as open_deal_count,
  sum(d.amount) as open_pipeline
from deals d
join accounts a
  on d.account_id = a.account_id
where d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  and d.close_date between '2026-07-01' and '2026-09-30'
group by a.account_id, a.account_name, a.industry, a.tier
order by open_pipeline desc;
```

## Example 10: High-Score Signals for Open Pipeline Accounts

User prompt:

What are the active high-intent or critical signals for open pipeline accounts and their recommended actions?

SQL:

```sql
select
  a.account_name,
  d.deal_name,
  d.amount as deal_value,
  d.stage,
  s.signal_type,
  s.signal_title,
  s.score as signal_score,
  s.action_recommended
from signals s
join accounts a
  on s.account_id = a.account_id
join deals d
  on a.account_id = d.account_id
where d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  and s.score >= 75
order by s.score desc, d.amount desc;
```

## Example 11: Next Best Action by Account

User prompt:

Give me next best actions for accounts with open pipeline this quarter.

SQL:

```sql
select
  a.account_name,
  d.deal_name,
  d.amount as open_pipeline,
  d.close_date,
  s.signal_type,
  s.signal_title,
  s.score,
  s.action_recommended as next_best_action
from deals d
join accounts a
  on d.account_id = a.account_id
left join signals s
  on a.account_id = s.account_id
where d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  and d.close_date between '2026-07-01' and '2026-09-30'
  and (s.score >= 75 or s.score is null)
order by s.score desc, d.amount desc;
```

## Example 12: Champion-Backed Open Pipeline

User prompt:

How much open pipeline has a champion attached?

SQL:

```sql
with deal_champion_status as (
  select
    d.deal_id,
    d.amount,
    case
      when count(distinct case when c.is_champion = true then c.contact_id end) > 0
      then 'Champion Attached'
      else 'No Champion'
    end as champion_status
  from deals d
  left join contacts c
    on d.account_id = c.account_id
  where d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
  group by d.deal_id, d.amount
)
select
  champion_status,
  count(deal_id) as open_deal_count,
  sum(amount) as open_pipeline
from deal_champion_status
group by champion_status
order by open_pipeline desc;
```

Alternative account-level version:

```sql
select
  a.account_name,
  sum(distinct d.amount) as open_pipeline,
  count(distinct c.contact_id) as champion_count
from deals d
join accounts a
  on d.account_id = a.account_id
left join contacts c
  on d.account_id = c.account_id
  and c.is_champion = true
where d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
group by a.account_id, a.account_name
having count(distinct c.contact_id) > 0
order by open_pipeline desc;
```

## Example 13: Negative Sentiment on Open Deals

User prompt:

Which open pipeline accounts have negative email sentiment?

SQL:

```sql
select
  a.account_name,
  d.deal_name,
  d.amount,
  avg(e.sentiment_score) as avg_sentiment,
  count(e.email_id) as email_count
from deals d
join accounts a
  on d.account_id = a.account_id
join emails e
  on d.account_id = e.account_id
where d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
group by a.account_id, a.account_name, d.deal_id, d.deal_name, d.amount
having avg(e.sentiment_score) < 0
order by avg_sentiment asc;
```

## Example 14: Upcoming Meetings for Open Pipeline

User prompt:

What upcoming meetings do we have for open pipeline accounts?

SQL:

```sql
select
  a.account_name,
  d.deal_name,
  d.amount,
  m.title as meeting_title,
  m.scheduled_start,
  m.agenda,
  u.full_name as organizer
from meetings m
join accounts a
  on m.account_id = a.account_id
join deals d
  on a.account_id = d.account_id
join users u
  on m.organizer_id = u.user_id
where m.status = 'Scheduled'
  and m.scheduled_start >= '2026-08-13'
  and d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
order by m.scheduled_start asc;
```

## Example 15: Accounts with Intent Signals but No Open Pipeline

User prompt:

Which accounts have intent signals but no open pipeline?

SQL:

```sql
select
  a.account_name,
  a.status,
  s.signal_title,
  s.score,
  s.detected_at,
  s.action_recommended
from signals s
join accounts a
  on s.account_id = a.account_id
left join deals d
  on a.account_id = d.account_id
  and d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
where s.signal_type = 'Intent Score'
  and d.deal_id is null
order by s.score desc;
```

## Example 16: Stage Conversion Counts

User prompt:

Show me the deal funnel by stage.

SQL:

```sql
select
  stage,
  count(deal_id) as deal_count,
  sum(amount) as total_amount
from deals
group by stage
order by
  case stage
    when 'Stage 1 - Discovery' then 1
    when 'Stage 2 - Qualification' then 2
    when 'Stage 3 - Evaluation' then 3
    when 'Stage 4 - Proposal' then 4
    when 'Stage 5 - Closed Won' then 5
    when 'Stage 5 - Closed Lost' then 6
    else 99
  end;
```

## Example 17: Closed-Won Bookings by Industry

User prompt:

Which industries produced the most bookings this year?

SQL:

```sql
select
  a.industry,
  sum(d.amount) as bookings_ytd
from deals d
join accounts a
  on d.account_id = a.account_id
where d.stage = 'Stage 5 - Closed Won'
  and d.close_date between '2026-01-01' and '2026-08-13'
group by a.industry
order by bookings_ytd desc;
```

## Example 18: Renewal or Upsell Pipeline from Customers

User prompt:

How much expansion pipeline do we have from current customers?

SQL:

```sql
select
  a.account_name,
  d.deal_type,
  sum(d.amount) as expansion_pipeline
from deals d
join accounts a
  on d.account_id = a.account_id
where a.status = 'Customer'
  and d.deal_type in ('Upsell', 'Renewal')
  and d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
group by a.account_id, a.account_name, d.deal_type
order by expansion_pipeline desc;
```

## Example 19: Deal Risk from Negative Sentiment and Weak Champion Coverage

User prompt:

Which open deals look risky based on sentiment and lack of champion?

SQL:

```sql
select
  a.account_name,
  d.deal_name,
  d.amount,
  d.close_date,
  avg(e.sentiment_score) as avg_sentiment,
  count(distinct case when c.is_champion = true then c.contact_id end) as champion_count
from deals d
join accounts a
  on d.account_id = a.account_id
left join emails e
  on d.account_id = e.account_id
left join contacts c
  on d.account_id = c.account_id
where d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
group by a.account_id, a.account_name, d.deal_id, d.deal_name, d.amount, d.close_date
having avg(e.sentiment_score) < 0
   or count(distinct case when c.is_champion = true then c.contact_id end) = 0
order by d.close_date asc, d.amount desc;
```

## Example 20: Account 360 Summary

User prompt:

Give me an account summary for Apex Logistics.

SQL:

```sql
select
  a.account_name,
  a.industry,
  a.tier,
  a.status,
  a.arr,
  count(distinct c.contact_id) as contact_count,
  count(distinct case when c.is_champion = true then c.contact_id end) as champion_count,
  count(distinct d.deal_id) as deal_count,
  sum(case
    when d.stage not in ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
    then d.amount else 0
  end) as open_pipeline,
  count(distinct s.signal_id) as signal_count,
  max(s.detected_at) as latest_signal_at
from accounts a
left join contacts c
  on a.account_id = c.account_id
left join deals d
  on a.account_id = d.account_id
left join signals s
  on a.account_id = s.account_id
where lower(a.account_name) = lower('Apex Logistics')
group by a.account_id, a.account_name, a.industry, a.tier, a.status, a.arr;
```

## SQL Generation Rules

- Use explicit date ranges instead of vague relative dates.
- Use `close_date` for bookings, open pipeline, win rate, and sales-cycle cohorts.
- Use `created_date` for pipeline generation. Pipeline Generation questions are always created-date cohorts.
- Use every non-closed stage for Open Pipeline by default. Use `Stage 1 - Discovery` alone only when the user asks for early-stage or Discovery pipeline.
- Use closed-won and closed-lost deals only for Win Rate denominators.
- Use revenue win rate by default.
- Use count win rate when the user says logo win rate, deal count win rate, or by number of deals.
- Join `deals.owner_id` to `users.user_id` for rep-level reporting.
- Join through `accounts.account_id` for industry, tier, customer/prospect status, contacts, meetings, emails, and signals.
- Avoid summing deal amount after joining to contacts or emails unless grouping at deal level or using a de-duplicated deal subquery.
