# MicroCoaching

MicroCoaching delivers AI-assisted health coaching to community health workers (CHWs). It uses AI in the following manner:

1. **Learning Module Creation:** Help administrators to create [micro learning modules](GLOSSARY.md#micro-learning-module) out of the raw training materials.
2. **AI Assistant:** Help the Community Health Workers to ask questions from within the above learning modules which can assist them during the day to day activities

The documentation goes over the technical implementation details by going over the corresponding product flow.

## System lifecycle and integration flow

1. **Content creation:** An admin creates coaching modules by uploading [source documents](concepts/source-documents.md) (PDF, PPTX, DOCX, audio, video) through the [ingest pipeline](content-administration/ingest-pipeline.md) or by [authoring them manually](content-administration/edit-and-publish.md).
2. **Review and publish:** An admin [reviews the drafted modules](content-administration/review-merges.md) and [publishes them](content-administration/edit-and-publish.md) for training and they become answerable through the AI Assistant.
3. **Assignment:** Admins [assign published modules and knowledge documents](content-administration/assign-content.md) to hierarchy users or geographical units, this allows the Community Health Workers to go through the learning module and learn the content.
4. **Offline synchronization:** The Android SDK [syncs published content](device-coaching/sync-content.md) via `/sync/*` and operates offline.
5. **Learning interactions:** The CHW reads cards and completes quizzes for assigned modules directly on the device. See [Device coaching](device-coaching/README.md).
6. **AI assistance:** The CHW queries module content through the [AI coaching chatbot](device-coaching/coaching-chat.md) (cloud or on-device [EDGE mode](GLOSSARY.md#edge-mode)).
7. **Telemetry and reinforcement:** CHW interactions emit [telemetry](device-coaching/send-telemetry.md) events via `POST /telemetry/events`, updating [behavioural gap](GLOSSARY.md#behavioural-gap) states, driving [morning review](device-coaching/morning-review.md) recommendations in the form of learning quizzes which should be reviewed.
8. **Dashboard insights:** A [Program Organizer](GLOSSARY.md#program-organizer) and an [Area Manager or Admin](GLOSSARY.md#area-manager) monitor [team activity](supervision/team-activity.md), [digital-help demand](supervision/digital-help-demand.md), and [module creation suggestions](supervision/module-creation-suggestions.md) on the [dashboard](supervision/README.md).

## Distinctive behaviour

- The SDK supports offline functionality and thus maintains the state for a user within the device (this state is also maintained within the backend so it can be synced if the local state is deleted).
- The micro coaching is locale agnostic and we can generate content specific to a [particular locale](administration/language-and-locales.md).
- While creating module through the ingestion, we check the current catalog of modules within the "Draft" and "Published" statuses for the similar module and requires review from the user whether to [merge or keep the newly generated modules](content-administration/review-merges.md).
- AI Assistant can run in the cloud (Online) or in [EDGE mode](GLOSSARY.md#edge-mode) (Offline) on the device.
- The refreshers shown to a CHW on the application are based upon his performance over the learning modules.
- In the implementation, we also have provision for refreshers to be based upon the upcoming vists of the CHW and his referral history but this is not activated by default and some sanity work has to be done to ensure its correctness.

## Next step

[Getting started](getting-started/README.md)
