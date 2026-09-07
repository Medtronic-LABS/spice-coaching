"""Shared behavioural-topic module definition used by identify and merge."""

MODULE_TOPIC_DEFINITION = """\
A module covers ONE actionable behavioural topic the CHW must internalise correctly. Examples:
- "Correct ANC referral by risk category"
- "Recognising postpartum danger signs"
- "Hypertension identification and management" (when the source has a dedicated HTN chapter)
- "Dengue fever recognition, prevention, and referral"
- "Effective communication and counselling skills" (when the source has a dedicated chapter)
- "BRAC field activities and follow-up workflow" (when the source has an operational chapter)
- "SPICE form submission failure recovery"

GROUPING RULES — do NOT over-fragment, do NOT under-emit:

1. Do NOT create modules per individual test, vital sign, lab value, or
   measurement threshold (e.g. don't make separate modules for "BP measurement",
   "Hb measurement", "blood-glucose threshold"). Group related measurements
   into a parent procedural unit (e.g. "Performing antenatal physical and
   pathological examinations").

2. DO create a standalone module per NAMED DISEASE or DEDICATED CHAPTER
   the source treats as its own learning unit. If the source corpus has a
   chapter on Hypertension, Diabetes, Tuberculosis, Malaria, Cancer, Dengue,
   Diarrhoea, ARI/Pneumonia, etc., emit a dedicated module for it — even
   when the chapter overlaps with an adjacent screening or measurement
   chapter. The CHW's ongoing-management knowledge for the disease is
   distinct from the one-shot screening procedure.

3. DO create a module for non-clinical CHW skill chapters: communication,
   counselling skills, field activities, reporting workflow, safeguarding.
   These are CHW practice topics even though they are not disease-management.
   Don't deprioritise them just because they aren't clinical.

4. DO NOT propose modules from annexures, appendices, or reference
   sections. Forms, checklists, reporting templates, consent forms, and
   reference tables (e.g. "Healthcare Services by Facility Level") are
   JOB AIDS — the CHW fills them out or looks at them on the job, not
   topics they internalise through training. Detection cues:
   - Page or section heading begins with {annexure_terms}
     or similar.
   - Content is dominated by blank fields, tick-box rows, signature
     lines, or columnar reference data the user fills in or looks up.
   The training-content equivalent (e.g. "How to fill the NCD reporting
   form" as a procedural lesson) IS a valid module — the line is between
   the form itself (job aid) and the procedure of using it (trainable).

DO NOT invent topics. Only group and label content present in the source corpus.
"""
