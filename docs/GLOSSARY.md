# Glossary

## MicroCoaching

This product. It delivers AI-assisted health coaching to community health workers.

## Micro Learning Module

A learning entity consisting of byte sized content within the cards and accompanying quizzes.

## CHW

Community health worker. The device user. The hierarchy role is `SHASTIYA_KORMI`. Do not write “field user”.

## Program Organizer

Supervisor of community health workers. The hierarchy role is `PO`.

## Area Manager

Content and program lead. The hierarchy role is `AREA_MANAGER`. This role uses admin routes and dashboard routes.

## Super Admin

Hierarchy administrator. The hierarchy role is `SUPER_ADMIN`. This role is not a device user. Do not write “platform admin”. SPICE principals with `SUPER_USER` or `JOB_USER` bypass hierarchy binding; that is not the Super Admin role.

## SPICE

Host product. SPICE authenticates users and embeds the Android SDK.

## tenant

SPICE country tenant. Platform stores it as `tenant_id` (`BIGINT`). Content, hierarchy, and sync stay inside one tenant. The **selected tenant** on a request is the tenant middleware resolves for that call.

## module

One coaching topic. Cards and quizzes belong to one module row.

## module family

Stable identity across module content versions. Each saved content change creates a new module row in the same family.

## tip

The latest module row in a module family. Prefer “latest module row in the family” in procedures. Use `tip` only when matching admin UI copy.

## card

One screen of a module. Cards live as relational rows. Cross-module card reuse is not a concept.

## source document

An uploaded PDF, PPTX, DOCX, audio file, or video file. A source document can feed ingest, or it can sync as a knowledge library file.

## assignment

A grant of a published module or a source document to a hierarchy user or to a geography.

## dual-path merge

Review copies that ingest writes when new content matches a similar published module. The reviewer chooses **override** (keep LLM-merged cards) or **split** (keep the new-document cards only).

## content domain

Ingest and module field `content_domain`. Allowed values: `clinical`, `digital`, `operational`. Default is `clinical`.

## platform-api

Public HTTP service. Devices and admin clients call this service. Compose service name: `platform-api`.

## platform-worker

Celery worker process. It runs ingest jobs and background jobs. Compose service name: `platform-celery-worker`. Prefer the Compose name in setup and logs.

## platform-celery-beat

Celery Beat process. It runs scheduled jobs. Compose service name: `platform-celery-beat`.

## ai-runtime

Private inference service. It runs generation, embedding, and transcription. Devices do not call ai-runtime.

## EDGE mode

On-device chat. The SDK embeds the question locally and generates an answer over synced card embeddings. Telemetry may record `inference_mode: edge`.

## Morning review

Device surface fed by `GET /morning/cards`. Do not write “morning-brief”.

## behavioural gap

A coaching gap that the device evaluates from SPICE referral and assessment context. Platform syncs gap definitions and CHW gap state. The detection rule is the JSON operator tree on the gap.

## assessment-due trigger

A workflow trigger that matches due patients or follow-up rows to coaching modules. The device evaluates the **assessment-due predicate** after sync.

## ingest

The pipeline that turns source documents into module drafts, then into published coaching content.

## ingest batch

One admin ingest request. It contains one **ingestion run** per source document.

## ingestion run

One pipeline execution per source document in an ingest batch. Admins poll stage progress on the run. Dual-path review pairs appear after the `card_draft` stage finishes.

## telemetry

Observation events that the SDK sends to platform-api. The backend writes analytics and updates operational state.

## locale-keyed content

Text stored as a map from locale code to string, for example `{"bn": "..."}`. The deployment primary locale is required for CHW-facing content.

## knowledge library

Source documents that sync to devices without a full module ingest. These rows have `sync_published_visible=true`.

## module embedding store

Platform embedding upsert and search. The default adapter is pgvector on `module.embedding`.

## Problem Details

RFC 7807 error body. `type` is `docs/error-codes.json#{code}`. Clients map `code` to user-facing copy.

## performance status

Dashboard field `performance_status`. Values are `on_track` or `at_risk`. For a CHW, on track means at least 60% of assigned modules in the date window have a responsive event (`module_card_viewed`, `module_quiz_viewed`, or `module_quiz_attempted`). Program Organizer and Area Manager status rolls up from descendant CHWs with the same 60% share rule.
