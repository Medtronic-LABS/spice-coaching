# Golden expansion prompt — nutrition (batch 2/2)

Expected records: 11

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

DOMAIN: nutrition
Generate exactly 11 new golden records distributed per the generation plan.

## FEW-SHOT EXAMPLES
[
  {
    "question_en": "During today's visit, I found swelling (edema) in the mother's feet/face, and upon checking blood pressure, I noticed it has increased compared to last month's record. As a health worker, what should be my next step in this situation?",
    "expected_answer_en": "Some swelling in the feet is normal during pregnancy. However, swelling in the face or hands, or swelling combined with increased blood pressure (≥140/90 mmHg) may indicate a risk of pre-eclampsia. Assess for danger signs, check blood pressure and urinary protein, and immediately refer the mother to the nearest hospital or Upazila Health Complex if criteria are met. Advise the mother to rest in the left lateral position and monitor fetal movement.",
    "question_bn": "আজ ভিজিটে মায়ের পা/মুখ ফোলা (ইডিমা) পাওয়া গেছে, এবং রক্তচাপ মেপে দেখলাম গত মাসের রেকর্ডের তুলনায় এই মাসে বেড়েছে। এই অবস্থায় আমি স্বাস্থ্যকর্মী হিসেবে পরবর্তী পদক্ষেপ কী হওয়া উচিত?",
    "expected_answer_bn": "গর্ভাবস্থায় পায়ে সাধারণ ফোলা থাকা স্বাভাবিক হতে পারে। কিন্তু মুখ বা হাতে ফোলা, অথবা ফোলার সঙ্গে রক্তচাপ বৃদ্ধি (≥১৪০/৯০ mmHg) থাকলে প্রি-এক্ল্যাম্পসিয়ার ঝুঁকি থাকতে পারে। বিপদচিহ্ন যাচাই করুন, রক্তচাপ ও প্রস্রাবে প্রোটিন পরীক্ষা করুন এবং প্রয়োজনে তাৎক্ষণিক নিকটস্থ হাসপাতাল বা উপজেলা স্বাস্থ্য কমপ্লেক্সে রেফার করুন। রোগীকে বাম কাত হয়ে বিশ্রাম নিতে এবং বাচ্চার নড়াচড়ার দিকে খেয়াল রাখতে বলুন।",
    "source_card_id": [
      "1f5fb32d-13d7-4ebb-beb7-d60b6fbfab26",
      "2504fd7f-e3e5-42b3-924f-51c75d754231",
      "d687a96e-ed56-4035-9e14-315b21de05ad",
      "74aece78-688f-40ee-895c-25ba4693df30"
    ],
    "query_type": "Scenario-based",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Clinical Protocol & Escalation",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "3f751ce8-c5fc-4a45-9bd2-6f7c4807e396",
      "46900f4a-4978-4e3f-9db1-cceb677c8146"
    ]
  },
  {
    "question_en": "The mother has edema and slightly increased blood pressure, but it is below 140/90, urinary protein is negative, and there are no danger signs. What advice should I give the mother in this situation?",
    "expected_answer_en": "Reassure the mother but advise her to remain cautious. Advise adequate rest, at least 8 hours of sleep at night, sleeping on the left side, reducing salt intake, and drinking enough water. Instruct her to go to the hospital immediately if any danger signs appear and to schedule the next ANC visit sooner. Do not prescribe any medication.",
    "question_bn": "মায়ের ইডিমা আছে এবং রক্তচাপ সামান্য বেড়েছে, কিন্তু তা ১৪০/৯০-এর নিচে, প্রস্রাবে প্রোটিন নেগেটিভ এবং কোনো বিপদচিহ্ন নেই — এই অবস্থায় আমি মাকে কী পরামর্শ দেব?",
    "expected_answer_bn": "মাকে আশ্বস্ত করুন কিন্তু সতর্ক থাকতে বলুন। পর্যাপ্ত বিশ্রাম, রাতে ৮ ঘণ্টা ঘুম, বাম কাত হয়ে শোয়া, লবণ কম খাওয়া এবং পর্যাপ্ত পানি পানের পরামর্শ দিন। বাসায় কোনো বিপদচিহ্ন দেখা দিলে সঙ্গে সঙ্গে হাসপাতালে যেতে বলুন এবং পরবর্তী এএনসি (ANC) ভিজিট দ্রুত করার পরামর্শ দিন। নিজে থেকে কোনো ওষুধ দেবেন না।",
    "source_card_id": [
      "fabcfe06-262b-4bea-ab5e-7cfd05ddb997",
      "dbef5a4b-e803-41b4-93af-cd4e6dbde2ff",
      "e4ac0dd2-e641-434d-a4b2-18449786df89",
      "5481b97d-5841-4009-82f0-c4d7306bbbc2"
    ],
    "query_type": "Scenario-based",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Counseling & Home Management",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "1d030fd0-6541-4e4b-bb0b-38a1cc2b29ab",
      "3f751ce8-c5fc-4a45-9bd2-6f7c4807e396",
      "46900f4a-4978-4e3f-9db1-cceb677c8146",
      "51ccb087-7ef6-4ad0-aec4-6285f7857a5e"
    ]
  },
  {
    "question_en": "The mother is in the 3rd trimester, has edema and slightly increased blood pressure but below 140/90, urinary protein is negative, and there are no danger signs. Besides previous advice, what additional advice should I give for the 3rd trimester?",
    "expected_answer_en": "Increase the frequency of ANC visits, teach fetal kick counting, discuss birth preparedness planning (emergency transport, blood donor, money), ensure institutional delivery, advise avoiding overexertion and standing for long periods, teach how to recognize danger signs, and provide nutritional advice.",
    "question_bn": "মা তৃতীয় ত্রৈমাসিকে (3rd trimester) আছেন, তার ইডিমা আছে এবং রক্তচাপ সামান্য বেড়েছে কিন্তু ১৪০/৯০-এর নিচে, প্রস্রাবে প্রোটিন নেগেটিভ এবং কোনো বিপদচিহ্ন নেই। আগের পরামর্শের পাশাপাশি তৃতীয় ত্রৈমাসিক (3rd trimester) বিবেচনায় আমি মাকে অতিরিক্ত কী পরামর্শ দেব?",
    "expected_answer_bn": "ANC ভিজিটের সংখ্যা বাড়ান, বাচ্চার নড়াচড়া (Fetal kick count) গণনা শেখান, প্রসব প্রস্তুতি পরিকল্পনা (জরুরি পরিবহন, রক্তদাতা, টাকা) নিয়ে আলোচনা করুন, প্রাতিষ্ঠানিক প্রসব নিশ্চিত করুন, অতিরিক্ত পরিশ্রম ও দীর্ঘক্ষণ দাঁড়িয়ে থাকা এড়াতে বলুন, বিপদচিহ্ন চিনতে শেখান এবং সুষম পুষ্টির পরামর্শ দিন।",
    "source_card_id": [
      "730c977b-8cec-4ba0-a84c-b37270abe8a5",
      "905210ac-0b60-48d1-87a2-7030ee28f0c3",
      "af773e4f-1d36-4a7e-a380-a4d2c68dab33",
      "5481b97d-5841-4009-82f0-c4d7306bbbc2"
    ],
    "query_type": "Scenario-based",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Counseling & Birth Preparedness",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "46900f4a-4978-4e3f-9db1-cceb677c8146",
      "51ccb087-7ef6-4ad0-aec4-6285f7857a5e",
      "6fa7a48b-fce5-48f6-8eaa-afbb56438bf6"
    ]
  },
  {
    "question_en": "What advice should be given to the mother in the postnatal period?",
    "expected_answer_en": "Eat balanced food (fish, meat, eggs, lentils, vegetables) and drink plenty of water. Take vitamin A and iron-calcium supplements. Avoid heavy work for 42 days, ensure rest and sleep. Be aware of breast care, personal hygiene, and postnatal danger signs.",
    "question_bn": "প্রসবপরবর্তী সময়ে মায়ের জন্য কি কি পরামর্শ দিতে হবে?",
    "expected_answer_bn": "সুষম খাবার (মাছ, মাংস, ডিম, ডাল, শাক-সবজি) ও প্রচুর পানি পান করতে হবে। ভিটামিন এ এবং আয়রন-ক্যালসিয়াম সাপ্লিমেন্ট নিতে হবে। ভারী কাজ ৪২ দিন পর্যন্ত এড়িয়ে চলতে হবে, পূর্ণ বিশ্রাম ও ঘুম নিশ্চিত করতে হবে। স্তনের যত্ন, ব্যক্তিগত পরিচ্ছন্নতা এবং প্রসব পরবর্তী বিপদচিহ্ন সম্পর্কে সচেতন হতে হবে।",
    "source_card_id": [
      "20b93b58-d6cf-4ce2-9a3d-7d352c7c029f",
      "f1c92c05-d7b4-4b76-8c7c-41c9d21cc29f",
      "18c3171f-d17c-496d-b0fb-a2f4e4402517",
      "b66830d4-393e-49e8-90a8-3b331729ba8b",
      "34b6d1de-544c-4f13-8305-d893088b1aef"
    ],
    "query_type": "Procedural",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Postnatal Maternal Counseling",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "102da01a-b99c-44c1-8469-5f09d87639be",
      "e7b05394-a774-4ae1-a5c4-955a9483a131"
    ]
  },
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
  }
]

