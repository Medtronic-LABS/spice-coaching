# Golden expansion prompt — neonatal (batch 1/2)

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

DOMAIN: neonatal
Generate exactly 3 new golden records distributed per the generation plan.

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
    "module_id": "ef6d104b-161b-491f-b853-b772ffaf97a4",
    "module_title": "নবজাতক কাদের বলে এবং গর্ভকালীন সময়ের ভিত্তিতে নবজাতকের প্রকারভেদ",
    "record_count": 3,
    "suggested_query_types": [
      "Situational",
      "Procedural",
      "Referral Decision"
    ],
    "card_ids": [
      "f29d8b77-a0f1-47af-a828-9400d4230e11",
      "c56b2e7c-5376-4762-aded-06e3c7c57f11",
      "b5e525b1-f036-45e7-87ee-4ed2470133f6",
      "bfcf4b47-8c14-4ff9-a688-4733b9ef731f",
      "df8b88bd-d1dd-4c5c-844d-d52a0aa4ce18",
      "0abe65ab-03bf-4564-b0e3-38fb902d662d"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: নবজাতক কাদের বলে এবং গর্ভকালীন সময়ের ভিত্তিতে নবজাতকের প্রকারভেদ
module_id: ef6d104b-161b-491f-b853-b772ffaf97a4
cards: 6

### Card 1 (id: f29d8b77-a0f1-47af-a828-9400d4230e11)
Title (bn): নবজাতক কাদের বলে এবং গর্ভকালীন সময়ের ভিত্তিতে নবজাতকের প্রকারভেদ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'জন্মের পর থেকে ২৮ দিন পর্যন্ত শিশুকে নবজাতক বলে। সাধারণত একটি শিশু পূর্ণ ৩৭ সপ্তাহ থেকে ৪২ সপ্তাহ মায়ের গর্ভে থাকে। গর্ভকালীন সময়ের ভিত্তিতে নবজাতককে তিন ভাগে ভাগ করা যায়। অপরিনত শিশু হলো যারা গর্ভের পূর্ণ ৩৭ সপ্তাহের পূর্বে জন্ম নেয়। এদের লম্বা ৫০ সেন্টিমিটারের কম হয়, মাথা ছোট থাকে, কান, স্তন ও জননাঙ্গ অপরিনত থাকে এবং সারা শরীর লোমে আবৃত থাকে। পরিনত শিশু হলো যারা গর্ভের পূর্ণ ৩৭ সপ্তাহ থেকে ৪২ সপ্তাহের মধ্যে জন্ম নেয়। এদের ওজন স্বাভাবিক (২.৫ কেজি বা তার বেশি) অথবা কম হতে পারে। অধিক পরিণত শিশু হলো যারা গর্ভের ৪২ সপ্তাহের পরে জন্ম নেয়। এদের ত্বক সাধারণত মোটা ও শুকনা কাগজের মতো থাকে, কান, স্তন, জননাঙ্গ পরিনত হয় এবং শরীরে লোম কম থাকে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a sleeping baby swaddled in a pink blanket, with a blue pacifier in its mouth. The baby has light skin, closed eyes, and a few curls of hair.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/7260f4ef82b042ac8fa4a7b39483279f8648230281290fba2bee14baf7087e86.jpg'}}, {'type': 'image', 'attrs': {'alt': 'A drawing of a newborn baby lying on its back, with the umbilical cord still attached and clamped. The baby is depicted with its head turned to the left and arms bent.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/7153e5231e96388d4119747854d68ec6c98c80c33441232a917475e90b220b55.jpg'}}]

### Card 2 (id: c56b2e7c-5376-4762-aded-06e3c7c57f11)
Title (bn): সুস্থ নবজাতকের লক্ষণ
Body (bn): একটি নবজাতককে সুস্থ বলতে হলে কিছু লক্ষণ দেখতে হবে। নবজাতক পূর্ণ বয়সে জন্ম গ্রহণ করবে, অর্থাৎ পূর্ণ ৩৭ সপ্তাহ থেকে ৪২ সপ্তাহের মধ্যে জন্ম হবে। জন্ম ওজন ২.৫ কেজি থেকে ৪ কেজি হবে। শিশুর রং গোলাপী হবে। শ্বাস প্রতি মিনিটে ৩০ থেকে ৫৯ বার হবে। হৃদস্পন্দন প্রতি মিনিটে ১০০ থেকে ১৬০ বার হবে। তাপমাত্রা ৯৭ থেকে ৯৯ ডিগ্রী ফারেনহাইট হবে। ২৪ ঘন্টার মধ্যে মলত্যাগ করবে এবং ৪৮ ঘন্টার মধ্যে প্রস্রাব করবে।

