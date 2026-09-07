# Golden expansion prompt — neonatal (batch 2/2)

Expected records: 4

## System

You are an expert author of bilingual golden evaluation records for a community health worker (CHW/SK) RAG coaching chatbot in Bangladesh.

Write scenario-based questions that sound like real field workers asking for guidance during home visits or clinic sessions.

Rules:
- Ground every expected answer ONLY in the provided MODULE CORPUS cards.
- Use exact module_id and source_card_id UUIDs from the corpus — never invent IDs.
- Provide both English (question_en, expected_answer_en) and Bengali (question_bn, expected_answer_bn).
- Match the tone, depth, and structure of the FEW-SHOT EXAMPLES.
- Vary query_type across the generation plan (Factual, Situational, Scenario-based, Procedural, Referral Decision, Cross-card Synthesis, Counseling, Drug / Dosage).
- Pick chw_pattern from the allowed taxonomy list.
- Set answerable to "yes", confidence to "high" unless the question is intentionally ambiguous.
- Return a single JSON object with key "records" (array). No markdown fences.


## Human

DOMAIN: neonatal
Generate exactly 4 new golden records distributed per the generation plan.

## FEW-SHOT EXAMPLES
[
  {
    "question_en": "What advice should be given for the newborn in postnatal care (PNC)?",
    "expected_answer_en": "Exclusive breastfeeding for 6 months, apply chlorhexidine to the navel, no bath for the first 3 days after birth, no haircut for 1 month, wash hands before handling, vaccinations on time, and advise on Kangaroo Mother Care.",
    "question_bn": "প্রসব পরবর্তী সেবায় (PNC) তে নবজাতকের জন্য কি কি পরামর্শ দিতে হবে?",
    "expected_answer_bn": "৬ মাস পর্যন্ত শুধুমাত্র বুকের দুধ খাওয়াতে হবে, নাভীতে ক্লোরোহেক্সিডিন ব্যবহার করতে হবে, জন্মের পর ৩ দিন গোসল না করানো, ১ মাস চুল না কাটা, হাত ধোয়ার অভ্যাস করা, সময়মতো টিকা দেওয়া এবং ক্যাঙ্গারু মাদার কেয়ার সম্পর্কে পরামর্শ দিতে হবে।",
    "source_card_id": [
      "a05420f1-e40e-4d86-a4ed-9a0ccf6758fb",
      "2744ec06-2aee-49ce-a763-d76b0466626d",
      "bafddfcf-e4d4-449e-8a96-083459245c98",
      "d1cb2b4d-b278-43a9-aea8-c716bcf1a017",
      "f532e43c-b3fa-4893-a013-fbab3409f373",
      "bfcf4b47-8c14-4ff9-a688-4733b9ef731f"
    ],
    "query_type": "Procedural",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Newborn Care Counseling",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "bb5fb8d0-56ec-4134-b9ba-35317227e91b",
      "ef6d104b-161b-491f-b853-b772ffaf97a4"
    ]
  },
  {
    "question_en": "What are the danger signs for a newborn and when should they be referred?",
    "expected_answer_en": "Poor breastfeeding, lethargy, respiratory distress, seizures, abnormal fever or hypothermia, pus in eyes, redness around the navel, jaundice within 24 hours of birth, or more than 10 pus-filled spots on skin—refer immediately if any of these occur.",
    "question_bn": "নবজাতকের বিপদজনক লক্ষণ গুলো কি কি এবং কখন রেফার করতে হবে?",
    "expected_answer_bn": "বুকের দুধ কম টানা, নিস্তেজ ভাব, শ্বাসকষ্ট, খিঁচুনি, অস্বাভাবিক জ্বর বা শরীরের তাপমাত্রা কমে যাওয়া, চোখে পুঁজ পড়া, নাভির চারপাশ লাল হওয়া, জন্মের ২৪ ঘন্টার মধ্যে জন্ডিস, বা ত্বকে ১০টির বেশি পুঁজবটি দেখা দিলে দ্রুত রেফার করতে হবে।",
    "source_card_id": [
      "df8b88bd-d1dd-4c5c-844d-d52a0aa4ce18",
      "f532e43c-b3fa-4893-a013-fbab3409f373",
      "e0ecece8-56ae-43be-8e93-19c0c03118fb"
    ],
    "query_type": "Factual",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Danger Signs & Referral Criteria",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "6fa7a48b-fce5-48f6-8eaa-afbb56438bf6",
      "bb5fb8d0-56ec-4134-b9ba-35317227e91b",
      "ef6d104b-161b-491f-b853-b772ffaf97a4"
    ]
  },
  {
    "question_en": "It has been 2 weeks since the birth. The baby's umbilical cord has not dried yet. As a health worker, what should I do?",
    "expected_answer_en": "The cord not drying or falling off can be a cause for concern. Check for signs of infection and refer the baby to the nearest hospital or Upazila Health Complex for evaluation.",
    "question_bn": "প্রসবের ২ সপ্তাহ হয়ে গিয়েছে। এখনো বাচ্চার নাভি শুকায় নি। একজন স্বাস্থ্যকর্মী হিসেবে আমার কি করনীয়?",
    "expected_answer_bn": "নাভি না শুকানো বা নাভি না পড়া উদ্বেগের বিষয় হতে পারে। সংক্রমণের লক্ষণ আছে কি না যাচাই করুন এবং শিশুটিকে মূল্যায়নের জন্য নিকটস্থ হাসপাতালে বা উপজেলা স্বাস্থ্য কেন্দ্রে রেফার করুন।",
    "source_card_id": [
      "bfcf4b47-8c14-4ff9-a688-4733b9ef731f",
      "df8b88bd-d1dd-4c5c-844d-d52a0aa4ce18",
      "267c0c6a-357b-447b-8b6e-04884814670d",
      "e0ecece8-56ae-43be-8e93-19c0c03118fb"
    ],
    "query_type": "Scenario-based",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Problem Identification & Escalation",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "0d157214-3387-49a6-abb3-06bc7e42a6aa",
      "6fa7a48b-fce5-48f6-8eaa-afbb56438bf6",
      "ef6d104b-161b-491f-b853-b772ffaf97a4"
    ]
  }
]