## GENERATION PLAN
[
  {
    "module_id": "f2e10590-9fa6-420c-a131-5f0f070df449",
    "module_title": "শালদুধ কি?",
    "record_count": 11,
    "suggested_query_types": [
      "Factual",
      "Procedural",
      "Cross-card Synthesis",
      "Counseling",
      "Drug / Dosage",
      "Situational",
      "Factual",
      "Situational",
      "Procedural",
      "Referral Decision",
      "Factual"
    ],
    "card_ids": [
      "602a8ad8-4a60-4075-b594-1c78cd5ae29b",
      "9be5b401-d194-464b-9841-00ba9bb2eebb",
      "e6f06d40-1eb8-4d7c-9227-9772e3a038de",
      "5a68bce8-159e-4a3a-a94c-698e9606d746",
      "ce3f0c80-3c59-438f-b0fe-f51ce37205a3",
      "366ed8a1-1194-425c-9b02-5a5c08b9c290",
      "ba085f83-6b23-45c8-9785-1aacaf292c52",
      "c9b2990d-028f-4a44-bdc5-55716abc10bc",
      "a02d552c-5628-45b9-8474-46ca14c6dce1",
      "e2af1c87-82a4-47e8-aa31-dbaef0f052e9"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: শালদুধ কি?
module_id: f2e10590-9fa6-420c-a131-5f0f070df449
cards: 10

### Card 1 (id: 602a8ad8-4a60-4075-b594-1c78cd5ae29b)
Title (bn): শালদুধ কি?
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শালদুধ হল মায়ের প্রথম দুধ যা দেখতে হলদেটে, আঠালো, বেশ ঘন এবং পরিমাণে অল্প।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'A drawing of a newborn baby lying on its back, with the umbilical cord still attached and clamped. The baby is depicted with its head turned to the left and arms bent.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/7153e5231e96388d4119747854d68ec6c98c80c33441232a917475e90b220b55.jpg'}}]

