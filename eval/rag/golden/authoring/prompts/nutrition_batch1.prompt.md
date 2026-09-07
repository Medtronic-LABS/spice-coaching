# Golden expansion prompt — nutrition (batch 1/2)

Expected records: 6

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
Generate exactly 6 new golden records distributed per the generation plan.

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
    "module_id": "519a4bfc-2c2d-458c-93d6-e117cc4df8cd",
    "module_title": "শিশুর বৃদ্ধি ও বিকাশ কী?",
    "record_count": 6,
    "suggested_query_types": [
      "Drug / Dosage",
      "Situational",
      "Factual",
      "Situational",
      "Procedural",
      "Referral Decision"
    ],
    "card_ids": [
      "d9f9adfa-1371-4c03-8547-dc4c4bf52e09",
      "62455d97-43c8-4df5-b56b-c202fe94cd26",
      "2031c3d1-8fd5-4d96-92f8-f27d10854893",
      "378e6e49-9680-4dbc-b0c3-29f51eb849bb",
      "f261e2f1-781a-4be0-ad80-1957757d17c7",
      "af1d5340-b054-436b-9cf5-bfc281e0fa16"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: শিশুর বৃদ্ধি ও বিকাশ কী?
module_id: 519a4bfc-2c2d-458c-93d6-e117cc4df8cd
cards: 6

### Card 1 (id: d9f9adfa-1371-4c03-8547-dc4c4bf52e09)
Title (bn): শিশুর বৃদ্ধি ও বিকাশ কী?
Body (bn): শিশুর বৃদ্ধি হলো শরীরের বিভিন্ন অঙ্গের আকারে বড় ও লম্বা হওয়া এবং ওজন বাড়া। শিশুর বিকাশ হলো শিশুর বিভিন্ন অঙ্গের ব্যবহার, কথা বলার, অনুভূতি ও ভাবের আদান-প্রদানের দক্ষতা, যা শিশু বুদ্ধিতে বাড়া বা বিকাশ।

### Card 2 (id: 62455d97-43c8-4df5-b56b-c202fe94cd26)
Title (bn): গ্রোথ চার্ট বা ওজন বৃদ্ধির চার্ট কী?
Body (bn): [{'type': 'paragraph', 'content': [{'text': "যে চার্ট দিয়ে শিশুর বৃদ্ধি পর্যবেক্ষণ করা হয়, তাকে গ্রোথ চার্ট বা 'ওজন বৃদ্ধির চার্ট' বলা হয়। এই চার্টের মাধ্যমে শিশুর পুষ্টি অবস্থা পর্যবেক্ষণ করা হয়।", 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'মেয়েদের ওজন বৃদ্ধির চার্ট\nতমন (কিলোগ্রাম)\nOmow\nশিশুর জন্ম ওজন (কেজি)\nবৃঠিকভাবে বাড়ছে\nদিজ্য গুজব রেখা\nবে, শিশুর ওজন সঠিকতাসে পড়ত\nঅতধাস\nLU\nছেলেদের ওজন বৃদ্ধির চার্ট\nbet\n২৯\nভাদন (ফিনোলাম)\nওজন (কিলোগ্রাম)\nবিপদের লক্ষণ্য\nশিশুর জন্য ওজন (কেজি)\nRa\n২০\nবীচের দিকে মানতে\nবিপদের লক্ষণ\n৩\nVE\n人人\nগতক\nThis figure displays two growth charts, one for girls (মেয়েদের ওজন বৃদ্ধির চার্ট) and one for boys (ছেলেদের ওজন বৃদ্ধির চার্ট), showing weight (ওজন (কিলোগ্রাম)) over time. The charts are color-coded with green for "বৃঠিকভাবে বাড়ছে" (growing correctly), yellow for "বীচের দিকে মানতে" (borderline), and red for "বিপদের লক্ষণ" (danger signs). Both charts include a section for "শিশুর জন্ম ওজন (কেজি)" (baby\'s birth weight (kg)).', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/8a81d672dae172e97c1df2dad890be6fb6c28bb36d4a4597b2afab56c52bde7a.png'}}]

### Card 3 (id: 2031c3d1-8fd5-4d96-92f8-f27d10854893)
Title (bn): ওজন বৃদ্ধির চার্টের অংশসমূহ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ওজন বৃদ্ধির চার্টের নীচে শিশুর বয়স, ডান পাশে ওজন এবং বাম পাশে শিশুর অবস্থা (স্বাভাবিক, স্বল্প অপুষ্টি, মাঝারি অপুষ্টি, মারাত্মক অপুষ্টি) উল্লেখ থাকে। এতে পাঁচ ধরনের রং থাকে: সাদা, সবুজ, হালকা হলুদ, গাঢ় হলুদ ও লাল (উপর থেকে নিচের দিকে)।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'মেয়েদের ওজন বৃদ্ধির চার্ট\nতমন (কিলোগ্রাম)\nOmow\nশিশুর জন্ম ওজন (কেজি)\nবৃঠিকভাবে বাড়ছে\nদিজ্য গুজব রেখা\nবে, শিশুর ওজন সঠিকতাসে পড়ত\nঅতধাস\nLU\nছেলেদের ওজন বৃদ্ধির চার্ট\nbet\n২৯\nভাদন (ফিনোলাম)\nওজন (কিলোগ্রাম)\nবিপদের লক্ষণ্য\nশিশুর জন্য ওজন (কেজি)\nRa\n২০\nবীচের দিকে মানতে\nবিপদের লক্ষণ\n৩\nVE\n人人\nগতক\nThis figure displays two growth charts, one for girls (মেয়েদের ওজন বৃদ্ধির চার্ট) and one for boys (ছেলেদের ওজন বৃদ্ধির চার্ট), showing weight (ওজন (কিলোগ্রাম)) over time. The charts are color-coded with green for "বৃঠিকভাবে বাড়ছে" (growing correctly), yellow for "বীচের দিকে মানতে" (borderline), and red for "বিপদের লক্ষণ" (danger signs). Both charts include a section for "শিশুর জন্ম ওজন (কেজি)" (baby\'s birth weight (kg)).', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/8a81d672dae172e97c1df2dad890be6fb6c28bb36d4a4597b2afab56c52bde7a.png'}}]

### Card 4 (id: 378e6e49-9680-4dbc-b0c3-29f51eb849bb)
Title (bn): গ্রোথ চার্ট পূরণ করার পদ্ধতি
Body (bn): [{'type': 'paragraph', 'content': [{'text': "প্রথমে 'শিশুর জন্মতারিখ' ঘরে শিশুর জন্মতারিখ এবং 'শিশুর জন্ম ওজন (কেজি)' ঘরে জন্মের সময়ের ওজন লিখতে হবে (যদি মা জানাতে পারেন)। চার্টের নিচে শিশুর বয়সের ঘরে সেবা গ্রহণকারীর সেবা গ্রহণের তারিখ লিখতে হবে। এরপর শিশুর ওজন মেপে চার্টে সেই ওজন থেকে বয়স বরাবর ফোটা দিতে হবে। এভাবে পরবর্তী প্রতিটি ভিজিটে ওজন মেপে ফোটা দিতে হবে এবং পরপর দুইটি ফোটা স্কেল দিয়ে সংযুক্ত করে দাগ দিতে হবে।", 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration shows a woman weighing a baby on a pink scale placed on a wooden table. A man and a young girl are standing next to her, observing the process.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/4269c09d3f61f2b527a54a955fe1206d18a314c0cf281190abceecf2498bf103.jpg'}}, {'type': 'image', 'attrs': {'alt': 'An illustration of two hands holding a piece of paper with blue lines and red checkmarks. One hand is holding a yellow pencil, appearing to write or mark on the paper.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/18d13ef089b2d9c2248bbfe192f3afc31b108fea1b34938dc816b87aef07376c.jpg'}}]

### Card 5 (id: f261e2f1-781a-4be0-ad80-1957757d17c7)
Title (bn): গ্রোথ চার্টের ফলাফল বিশ্লেষণ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'গ্রোথ চার্টে দাগটি যদি সবুজ রং এর ঘরে থাকে, তাহলে শিশুর বৃদ্ধি স্বাভাবিক। দাগটি যদি হালকা হলুদ রং এর ঘরে থাকে, তাহলে শিশুর স্বল্প অপুষ্টি। দাগটি যদি গাঢ় হলুদ রং এর ঘরে থাকে, তাহলে শিশুর মাঝারি অপুষ্টি। দাগটি যদি লাল রং এর ঘরে থাকে, তাহলে শিশুর মারাত্মক অপুষ্টি।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'মেয়েদের ওজন বৃদ্ধির চার্ট\nতমন (কিলোগ্রাম)\nOmow\nশিশুর জন্ম ওজন (কেজি)\nবৃঠিকভাবে বাড়ছে\nদিজ্য গুজব রেখা\nবে, শিশুর ওজন সঠিকতাসে পড়ত\nঅতধাস\nLU\nছেলেদের ওজন বৃদ্ধির চার্ট\nbet\n২৯\nভাদন (ফিনোলাম)\nওজন (কিলোগ্রাম)\nবিপদের লক্ষণ্য\nশিশুর জন্য ওজন (কেজি)\nRa\n২০\nবীচের দিকে মানতে\nবিপদের লক্ষণ\n৩\nVE\n人人\nগতক\nThis figure displays two growth charts, one for girls (মেয়েদের ওজন বৃদ্ধির চার্ট) and one for boys (ছেলেদের ওজন বৃদ্ধির চার্ট), showing weight (ওজন (কিলোগ্রাম)) over time. The charts are color-coded with green for "বৃঠিকভাবে বাড়ছে" (growing correctly), yellow for "বীচের দিকে মানতে" (borderline), and red for "বিপদের লক্ষণ" (danger signs). Both charts include a section for "শিশুর জন্ম ওজন (কেজি)" (baby\'s birth weight (kg)).', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/8a81d672dae172e97c1df2dad890be6fb6c28bb36d4a4597b2afab56c52bde7a.png'}}]

### Card 6 (id: af1d5340-b054-436b-9cf5-bfc281e0fa16)
Title (bn): গ্রোথ চার্টের ফলাফল দেখে করণীয়
Body (bn): [{'type': 'paragraph', 'content': [{'text': "যদি দাগটি সবুজ রং এর ঘরে থাকে, তাহলে মাকে বলতে হবে যেভাবে শিশুকে যত্ন ও পরিচর্যা করছিলেন সেভাবেই করবেন। যদি দাগটি হালকা হলুদ বা গাঢ় হলুদ রং এর ঘরে থাকে (স্বল্প অপুষ্টি/ মাঝারি অপুষ্টি), সেক্ষেত্রে মাকে পরামর্শ দিতে হবে যে, ৬ মাস বয়স পর্যন্ত শিশুকে শুধুমাত্র বুকের দুধ খাওয়াতে হবে। ৭ মাস বয়স থেকে শিশুকে বুকের দুধের পাশাপাশি পারিবারিক খাবার বাড়তি খাবার হিসেবে দিতে হবে। প্রতিদিন শিশুকে অবশ্যই মাছ/মাংস/ডিম, শাক-সবজি, ঘন ডাল এবং ভাত খাওয়াতে হবে। সেই সাথে পুষ্টিকর নাস্তা (দুধের তৈরি খাবার এবং মৌসুমি ফল) খাওয়াতে হবে। ২ বছর বয়স পর্যন্ত শিশুকে বুকের দুধ খাওয়ানো চালিয়ে যেতে হবে। ৬ মাস পূর্ণ হওয়ার পর থেকে ৫ বছর বয়স পর্যন্ত শিশুদের পারিবারিক খাবারের সাথে 'পুষ্টিকণা' খাওয়াতে হবে। যদি দাগটি লাল রং এর ঘরে থাকে (মারাত্মক অপুষ্টি), তাহলে শিশুকে নিকটবর্তী হাসপাতালে চিকিৎসকের কাছে রেফার করতে হবে।", 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'A watercolor illustration shows a woman in a green sari sitting on a purple mat, breastfeeding a baby. The background features a woven wall and traditional clay pots.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/0b357899f83ae87b2a39f1dbf833b81bb4b2a604c59828d7edfa23df2f1dfc43.jpg'}}, {'type': 'image', 'attrs': {'alt': 'An illustration of a woman in a purple sari feeding a baby from a bowl. The woman is holding the baby on her lap and appears to be offering food with a spoon.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/2bb7aed0520f8c3c024fdd606d72d3c3f5f54981b40efb2726619953f2da0466.jpg'}}, {'type': 'image', 'attrs': {'alt': 'বাড়তি খাবারের সঙ্গে কমপক্ষে দুই বছর বয়স পর্যন্ত মায়ের দুধ খাওয়াতে হবে\n৬-৮ মাস পূর্ণ শিশুর খাবার ২৫০ মি.লি.\nবাটির ১/২ বাটি দিনে ২ বার + সঙ্গে\nপুষ্টিকর নাশতা ১-২ বার\n৯-১১ মাস পূর্ণ শিশুর খাবার\n২৫০ মি.লি. বাটির ১/২ বাটি\nদিনে ৩ বার + সঙ্গে\nপুষ্টিকর নাশতা\n১-২ বার\n১২-২৩ মাস পূর্ণ\nশিশুর খাবার\n২৫০ মি.লি. বাটির ১ বাটি\nদিনে ৩ বার + সঙ্গে\nপুষ্টিকর নাশতা ১-২ বার\nThe figure illustrates feeding guidelines for children from 6 months to 23 months, emphasizing continued breastfeeding up to two years alongside complementary foods. It shows three stages of child development (6-8 months, 9-11 months, 12-23 months) with corresponding food quantities, meal frequencies, and snack recommendations.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/e3c89f042c5f96d01d337d15a32c7a0ea2a30186d7e303c4f1c69dbc756b5895.jpg'}}]


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
