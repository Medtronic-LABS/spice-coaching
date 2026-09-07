# Golden expansion prompt — immunisation (batch 0/0)

Expected records: 3

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

DOMAIN: immunisation
Generate exactly 3 new golden records distributed per the generation plan.

## FEW-SHOT EXAMPLES
[
  {
    "question_en": "The EPI card does not have IPV-2 information, but the mother says the child was vaccinated. What should I do in this situation?",
    "expected_answer_en": "Do not rely solely on verbal information. Re-verify the EPI card and confirm with the respective Health Assistant. Do not guess information until confirmed.",
    "question_bn": "EPI কার্ডে IPV-2-এর তথ্য লেখা নেই, কিন্তু মা বলছেন শিশুকে টিকা দেওয়া হয়েছে। এ অবস্থায় আমি কী করব?",
    "expected_answer_bn": "শুধুমাত্র মৌখিক তথ্যের ওপর ভিত্তি করবেন না। EPI কার্ড পুনরায় যাচাই করুন এবং সংশ্লিষ্ট হেলথ অ্যাসিস্ট্যান্টের সাথে নিশ্চিত করুন। নিশ্চিত না হওয়া পর্যন্ত তথ্য অনুমান করবেন না।",
    "source_card_id": [
      "c5a75002-e4b6-46e3-ad4a-3fc55d3b3921",
      "44051a6f-21c2-434f-996e-4c5fbc5992d6"
    ],
    "query_type": "Scenario-based",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Documentation Verification & Coordination",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "065e5a37-6dcf-4fe4-9450-b05176ad13ac"
    ]
  },
  {
    "question_en": "The child missed IPV-2. Does the child need to restart all doses, or just get the missed dose?",
    "expected_answer_en": "There is no need to restart the entire schedule. Just give the missed IPV-2 dose as soon as possible. Consult the Health Assistant for final decisions.",
    "question_bn": "শিশুটিকে IPV-2 মিস করেছে। এখন কি তাকে প্রথম থেকে আবার সব ডোজ দিতে হবে, নাকি শুধু মিসড ডোজটাই দিলে হবে?",
    "expected_answer_bn": "পুরো শিডিউল পুনরায় শুরু করার প্রয়োজন নেই। শুধুমাত্র মিসড IPV-2 ডোজটি যত দ্রুত সম্ভব দিতে হবে। চূড়ান্ত সিদ্ধান্তের জন্য হেলথ অ্যাসিস্ট্যান্টের পরামর্শ নিন।",
    "source_card_id": [
      "44051a6f-21c2-434f-996e-4c5fbc5992d6",
      "c5a75002-e4b6-46e3-ad4a-3fc55d3b3921"
    ],
    "query_type": "Procedural",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Immunization Catch-up Rule",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "065e5a37-6dcf-4fe4-9450-b05176ad13ac"
    ]
  },
  {
    "question_en": "It was discovered from the EPI card that a child missed a scheduled vaccine. As an SK, how will you enlist the child as a 'missed vaccination child'?",
    "expected_answer_en": "Include the child's information in the 'missed vaccination child' list/form according to the prescribed method and provide this information to the respective Health Assistant, also informing them verbally if necessary.",
    "question_bn": "একজন শিশুর নির্ধারিত সময়ের একটি টিকা দেওয়া হয়নি বলে EPI কার্ড দেখে জানা গেল। একজন SK হিসেবে আপনি কীভাবে শিশুটিকে missed vaccination child হিসেবে তালিকাভুক্ত করবেন?",
    "expected_answer_bn": "নির্ধারিত পদ্ধতি অনুযায়ী 'missed vaccination child'-এর তালিকা/ফর্মে শিশুর তথ্য অন্তর্ভুক্ত করুন এবং সংশ্লিষ্ট হেলথ অ্যাসিস্ট্যান্টকে তথ্যটি দিন, প্রয়োজনে মৌখিকভাবেও জানান।",
    "source_card_id": [
      "c5a75002-e4b6-46e3-ad4a-3fc55d3b3921"
    ],
    "query_type": "Procedural",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Tracking & Reporting Defaulters",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "065e5a37-6dcf-4fe4-9450-b05176ad13ac"
    ]
  }
]