### Card 2 (id: 9be5b401-d194-464b-9841-00ba9bb2eebb)
Title (bn): কখন শালদুধ খাওয়াতে হবে?
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শিশু জন্মের সঙ্গে সঙ্গে মুখে এবং কাপড়ে মুড়ে যত দ্রুত সম্ভব, অর্থাৎ এক ঘণ্টার মধ্যে শালদুধ টানতে মায়ের বুকে দিতে হবে। দুধ দেওয়ার পূর্বে মায়ের স্তনের বোঁটা অবশ্যই পরিষ্কার করে নিতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'নবজাতকের অত্যাবশ্যকীয় পরিচর্যা\nমোছানো\nজন্মের সাথে সাথে পরিষ্কার ও শুকনো\nনরম সুতি কাপড় দিয়ে মোছানো\nনাড়ীর যত্ন\nএকবার ক্লোরহেক্সিডিন লাগানোর পর\nনাড়ীতে অন্য কোন কিছুই না লাগানো\nও শুষ্ক রাখা\nউষ্ণতা বজায় রাখা\nমোছানোর সাথে সাথে মায়ের ত্বকে\nত্বক স্পর্শে রাখা এবং পরবর্তীতে মাথা\nও শরীর কাপড়ে জড়িয়ে উষ্ণ রাখা\nবুকের দুধ খাওয়ানো\nজন্মের সাথে সাথে, অবশ্যই ১ ঘণ্টার\nমধ্যেই বুকের দুধ খাওয়ানো\nনা\nগোসল না করানো\nজন্মের তিন দিনের মধ্যে কোনভাবেই\nশিশুকে গোসল না করানো\nমা ও নবজাতক বাঁচানোর সাফ কথা:\nThis is a public health poster in Bengali titled "Essential Care for Newborns". It illustrates five key practices for newborn care: wiping, umbilical cord care, maintaining warmth, breastfeeding, and not bathing the baby immediately after birth. Each practice is accompanied by an illustration and a short descriptive text.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/157e79f5b7dd179dda8e277f02617c5b94429947704cf0a043df65f175be89cd.png'}}]

