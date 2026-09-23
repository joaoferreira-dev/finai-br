# Missing scheduled analysis on September 22, 2026

## Production evidence

Read-only investigation of `finai-prod-vm`, project `testing-gcp-resources`,
zone `us-central1-a`, around 21:08 BRT on September 22:

- Application image: `sha-7bdeb0f5f695f2767862a0e3630bd3db4b9de890`.
- Container started at `2026-09-22T11:26:51Z` (08:26 BRT), with zero restarts
  and `OOMKilled=false`. The scheduler started at 08:27 BRT.
- At `2026-09-22T21:00:01.748742036Z` (18:00 BRT), APScheduler logged
  `run_daily_cycle` as missed by `0:00:01.530672`. No cycle start followed.
- Deployed APScheduler version: 3.10.4. Its actual default job settings were
  `misfire_grace_time=1`, `coalesce=True`, and `max_instances=1`.
- Deployed collection registration did not override the one-second allowance;
  email registration explicitly allowed 300 seconds.
- Database aggregate query found no September 22 analyses. September 21 had
  five analyses created between `18:00:35Z` and `18:01:35Z` (15:00–15:01 BRT).
- At inspection, the host had 508 MiB available memory, 178 MiB swap usage,
  21% root disk usage, and a one-minute load average of 0.08. These are current
  observations; they do not establish resource conditions at 18:00.

No environment files or credential values were retrieved.

## Diagnosis

September 22 is a confirmed scheduler misfire. The executor rejected a job
that was 1.53 seconds late because its allowance was only one second. This
check happens before invoking application collection, LLM calls, or database
writes. The immediate skip is explained; the underlying cause of the small
host/executor delay is not established by the available evidence.

The earlier timing issue is different. Before commit `6bd9c20`, cron trigger
instances omitted their timezone even though the scheduler had a São Paulo
timezone. An already constructed trigger retains its own timezone. Yesterday's
15:00 BRT writes are consistent with the old 18:00 UTC trigger. Historical
container logs from before today's container replacement were not available
in the current container, so this is supported by code history and database
timestamps rather than a retained September 21 scheduler log.

Commit `6bd9c20` deployed explicit São Paulo cron timezones this morning, but
increased the delay allowance only for email. This left collection exposed
to the one-second default.

References for the deployed library version:

- [APScheduler 3.10.4 scheduler defaults](https://github.com/agronholm/apscheduler/blob/3.10.4/apscheduler/schedulers/base.py)
- [APScheduler 3.10.4 executor skip logic](https://github.com/agronholm/apscheduler/blob/3.10.4/apscheduler/executors/base.py)
- [APScheduler 3.x missed execution guidance](https://apscheduler.readthedocs.io/en/3.x/userguide.html#missed-job-executions-and-coalescing)

## Prepared fix

`create_scheduler()` applies a shared 300-second allowance to both jobs,
explicitly retains coalescing and one concurrent execution per job, and keeps
the existing weekday São Paulo cron triggers. A five-minute window tolerates
brief host delays without allowing arbitrarily late execution.

The application now logs missed executions and concurrency skips as errors,
including the scheduled local timestamp for a misfire. Startup logs expose
the configured timezone and delay allowance.

Regression tests use the real APScheduler executor with a controlled clock
and mocked application callbacks. They cover the observed 1.530672-second
delay, a 299-second delay, rejection at 301 seconds, missed-run logging,
concurrency-skip logging, and both jobs' weekday São Paulo schedules.

## Production recovery and limits

The prepared source change must be deployed through the normal image and
deployment workflow before it affects production. Confirm the deployed
startup logs show `tolerância=300s` for both jobs.

Then run one collection cycle using `python -m main run` in the application
container and check persisted analysis dates and per-ticker completion logs.
This runs collection and analysis without sending an email. A successful
process exit alone is insufficient: the current collection loop catches
individual ticker failures, so verify that each expected ticker was persisted.

Do not treat this as historical backfill: the current ingestion path fetches
current market data and the previous 24 hours of news. A delayed recovery may
not recreate the exact inputs available on September 22.

The scheduler uses an in-memory job store. This change handles short delays
while the process is alive; it does not replay jobs missed while the container
was stopped or runs already discarded before deployment. Durable restart
catch-up and external alerting would require separate work. Those limitations
did not cause the observed September 22 skip.
