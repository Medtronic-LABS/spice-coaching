# Seed data

Files in this directory are optional content dumps. They are **not**
applied automatically by `alembic upgrade head` — load them manually
when needed.

## Files

### `behavioural_gaps_pilot.json`

Pilot-program list of behavioural gaps. Imported by an admin endpoint
or a one-off script; safe to redistribute.

### `platform_models_module_data.sql`

2146-row pg_dump of BRAC / UHIS training content used during pilot
development. **Legal status: unconfirmed.** This content was prepared
by partner organisations and the redistribution licence has not been
agreed in writing as of this commit. Do NOT load this into a public
deployment, and do NOT publish it as part of an OSS release artifact,
without first confirming you have the right to redistribute it.

To load locally after confirming you have the right to use it:

```bash
psql "$DATABASE_URL" -f seed/platform_models_module_data.sql
```

The migration that previously loaded this file
(`infra/alembic/versions/0002_platform_models_module_data.py`) is now a
no-op for the same reason.