## GENERATION PLAN
[
  {
    "module_id": "bb5fb8d0-56ec-4134-b9ba-35317227e91b",
    "module_title": "নবজাতকের পরীক্ষা-নিরীক্ষা",
    "record_count": 4,
    "suggested_query_types": [
      "Factual",
      "Procedural",
      "Cross-card Synthesis",
      "Counseling"
    ],
    "card_ids": [
      "a0e5387f-fe69-49c6-86ee-da491a04b6ac",
      "a05420f1-e40e-4d86-a4ed-9a0ccf6758fb",
      "2744ec06-2aee-49ce-a763-d76b0466626d",
      "bafddfcf-e4d4-449e-8a96-083459245c98",
      "d1cb2b4d-b278-43a9-aea8-c716bcf1a017",
      "f532e43c-b3fa-4893-a013-fbab3409f373"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: নবজাতকের পরীক্ষা-নিরীক্ষা
module_id: bb5fb8d0-56ec-4134-b9ba-35317227e91b
cards: 6

### Card 1 (id: a0e5387f-fe69-49c6-86ee-da491a04b6ac)
Title (bn): নবজাতকের পরীক্ষা-নিরীক্ষা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'নবজাতকের জন্য ওজন, শ্বাসের গতি, সাইনোসিস (শরীরের রং নীলচে হওয়া), তাপমাত্রা, জন্ডিস, নাভী ও প্রস্রাব-পায়খানা পরীক্ষা করতে হয়।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration depicts a healthcare worker in a white coat and head covering examining the arm of a woman. Another woman stands nearby, holding a baby wrapped in a blue blanket. The background suggests an indoor setting with bamboo-like walls.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/317cd2f3383d5ca0a8a43f18a69212ed4f7676aa4ccc76aaf09540cc0a3f5507.jpg'}}]