### Card 3 (id: e6f06d40-1eb8-4d7c-9227-9772e3a038de)
Title (bn): শালদুধে মা ও শিশুর উপকারিতা
Body (bn): শালদুধ খাওয়ালে মা ও শিশু উভয়েরই উপকার হয়। মায়ের প্রসব পরবর্তী রক্ত ক্ষরণ কম হয়, জরায়ু আগের অবস্থায় তাড়াতাড়ি ফিরে আসে এবং গর্ভফুল তাড়াতাড়ি পড়ে। শিশুর রোগ প্রতিরোধ ক্ষমতা বাড়ে এবং শিশুর প্রথম কালো পায়খানা দ্রুত বের হতে সাহায্য করে।

### Card 4 (id: 5a68bce8-159e-4a3a-a94c-698e9606d746)
Title (bn): মায়ের দুধের উপকারিতা: শিশুর জন্য
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শিশুর শরীর ভালোভাবে বেড়ে ওঠার জন্য মায়ের দুধে সব ধরনের পুষ্টি পাওয়া যায়। শিশুর ব্রেইন বা বুদ্ধি ভালোভাবে বাড়ে। শিশুর রোগ প্রতিরোধ ক্ষমতা বাড়ে ফলে বিভিন্ন অসুখ থেকে রক্ষা পায়, যেমন ডায়রিয়া, সর্দি কাশি, ঠান্ডা, নিউমোনিয়া, কান পাকা, এলার্জি। মায়ের দুধ একটা নির্দিষ্ট তাপমাত্রায় থাকে। মায়ের দুধ শিশুর জন্য নিরাপদ ও সহজে হজম করতে পারে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'A watercolor illustration shows a woman in a green sari sitting on a purple mat, breastfeeding a baby. The background features a woven wall and traditional clay pots.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/0b357899f83ae87b2a39f1dbf833b81bb4b2a604c59828d7edfa23df2f1dfc43.jpg'}}, {'type': 'image', 'attrs': {'alt': 'An illustration of a woman with brown hair, wearing a blue dress, sitting and breastfeeding a baby. The baby is light pink and white.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/0b225d60e4063b5d801a98585559fea03b910bfeb8af33c45a9acb599ea6f801.jpg'}}]

### Card 5 (id: ce3f0c80-3c59-438f-b0fe-f51ce37205a3)
Title (bn): মায়ের দুধের উপকারিতা: মায়ের জন্য
Body (bn): মায়ের সাথে শিশুর সম্পর্ক ভালো হয়। মায়ের জরায়ু তাড়াতাড়ি আগের অবস্থায় ফিরে আসে। মায়ের রক্ত ক্ষরণ কমায়। মায়ের স্তন, জরায়ু ও ডিম্বাশয়ের ক্যানসারের ঝুঁকি কমে যায়। মায়ের সময় বাঁচে ও ঝামেলা কম হয়।