### Card 3 (id: b5e525b1-f036-45e7-87ee-4ed2470133f6)
Title (bn): নবজাতকের প্রথম ৬ ঘন্টার অত্যাবশ্যকীয় সেবা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'জন্মের পরপর নবজাতকের কিছু সেবা অতি জরুরী। প্রথম ৬ ঘন্টার সেবার মধ্যে রয়েছে: মোছানো - জন্মের সাথে সাথে পরিষ্কার শুকনো ও নরম সুতি কাপড় দিয়ে শিশুকে মুছতে হবে। শিশুর গায়ে ঘষা দেওয়া যাবে না। উষ্ণতা বজায় রাখা - মোছানোর সাথে সাথে মায়ের ত্বকে ত্বক স্পর্শে রাখতে হবে এবং পরবর্তীতে মাথা ও শরীর কাপড়ে জড়িয়ে উষ্ণ রাখতে হবে। শিশুর শরীরের তুলনায় মাথা অনেক বড়, মাথা না ঢাকলে শিশু তাপ হারাতে পারে। শালদুধ খাওয়ানো - জন্মের সাথে সাথে, অবশ্যই ১ ঘন্টার মধ্যেই শিশুকে মায়ের দুধ টানতে দিতে হবে। শালদুধ খাওয়ানোর আগে মায়ের স্তনের বোঁটা অবশ্যই পরিষ্কার করে নিতে হবে। নাভী কাটা ও বাঁধা - পরিষ্কার ও জীবানুমুক্ত সুতা দিয়ে নির্দিষ্ট দূরত্বে তিনটি বাঁধন দিয়ে জীবানুমুক্ত ব্লেড দিয়ে শিশুর দিক থেকে দ্বিতীয় ও তৃতীয় বাঁধনের মাঝে নাভী কাটতে হবে। গোসল না করানো - জন্মের তিন দিনের মধ্যে কোনভাবেই শিশুকে গোসল করানো যাবে না।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'নবজাতকের অত্যাবশ্যকীয় পরিচর্যা\nমোছানো\nজন্মের সাথে সাথে পরিষ্কার ও শুকনো\nনরম সুতি কাপড় দিয়ে মোছানো\nনাড়ীর যত্ন\nএকবার ক্লোরহেক্সিডিন লাগানোর পর\nনাড়ীতে অন্য কোন কিছুই না লাগানো\nও শুষ্ক রাখা\nউষ্ণতা বজায় রাখা\nমোছানোর সাথে সাথে মায়ের ত্বকে\nত্বক স্পর্শে রাখা এবং পরবর্তীতে মাথা\nও শরীর কাপড়ে জড়িয়ে উষ্ণ রাখা\nবুকের দুধ খাওয়ানো\nজন্মের সাথে সাথে, অবশ্যই ১ ঘণ্টার\nমধ্যেই বুকের দুধ খাওয়ানো\nনা\nগোসল না করানো\nজন্মের তিন দিনের মধ্যে কোনভাবেই\nশিশুকে গোসল না করানো\nমা ও নবজাতক বাঁচানোর সাফ কথা:\nThis is a public health poster in Bengali titled "Essential Care for Newborns". It illustrates five key practices for newborn care: wiping, umbilical cord care, maintaining warmth, breastfeeding, and not bathing the baby immediately after birth. Each practice is accompanied by an illustration and a short descriptive text.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/157e79f5b7dd179dda8e277f02617c5b94429947704cf0a043df65f175be89cd.png'}}, {'type': 'image', 'attrs': {'alt': 'A watercolor illustration shows a woman in a green sari sitting on a purple mat, breastfeeding a baby. The background features a woven wall and traditional clay pots.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/0b357899f83ae87b2a39f1dbf833b81bb4b2a604c59828d7edfa23df2f1dfc43.jpg'}}, {'type': 'image', 'attrs': {'alt': 'An illustration of a woman with brown hair, wearing a blue dress, sitting and breastfeeding a baby. The baby is light pink and white.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/0b225d60e4063b5d801a98585559fea03b910bfeb8af33c45a9acb599ea6f801.jpg'}}, {'type': 'image', 'attrs': {'alt': 'ভাল সংগতি\nভাল সংগতি নয়\nস্তন্যপান করানোর সঠিক পদ্ধতি\nThe figure shows two illustrations of a baby latching to the breast, labeled "ভাল সংগতি" (good latch) and "ভাল সংগতি নয়" (not good latch), and three illustrations of a mother holding a baby for breastfeeding, labeled "স্তন্যপান করানোর সঠিক পদ্ধতি" (correct breastfeeding method).', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/3abdf5a59c4aea75dcaf8131a8efcbe996a1fe325acba24fd2907650b43db5ab.jpg'}}]