### Card 2 (id: a05420f1-e40e-4d86-a4ed-9a0ccf6758fb)
Title (bn): নবজাতকের বুকের দুধ খাওয়ানো
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'জন্মের প্রথম তিন দিন পর্যন্ত শালদুধ খাওয়ানো নিশ্চিত করুন। মাকে বুকের দুধ খাওয়ানোর সঠিক পদ্ধতি শেখান। ছয় মাস পর্যন্ত শুধুমাত্র বুকের দুধ খাওয়ানো (দিনে দশ থেকে বারো বার) নিশ্চিত করুন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration shows a family scene with a new mother holding a baby, drinking water offered by a man, while an older woman sits beside her on a bed, talking. The man is seated on a stool next to the bed.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/bd0f447b3bbb0965814bd54eecb1c4b1cca4950ab430490bb5e1ba1988edd545.jpg'}}]

### Card 3 (id: 2744ec06-2aee-49ce-a763-d76b0466626d)
Title (bn): নবজাতকের নাভীর যত্ন
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'জন্মের পর নাভীতে 7.1% ক্লোরোহেক্সিডিন লাগানোর পর আর কিছু লাগানো যাবে না। নাভী সাত থেকে দশ দিনের মধ্যে শরীর থেকে পড়ে যাবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration shows a family scene with a new mother holding a baby, drinking water offered by a man, while an older woman sits beside her on a bed, talking. The man is seated on a stool next to the bed.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/bd0f447b3bbb0965814bd54eecb1c4b1cca4950ab430490bb5e1ba1988edd545.jpg'}}]

### Card 4 (id: bafddfcf-e4d4-449e-8a96-083459245c98)
Title (bn): নবজাতকের সাধারণ যত্ন
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'তিন দিন পর্যন্ত নবজাতককে গোসল করানো যাবে না এবং এক মাস পর্যন্ত চুল কাটা যাবে না। নবজাতককে ধরার আগে ও পরে সাবান দিয়ে ভালো করে হাত ধুতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration shows a family scene with a new mother holding a baby, drinking water offered by a man, while an older woman sits beside her on a bed, talking. The man is seated on a stool next to the bed.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/bd0f447b3bbb0965814bd54eecb1c4b1cca4950ab430490bb5e1ba1988edd545.jpg'}}]

### Card 5 (id: d1cb2b4d-b278-43a9-aea8-c716bcf1a017)
Title (bn): নবজাতকের টিকাকরণ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'জন্মের পর যত তাড়াতাড়ি সম্ভব বিসিজি টিকা দিতে হবে। দেড় মাস থেকে পনেরো থেকে আঠারো মাস পর্যন্ত মোট পাঁচ বার টিকা কেন্দ্রে যেতে হবে এবং দশটি রোগের টিকা নিতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration shows a family scene with a new mother holding a baby, drinking water offered by a man, while an older woman sits beside her on a bed, talking. The man is seated on a stool next to the bed.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/bd0f447b3bbb0965814bd54eecb1c4b1cca4950ab430490bb5e1ba1988edd545.jpg'}}]

### Card 6 (id: f532e43c-b3fa-4893-a013-fbab3409f373)
Title (bn): কম জন্ম ওজনের নবজাতকের যত্ন ও বিপদচিহ্ন
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'কম জন্ম ওজনের নবজাতকের জন্য বিশেষ যত্ন (ক্যাঙ্গারু মাদার কেয়ার) সম্পর্কে পরামর্শ দিতে হবে। নবজাতকের বিপদচিহ্ন দেখা দিলে সাথে সাথে হাসপাতালে বা উপজেলা স্বাস্থ্য কেন্দ্রে রেফার করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration shows a family scene with a new mother holding a baby, drinking water offered by a man, while an older woman sits beside her on a bed, talking. The man is seated on a stool next to the bed.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/bd0f447b3bbb0965814bd54eecb1c4b1cca4950ab430490bb5e1ba1988edd545.jpg'}}]


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