## GENERATION PLAN
[
  {
    "module_id": "065e5a37-6dcf-4fe4-9450-b05176ad13ac",
    "module_title": "ইপিআই কার্যক্রমের উদ্দেশ্য ও লক্ষ্যিত জনগোষ্ঠী",
    "record_count": 3,
    "suggested_query_types": [
      "Factual",
      "Situational",
      "Procedural"
    ],
    "card_ids": [
      "25738f5d-830f-4d8b-bc38-9ecacfd2b35f",
      "afa85ee2-2d09-49da-9fb1-3217bc589f82",
      "44051a6f-21c2-434f-996e-4c5fbc5992d6",
      "ab78583f-c3cc-44df-9bc0-9ae532e3329c",
      "c5a75002-e4b6-46e3-ad4a-3fc55d3b3921"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: ইপিআই কার্যক্রমের উদ্দেশ্য ও লক্ষ্যিত জনগোষ্ঠী
module_id: 065e5a37-6dcf-4fe4-9450-b05176ad13ac
cards: 5

### Card 1 (id: 25738f5d-830f-4d8b-bc38-9ecacfd2b35f)
Title (bn): ইপিআই কার্যক্রমের উদ্দেশ্য ও লক্ষ্যিত জনগোষ্ঠী
Body (bn): প্রশিক্ষক প্রথমে সবাইকে শুভেচ্ছা জানিয়ে সেশন শুরু করবেন এবং ইপিআই সর্ম্পকে একটি ধারণা দিবেন। ইপিআই এর লক্ষ্যিত জনগোষ্ঠী কারা তা বলবেন ও বোর্ডে লিখবেন এবং সকলকে বলতে বলবেন।

### Card 2 (id: afa85ee2-2d09-49da-9fb1-3217bc589f82)
Title (bn): শিশুর টিকা দিয়ে প্রতিরোধযোগ্য রোগসমূহ
Body (bn): আমরা বাচ্চাদের কোন কোন রোগের জন্য টিকা দিই, সেই রোগগুলোর নাম জানতে হবে। জেনে থাকলে সেগুলোর নাম কয়েকজনকে বলতে বলবেন এবং তিনি তা বোর্ডে লিখবেন। বলা শেষে সংযোজন বিয়োজন করে প্রতিরোধযোগ্য রোগ সর্ম্পকে একটি সংক্ষিপ্ত ধারণা দিবেন। শিশুর টিকা দিয়ে প্রতিরোধযোগ্য রোগ সর্ম্পকে বলতে পারবেন।

### Card 3 (id: 44051a6f-21c2-434f-996e-4c5fbc5992d6)
Title (bn): শিশুর টিকার সিডিউল
Body (bn): আমরা বাচ্চাদের কোন কোন রোগের জন্য টিকা দিই, সেই টিকাগুলোর নাম জানতে হবে। জেনে থাকলে সেগুলোর নাম কয়েকজনকে বলতে বলবেন এবং তিনি তা বোর্ডে লিখবেন। বলা শেষে সেগুলো যাচাই করবেন এবং ভুল-ত্রুটি সংযোজন বিয়োজন করে টিকার সিডিউল এর পোষ্টার উপস্থাপন করবেন। সবাই বুঝলো কিনা তা যাচাই করবেন। শিশুর টিকার সিডিউল বলতে পারবেন।

### Card 4 (id: ab78583f-c3cc-44df-9bc0-9ae532e3329c)
Title (bn): টিকার সাধারণ ও বিপদজনক পার্শ্বপ্রতিক্রিয়া এবং ব্যবস্থাপনা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'টিকা নেয়ার পর শিশুরা কি ধরণের সমস্যার সম্মুখীন হয় তা জানতে চাইবেন। তাদের বলা কথাগুলো মনযোগ সহকারে শুনবেন। পরে নিজে টিকার সাধারণ ও বিপদজনক সমস্যা এবং এর সমাধান নিয়ে আলোচনা করবেন। টিকার সাধারণ ও বিপদজনক পার্শ্বপ্রতিক্রিয়া এবং ব্যবস্থাপনা বলতে পারবেন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a baby lying down, receiving an injection in the upper arm from a hand holding a syringe.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/5183cfe600608a553dcf2d329bf7a0b4de6f89391b966820616a1cb930870e96.jpg'}}]

### Card 5 (id: c5a75002-e4b6-46e3-ad4a-3fc55d3b3921)
Title (bn): মাঠ পর্যায়ে ইপিআই কার্যক্রম বাস্তবায়নে স্বাস্থ্যকর্মীদের করণীয়
Body (bn): মাঠ পর্যায়ে ইপিআই কার্যক্রম সহজভাবে করতে স্বাস্থ্যকর্মীদের করণীয় সর্ম্পকে আলোচনা করবেন এবং অংশগ্রহণকারীদের জ্ঞান যাচাই করে সেশন শেষ করবেন।


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