### Card 6 (id: 366ed8a1-1194-425c-9b02-5a5c08b9c290)
Title (bn): শিশুকে সঠিকভাবে দুধ খাওয়ানোর নিয়ম: অবস্থান
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'মা আরাম করে বসবে বা শোবে। শিশুকে এমনভাবে ধরবে যাতে শিশুর শরীর ও মুখ মায়ের স্তনের দিকে ফিরানো থাকবে। শিশুর ঘাড় মায়ের কনুইয়ের ভাঁজে এবং মায়ের হাত শিশুর নিতম্বের উপর থাকবে। শিশুর মুখ মায়ের স্তনের দিকে এবং নাক স্তনের বোঁটা বরাবর থাকবে। শিশুর পেট মায়ের পেটের সঙ্গে লেগে থাকবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'ভাল সংগতি\nভাল সংগতি নয়\nস্তন্যপান করানোর সঠিক পদ্ধতি\nThe figure shows two illustrations of a baby latching to the breast, labeled "ভাল সংগতি" (good latch) and "ভাল সংগতি নয়" (not good latch), and three illustrations of a mother holding a baby for breastfeeding, labeled "স্তন্যপান করানোর সঠিক পদ্ধতি" (correct breastfeeding method).', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/3abdf5a59c4aea75dcaf8131a8efcbe996a1fe325acba24fd2907650b43db5ab.jpg'}}]

### Card 7 (id: ba085f83-6b23-45c8-9785-1aacaf292c52)
Title (bn): শিশুকে সঠিকভাবে দুধ খাওয়ানোর নিয়ম: সংস্থাপন
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শিশুর উপরের ঠোঁটের মাঝখান বরাবর এবং নাকের নীচে স্তনের বোঁটা ছোঁয়াতে হবে। শিশু বড় করে হাঁ করলে মুখে স্তনের বোঁটা সহ কালো অংশ শিশুর মুখের ভেতর দিতে হবে। শিশুর থুতনী ও নাক মায়ের স্তনের সাথে লেগে থাকবে এবং শিশুর নীচের ঠোঁট বাহিরের দিকে উল্টানো থাকবে। মায়ের স্তনের কালো অংশ যদি বড় হয় সেক্ষেত্রে কালো অংশের নীচের দিক যেন পুরোপুরি শিশুর মুখের মধ্যে যায়।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'ভাল সংগতি\nভাল সংগতি নয়\nস্তন্যপান করানোর সঠিক পদ্ধতি\nThe figure shows two illustrations of a baby latching to the breast, labeled "ভাল সংগতি" (good latch) and "ভাল সংগতি নয়" (not good latch), and three illustrations of a mother holding a baby for breastfeeding, labeled "স্তন্যপান করানোর সঠিক পদ্ধতি" (correct breastfeeding method).', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/3abdf5a59c4aea75dcaf8131a8efcbe996a1fe325acba24fd2907650b43db5ab.jpg'}}]

### Card 8 (id: c9b2990d-028f-4a44-bdc5-55716abc10bc)
Title (bn): শিশু ঠিক ভাবে দুধ পাচ্ছে কিনা কিভাবে বুঝব?
Body (bn): মুখের হাঁ বড় থাকবে। শিশুর নিচের ঠোঁট বাইরের দিকে উল্টানো থাকবে। স্তনের বোঁটার চারপাশের কালো অংশ বিশেষ করে নিচের অংশ পুরোপুরি শিশুর মুখের মধ্যে থাকবে। শিশুর নাকের ডগা এবং থুতনি স্তন স্পর্শ করে থাকবে। শিশুর দুধ গেলার শব্দ পাওয়া যাবে। শিশু চব্বিশ ঘন্টায় কমপক্ষে ছয় বার প্রস্রাব করবে। শিশু স্বাভাবিকভাবে বেড়ে উঠবে। শিশু হাসি-খুশি থাকবে।