### Card 4 (id: bfcf4b47-8c14-4ff9-a688-4733b9ef731f)
Title (bn): নবজাতকের ৬ ঘন্টা থেকে ১ মাস পর্যন্ত সেবা
Body (bn): [{'type': 'paragraph', 'content': [{'text': '৬ ঘন্টা থেকে ১ মাস পর্যন্ত নবজাতকের সেবার মধ্যে রয়েছে: শুধুমাত্র বুকের দুধ খাওয়ানো - জন্মের পর থেকে প্রথম ৬ মাস শিশুর জন্য শুধুমাত্র বুকের দুধই যথেষ্ট। এতে করে শিশু পুরোপুরি পুষ্টি পায় এবং শিশুর বুদ্ধি ও বিকাশ স্বাভাবিক হয়। নাভীতে কিছু না লাগানো - নাভীতে কোন কিছু না লাগিয়ে শুকনো ও পরিষ্কার রাখলে সাধারণত ৭ দিনের মধ্যেই নাভী পড়ে যায় এবং ১০ দিনের মধ্যে শুকিয়ে যায়। জন্ম ওজন নেয়া - শিশু জন্মের ৩ দিনের মধ্যে ওজন নিতে হবে কারণ এতে করে কম জন্ম ওজনের শিশু সনাক্ত করা যাবে এবং বিশেষ সেবা দেয়া সম্ভব হবে। গোসল করানো - শিশু সুস্থ থাকলে ৩ দিন পরে গোসল করানো যেতে পারে। কিন্তু কম জন্ম ওজনের শিশুদের বেলায় ৭ দিনের আগে গোসল করানো উচিত নয়। চুল কাটা - নবজাতকের চুল কাটলে মাথার ত্বকে আঘাত লাগতে পারে এবং জীবানু সংক্রমণ হতে পারে। এছাড়াও শিশু বেশিরভাগ তাপ হারায় মাথার মাধ্যমে। সুতরাং চুল যত দেরী করে ফেলা যায় ততো ভালো বিশেষ করে জন্মের প্রথম মাসে চুল না ফেলাই ভালো।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'dreamstime.com\nA stylized illustration depicts a fetus or newborn baby lying on a weighing scale. The baby is light orange, and the scale is grey with a dial and needle.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/01bb0b0dd884677bdf162f4b19b0913098b4bdb8aff7396f29d729d71eeb9468.jpg'}}, {'type': 'image', 'attrs': {'alt': 'An illustration shows a woman weighing a baby on a pink scale placed on a wooden table. A man and a young girl are standing next to her, observing the process.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/4269c09d3f61f2b527a54a955fe1206d18a314c0cf281190abceecf2498bf103.jpg'}}, {'type': 'image', 'attrs': {'alt': 'মেয়েদের ওজন বৃদ্ধির চার্ট\nতমন (কিলোগ্রাম)\nOmow\nশিশুর জন্ম ওজন (কেজি)\nবৃঠিকভাবে বাড়ছে\nদিজ্য গুজব রেখা\nবে, শিশুর ওজন সঠিকতাসে পড়ত\nঅতধাস\nLU\nছেলেদের ওজন বৃদ্ধির চার্ট\nbet\n২৯\nভাদন (ফিনোলাম)\nওজন (কিলোগ্রাম)\nবিপদের লক্ষণ্য\nশিশুর জন্য ওজন (কেজি)\nRa\n২০\nবীচের দিকে মানতে\nবিপদের লক্ষণ\n৩\nVE\n人人\nগতক\nThis figure displays two growth charts, one for girls (মেয়েদের ওজন বৃদ্ধির চার্ট) and one for boys (ছেলেদের ওজন বৃদ্ধির চার্ট), showing weight (ওজন (কিলোগ্রাম)) over time. The charts are color-coded with green for "বৃঠিকভাবে বাড়ছে" (growing correctly), yellow for "বীচের দিকে মানতে" (borderline), and red for "বিপদের লক্ষণ" (danger signs). Both charts include a section for "শিশুর জন্ম ওজন (কেজি)" (baby\'s birth weight (kg)).', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/8a81d672dae172e97c1df2dad890be6fb6c28bb36d4a4597b2afab56c52bde7a.png'}}]

### Card 5 (id: df8b88bd-d1dd-4c5c-844d-d52a0aa4ce18)
Title (bn): নবজাতকের বিপদচিহ্নসমূহ এবং করণীয়
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'নবজাতকের কিছু বিপদচিহ্ন দেখা দিলে দ্রুত ব্যবস্থা নিতে হবে। এই বিপদচিহ্নগুলো হলো: দ্রুত শ্বাসের সাথে বুকের পাঁজর ডেবে গেলে অথবা বুকের খাঁচা দেবে যাওয়া। বুকের দুধ টেনে খেতে না পারলে বা না চোষা। অতিরিক্ত জ্বর বা স্বাভাবিকের চেয়ে তাপমাত্রা কমে যাওয়া। খিঁচুনি। নাভি পাকা। নেতিয়ে পড়া। এই বিপদচিহ্নগুলো দেখা দিলে সাথে সাথে হাসপাতালে বা উপজেলা স্বাস্থ্য কেন্দ্রে রেফার করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'দ্রুত শ্বাস নেওয়া অথবা\nThe image shows two illustrations within a circular segmented diagram. The left segment depicts a baby lying down, and the right segment shows a baby being breastfed by an adult.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/fc81f69a2f0e544a8cda6f7431661361944eef44bbd39008a0371382c8d2163a.jpg'}}, {'type': 'image', 'attrs': {'alt': "নাভি পাকা\nবুকের খাঁচা দেবে যাওয়া\nবুকের দুধ ঢানতে\nনা পারা বা না চোষা\nজ্বর বা শরীর ঠান্ডা হওয়া\nA circular diagram with a baby's face in the center, surrounded by four quadrants depicting different infant health problems: umbilical infection, chest indrawing, inability to suckle breast milk, and fever or cold body.", 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/9168e38a21c09e3a12426138100f8f4eb04b81eedf89f52334f7300707d14a1d.jpg'}}, {'type': 'image', 'attrs': {'alt': 'খিঁচুনি\nনেতিয়ে পড়া\nThe image shows two illustrations of infants, each with a Bengali label. The left illustration shows an infant convulsing, labeled "খিঁচুনি" (convulsion). The right illustration shows an infant being held, appearing limp, labeled "নেতিয়ে পড়া" (limp/flaccid).', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/78860d88b909fc6612353522e28b4e2934a06a9550d3ade6b1b428d8990bd654.jpg'}}, {'type': 'image', 'attrs': {'alt': 'An illustration of a woman holding a distressed infant, with three circular insets highlighting symptoms: rapid breathing, lung issues (possibly pneumonia), and chest indrawing.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/e22744cbee3bf6ba008664e85a93abbf82564e846a739c1d083b06c1cf8ec0f8.jpg'}}]

### Card 6 (id: 0abe65ab-03bf-4564-b0e3-38fb902d662d)
Title (bn): নবজাতকের টিকাদান
Body (bn): জন্মের পর যত তাড়াতাড়ি সম্ভব বিসিজি টিকা দিতে হবে। দেড় মাস থেকে পনেরো থেকে আঠারো মাস পর্যন্ত মোট পাঁচ বার টিকা কেন্দ্রে যেতে হবে এবং দশটি রোগের টিকা নিতে হবে।


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