### Card 9 (id: a02d552c-5628-45b9-8474-46ca14c6dce1)
Title (bn): মায়ের স্তনের সাধারণ সমস্যা ও করণীয়
Body (bn): মায়ের স্তনের কিছু সাধারণ সমস্যা হতে পারে, যেমন স্তনের বোঁটা ভেতরের দিকে ঢুকে থাকা, স্তনে দুধ জমা হয়ে স্তন ফুলে যাওয়া ও শক্ত হওয়া, স্তনের বোঁটার চামড়া ছিলে বা ফেটে যাওয়া, এবং ছত্রাক সংক্রমণ। বোঁটা ভেতরের দিকে ঢুকে থাকলে গর্ভাবস্থা থেকে গোসলের সময় ভালোভাবে বোঁটা পরিষ্কার করতে হবে এবং হাত দিয়ে ম্যাসেজ করতে হবে। প্রসবের পরপরই বোঁটা পরিষ্কার করে হাত দিয়ে টেনে ওঠাতে হবে এবং শিশুকে ঘনঘন মায়ের বুকের দুধ টেনে খেতে দিতে হবে। স্তনে দুধ জমা হয়ে শক্ত হয়ে গেলে বুকের দুধ বের করে স্তন নরম করে শিশুকে বারে বারে খেতে দিতে হবে। ব্যথা বেশি হলে দুধ খাওয়ানোর আগে গরম সেঁক এবং পরে ঠান্ডা সেঁক দিতে হবে। ব্যথা বেড়ে গেলে হাসপাতালে রেফার করতে হবে। বোঁটার চামড়া ছিলে গেলে বোঁটার উপরে বুকের গাঢ় দুধ লাগিয়ে কিছুক্ষণ রোদ লাগাতে হবে এবং শিশুকে দুধ খাওয়ানোর সময় বোঁটার চারপাশের কালো অংশের বেশিরভাগ শিশুর মুখের মধ্যে আছে কিনা খেয়াল রাখতে হবে। বুকের দুধ খাওয়ানো কিছুতেই বন্ধ করা যাবে না এবং মাকে ঢিলে-ঢালা সুতি কাপড় পড়তে হবে। ছত্রাক সংক্রমণ হলে শিশু সহ মাকে চিকিৎসকের পরামর্শ নিয়ে চিকিৎসা করতে হবে।

### Card 10 (id: e2af1c87-82a4-47e8-aa31-dbaef0f052e9)
Title (bn): বুকের দুধ বের করে সংরক্ষণ করার পদ্ধতি
Body (bn): বুকের দুধ বের করার জন্য বড় মুখওয়ালা একটি বাটি বা কাপ নিতে হবে। বাটি বা কাপটিকে টিউবওয়েলের পানিতে ধুয়ে নিতে হবে, অথবা ফুটন্ত গরম পানিতে কয়েক মিনিট রেখে দিতে হবে। বুকের দুধ বের করার আগে মাকে অবশ্যই সাবান দিয়ে ভালোভাবে হাত ধুয়ে নিতে হবে। মাকে আরামদায়ক ভাবে বসতে হবে। দুধ গালানোর পূর্বে সম্ভব হলে শিশুকে কিছু সময় দুধ চুষাতে হবে। কোন কারণে শিশু দুধ চুষতে না পারলে দুই হাত দিয়ে কিছুক্ষণ স্তন ম্যাসেজ করতে হবে। বুড়ো আঙ্গুল বুকের উপরের দিকে ও বাকি চারটি আঙ্গুল বুকের নীচে দিয়ে আস্তে আস্তে বারবার চাপ দিয়ে আবার তা ছাড়তে বলুন, এভাবে বারবার করতে থাকবেন। প্রথমে দুধ না আসলেও পরে ফোঁটায় ফোঁটায় বের হয়ে আসবে। বুকের কালো অংশে চাপ দিয়ে দুধ বের করতে হবে, বোঁটায় চাপ দেওয়া উচিত নয়। বুকের বিভিন্ন অংশে ঘুরিয়ে ঘুরিয়ে চাপ দিয়ে দুধ বের করতে হবে। এক বুক থেকে কমপক্ষে তিন থেকে পাঁচ মিনিট পর্যন্ত দুধ বের করা যেতে পারে। সেই বুকের দুধ যখন আর বেশি করে বের হবে না তখন আরেক বুক থেকে দুধ বের করতে হবে। বুকের দুধ বের করতে বিশ থেকে ত্রিশ মিনিট সময়ের প্রয়োজন। গালানো দুধ একটি পরিষ্কার পাত্রে রাখবেন। ঘরের ভিতরের স্বাভাবিক তাপমাত্রায় বুকের দুধ আট ঘণ্টা পর্যন্ত রাখা যায়। শিশুকে যখন গালানো দুধ খাওয়ানো হবে তখন একবারে যতটুকু দুধ দিতে হবে ততটুকু দুধ বাটিতে নিন এবং বাটিটি হালকা গরম পানিতে কিছুক্ষণ রেখে গরম করা যায়। মায়ের দুধ আগুনে বা চুলায় গরম করা উচিত নয়, এতে মায়ের দুধের পুষ্টিগুণ নষ্ট হয়।


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
