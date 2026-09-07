# Golden expansion prompt — tuberculosis (batch 0/0)

Expected records: 12

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

DOMAIN: tuberculosis
Generate exactly 12 new golden records distributed per the generation plan.

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
    "module_id": "0e8bfcef-699b-4900-8814-0516ab815dae",
    "module_title": "যক্ষ্মা কী এবং এর প্রকারভেদ",
    "record_count": 12,
    "suggested_query_types": [
      "Factual",
      "Situational",
      "Procedural",
      "Referral Decision",
      "Factual",
      "Procedural",
      "Cross-card Synthesis",
      "Counseling",
      "Drug / Dosage",
      "Situational",
      "Factual",
      "Situational"
    ],
    "card_ids": [
      "a99a2a76-f3fd-46dc-94a8-237e1756f9fd",
      "bdd7a381-ba4e-4cd0-90ff-ce4ce07386b6",
      "1ec4f954-51f8-4580-9a4e-489437eaadee",
      "edf3c5ca-2a08-4581-a940-769f38b4d5af",
      "a11942a3-a808-4126-83e8-294e5eb7760e",
      "45b4890d-1df6-413e-bccb-9ca6570b39c7",
      "5a0c8af9-3c8e-4af2-8734-5979ce7966a7",
      "8395d8be-770a-40fa-82f0-521b7e2e2a24",
      "92a66443-4992-4948-bbe0-26281287ef44",
      "3cadd84e-5c56-4c4b-acdd-7ee9a9c8e141"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: যক্ষ্মা কী এবং এর প্রকারভেদ
module_id: 0e8bfcef-699b-4900-8814-0516ab815dae
cards: 10

### Card 1 (id: a99a2a76-f3fd-46dc-94a8-237e1756f9fd)
Title (bn): যক্ষ্মা কী এবং এর প্রকারভেদ
Body (bn): যক্ষ্মা একটি জীবাণুঘটিত মারাত্মক সংক্রামক রোগ। যা আক্রান্ত ব্যক্তির শরীর থেকে সুস্থ ব্যক্তির শরীরে যায়। মাইকোব্যাকটেরিয়াম টিউবারকুলোসিস নামক যক্ষ্মার জীবাণু এই রোগ ঘটায়। ফুসফুস, গ্রন্থি, হাড় ও অন্ত্রসহ শরীরের বিভিন্ন অংশে যক্ষ্মা হতে পারে। শরীরের অবস্থান অনুযায়ী যক্ষ্মাকে দুই ভাগে ভাগ করা হয়: ফুসফুসের যক্ষ্মা এবং ফুসফুস বহির্ভূত যক্ষ্মা। ফুসফুস ছাড়া শরীরের অন্য কোন স্থানে যক্ষ্মা যেমন ফুসফুসের আবরণী, গ্রন্থি, হাড়, মস্তিষ্কের আবরণী, অস্ত্র ইত্যাদিকে ফুসফুস বহির্ভূত যক্ষ্মা বলে। ফুসফুসের যক্ষ্মা আবার দুই প্রকার: কফে জীবাণুযুক্ত ফুসফুসের যক্ষ্মা (এসব রোগীর কফ পরীক্ষার মাধ্যমে জীবাণু পাওয়া যায় এবং এরা সংক্রামক রোগী) এবং কফে জীবাণুমুক্ত ফুসফুসের যক্ষ্মা (এসব রোগীর কফ পরীক্ষায় জীবাণু পাওয়া যায় না, পরবর্তী সময়ে এক্স-রে দ্বারা চিহ্নিত হয় এবং এরা সাধারণত অ-সংক্রামক রোগী)। ফুসফুস বহির্ভূত যক্ষ্মা সাধারণত সংক্রামক নয়। দাঁত, চুল, নখ ছাড়া শরীরের সব জায়গায় যেমন ফুসফুস, হাড়, কিডনি, জরায়ু, গ্রন্থি, পাকস্থলি ও শরীরের বিভিন্ন জায়গায় যক্ষ্মা হতে পারে।

### Card 2 (id: bdd7a381-ba4e-4cd0-90ff-ce4ce07386b6)
Title (bn): যক্ষ্মার লক্ষণ এবং এটি কিভাবে ছড়ায়
Body (bn): যক্ষ্মার প্রধান লক্ষণ হলো একনাগাড়ে দুই সপ্তাহ বা তার বেশি সময় ধরে কাশি (কাশির সাথে রক্ত থাকুক বা না থাকুক)। এছাড়াও নিচের লক্ষণগুলো দেখা যেতে পারে: ওজন কমে যাওয়া এবং শরীর দিন দিন দুর্বল হয়ে যাওয়া, বিকালের দিকে অল্প অল্প জ্বর আসা এবং রাতে শরীর ঘেমে জ্বর ছেড়ে যাওয়া, খাবারে অরুচি, শ্বাসকষ্ট এবং বুকে অথবা পিঠের উপরের অংশে ব্যথা। যক্ষ্মারোগীর হাঁচি ও কাশির মাধ্যমে যক্ষ্মার জীবাণু বের হয়ে বাতাসে মেশে এবং শ্বাস প্রশ্বাসের মাধ্যমে তা সুস্থ ব্যক্তির ফুসফুসে প্রবেশ করে ও বংশবৃদ্ধি করে। সংক্রমিত লোকদের শতকরা দশ ভাগই এ রোগে আক্রান্ত হতে পারে। এটি একটি মারাত্মক সংক্রামক রোগ এবং একজন পজেটিভ রোগী (যার হাঁচি বা কাশির সাথে জীবাণু বের হয়) বছরে আরও দশ জন লোককে আক্রান্ত করে। বাংলাদেশে যক্ষ্মা প্রাপ্তবয়স্ক মৃত্যুর ক্ষেত্রে একটি অন্যতম ঘাতক ব্যাধি যা প্রতি বছর বহু লোকের মৃত্যু ঘটায়।

### Card 3 (id: 1ec4f954-51f8-4580-9a4e-489437eaadee)
Title (bn): যক্ষ্মা রোগী চিহ্নিত করার উপায় এবং কফ সংগ্রহের নিয়ম
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যক্ষ্মা রোগী চিহ্নিত করার উপায় হলো কফ পরীক্ষা করে এবং বুকের এক্স-রে করে। কফ সংগ্রহের নিয়ম হলো সন্দেহজনক রোগীকে মোট দুই বার কফ দিতে হবে। প্রথমত, সকালে ঘুম থেকে উঠে মুখ ধোয়ার আগে একটি পটে কফ রাখতে হবে (সকালের কফ)। দ্বিতীয়ত, ল্যাবরেটরিতে বা স্মিয়ারিং সেন্টারে এসে আরও একটি পটে কফ দিতে হবে (স্পট কফ)। কফ বের করার জন্য রোগী পেছনে হাত রেখে গভীরভাবে শ্বাস নিয়ে বুকের গভীর থেকে কফ বের করতে হবে। মুখ থেকে থুতু দিলে হবে না। খোলা জায়গায় বাতাসের বিপরীতে মুখ করে কফ বের করতে হবে। খোলা স্থানে এবং লোকজন থেকে নিরাপদ দূরত্বে রোগী নির্দিষ্ট পাত্রে কফ সংগ্রহ করবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'কফ পরীক্ষা কেন্দ্র\nThe figure shows two identical illustrations of a man holding a cup, with a sun in the sky on the left and the text "কফ পরীক্ষা কেন্দ্র" (Sputum Test Center) on the right.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/c7beeff5405b7d5bb12c6426ba0af2ac530ed36fc601428d430c1d36221bc233.png'}}]

### Card 4 (id: edf3c5ca-2a08-4581-a940-769f38b4d5af)
Title (bn): কোথায় কফ পরীক্ষা করা হয় এবং যক্ষ্মা ধরা পড়লে করণীয়
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'কফ পরীক্ষা করা হয় সকল উপজেলা স্বাস্থ্যকেন্দ্র, সকল বক্ষব্যাধি ক্লিনিক ও হাসপাতাল, জেলা সদর হাসপাতাল, বিশেষায়িত হাসপাতাল, কমিউনিটি ক্লিনিক, নির্দিষ্ট এনজিও ক্লিনিক, সম্মিলিত সামরিক হাসপাতাল, সকল ইপিজেড, ফ্যাক্টরি, বিজিএমআই, বিকেএমআই এবং কারাগারসমূহে। যক্ষ্মা রোগ ধরা পড়লে দ্রুত চিকিৎসা শুরু করতে হবে। নিয়মিত এবং পূর্ণ মেয়াদে সেবিকার সামনে ওষুধ সেবন করতে হবে। চিকিৎসা চলাকালীন সময় রোগের অবস্থা বোঝার জন্য কফ পরীক্ষা করাতে হবে। যেখানে সেখানে কফ বা থুথু ফেলা যাবে না, রোগীর কফ, থুথু নির্দিষ্ট পাত্রে ফেলে পরে তা পুঁতে বা পুড়িয়ে ফেলতে হবে। হাঁচি, কাশির সময় রোগীকে মুখে রুমাল অথবা কাপড় ব্যবহার করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'জাতীয় যক্ষা নিয়ন্ত্রণ কর্মসূচি\nকফ সংগ্রহ ও পরীক্ষা কেন্দ্র\nআয়োজনে: ব্র্যাক\nA cartoon illustration depicts a woman in a lab coat at a table with a microscope and sample containers, speaking to a man. Behind them is a yellow banner with Bengali text.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/b11d6bc94ce1798aad3132b7db1e0460318e9d2936ad03f8cd5260b763bbf5ce.jpg'}}]

### Card 5 (id: a11942a3-a808-4126-83e8-294e5eb7760e)
Title (bn): যক্ষ্মার চিকিৎসায় রোগীর ধরণ
Body (bn): যক্ষ্মার চিকিৎসায় রোগীকে দুই ধরণের শ্রেণীতে ভাগ করা হয়: নতুন রোগী এবং পুরাতন রোগী। নতুন রোগী হলো কফে জীবাণুযুক্ত নতুন রোগী এবং যিনি কখনো যক্ষ্মার চিকিৎসা নেননি অথবা এক মাসের কম সময় ধরে চিকিৎসা করেছেন। এছাড়াও কফ পরীক্ষায় নেগেটিভ কিন্তু এক্স-রে দ্বারা চিহ্নিত নতুন রোগী এবং ফুসফুস বহির্ভূত নতুন যক্ষ্মা রোগীও নতুন রোগীর অন্তর্ভুক্ত। পুরাতন রোগী হলো যারা যক্ষ্মার চিকিৎসা গ্রহণের পর সুস্থ হয়েছিলেন কিন্তু পরবর্তীতে আবার যক্ষ্মা রোগী হিসাবে চিহ্নিত হয়েছেন। যেসব রোগী পূর্বে চিকিৎসায় এক মাসের বেশি যক্ষ্মার ঔষধ খেয়েছে, দুই থেকে পাঁচ মাস চিকিৎসা করার পর কফে জীবাণু পাওয়া গেছে এমন রোগী বা চিকিৎসা ফেইলর রোগী, এবং ট্রিটমেন্ট আফটার লস্ট টু ফলোআপ বা অন্যান্য রোগীও পুরাতন রোগীর অন্তর্ভুক্ত।

### Card 6 (id: 45b4890d-1df6-413e-bccb-9ca6570b39c7)
Title (bn): ডট (DOT) কী এবং এর কৌশলসমূহ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ডট (DOT) হলো রোগী নিয়মিত ডাক্তার, স্বাস্থ্যকর্মী বা স্বাস্থ্য সেবিকার সামনে সরাসরি পর্যবেক্ষণের মাধ্যমে চিকিৎসার পুরো মেয়াদে ওষুধ সেবন করা। ডট এর কৌশলসমূহ হলো: মাঠ কার্যক্রমে ফিল্ড অর্গানাইজার (FO) এবং কমিউনিটি হেলথ ওয়ার্কার (CHW) দের কাজে সহযোগিতা করা। সম্ভাব্য যক্ষ্মা রোগীর কফ সংগ্রহ করা এবং টিউবারকুলোসিস ডায়াগনোসিস সেন্টার (TDC) তে রোগী রেফার করা। যক্ষ্মা ধরা পড়লে ডটস পদ্ধতিতে চিকিৎসা প্রদান করা। ওষুধ সেবনের পর যদি কোন রোগীর পার্শ্ব-প্রতিক্রিয়া দেখা দেয় তাহলে অফিসে যোগাযোগ করা এবং রোগী রেফার করা। নিয়মিত রিফ্রেসার্সে অংশগ্রহণ করা। সকল ক্যাটাগরিতেই ইনটেনসিভ ফেজে এবং কন্টিনিউয়েশন ফেজে প্রতিদিন সকালে খালি পেটে রোগী সেবিকার বাড়িতে এলে স্বাস্থ্যসেবিকা তাকে সেবন বিধি মোতাবেক ওষুধ খাইয়ে দিবেন। যদি কোন নির্দিষ্ট দিনে রোগী সেবিকার বাড়িতে না আসে তবে সঙ্গে সঙ্গে সেবিকা রোগীর বাড়িতে গিয়ে, খোঁজ নিয়ে অনুপস্থিতির কারণ জেনে সমস্যা সমাধান করে ঐ দিনের ওষুধ খাইয়ে দেবেন। পার্শ্ব প্রতিক্রিয়ার খবর পাওয়ার পরপরই রোগীকে সঙ্গে সঙ্গে নিকটস্থ স্বাস্থ্যকেন্দ্রে রেফার করতে হবে অথবা ব্র্যাক পিওকে জানাতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration depicts a young man taking a pill with a glass of water in his hand, while an older woman in a sari stands beside him, looking on.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/6d14692a4b0be7b4cb38b0a96e35e6648668e2a1ab3c20268b119c308e10ed7a.jpg'}}]

### Card 7 (id: 5a0c8af9-3c8e-4af2-8734-5979ce7966a7)
Title (bn): ডট পদ্ধতিতে চিকিৎসার তথ্য সংরক্ষণ
Body (bn): সেবিকা ডট পদ্ধতিতে চিকিৎসার তথ্য সংরক্ষণ করবেন। রোগী নিয়মমাফিক ওষুধ খাওয়ার পর কার্ডের নির্দিষ্ট তারিখের ঘরে টিক চিহ্ন (√) দেবেন। রোগী যদি কোনদিন কোন কারণে ওষুধ না খায় তবে চিকিৎসা কার্ডে ঐ তারিখের ঘরে শূন্য (০) চিহ্ন দেবেন। মনে রাখবেন কার্ডে তথ্য সংরক্ষণ অত্যন্ত জরুরী।

### Card 8 (id: 8395d8be-770a-40fa-82f0-521b7e2e2a24)
Title (bn): যক্ষ্মার ওষুধের পার্শ্বপ্রতিক্রিয়া
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যক্ষ্মার ওষুধ খেলে রোগীর প্রস্রাবের রং কমলা বা লাল হলে ভয়ের কোন কারণ নেই, ওষুধ শেষ হলে প্রস্রাব আবার আগের মতো হয়ে যাবে। এছাড়াও কিছু কিছু মারাত্মক সমস্যা হতে পারে যা হলে সরাসরি হাসপাতালে যেতে হবে। কোন কোন গুরুতর পার্শ্ব-প্রতিক্রিয়া হলে সঙ্গে সঙ্গে হাসপাতালে যেতে হবে: চোখে ঝাপসা দেখলে, কানে ভোঁভোঁ করলে, চোখ হলুদ হয়ে গেলে, খেতে না পারলে, বমি হলে (জন্ডিস), রোগী অস্বাভাবিক আচরণ করলে, পেটে তীব্র ব্যথা হলে, প্রস্রাব বন্ধ হয়ে গেলে, চামড়ার নিচে লাল লাল চাকা হলে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'A person holds their stomach, indicating abdominal pain, with a translucent overlay of the digestive system (intestines) highlighted in white lines and a red glow in the stomach area. The background is a plain light gray.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/adbea571d18a56d36890fc4c09e349433f8daeb1b6df1f63798feb2b5a1f4103.jpg'}}]

### Card 9 (id: 92a66443-4992-4948-bbe0-26281287ef44)
Title (bn): যক্ষ্মা প্রতিরোধে পরামর্শ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যক্ষ্মা প্রতিরোধে যক্ষ্মারোগী এবং তার পরিবারের সদস্যদের কিছু পরামর্শ দিতে হবে। চিকিৎসা চলাকালীন রোগী পরিবারের সদস্যদের সঙ্গে স্বাভাবিক জীবনযাপন করতে পারে। হাঁচি-কাশির মাধ্যমে যক্ষ্মারোগ ছড়ায়, তাই মুখ কাপড়ে ঢেকে হাঁচি-কাশি দিতে হবে। যেখানে-সেখানে কফ না ফেলে নির্দিষ্ট পাত্রের মধ্যে ফেলে মাটিতে পুঁতে ফেলতে হবে। পরিবারের একজন রোগী হলে সেই পরিবারের অন্য কারও কাশি হলেই কফ পরীক্ষা করাতে হবে। জন্মের পরপরই শিশুকে বিসিজি টিকা দিতে হবে। রোগীর কোন সমস্যা হলে সেবিকাকে জানাতে হবে অথবা দ্রুত হাসপাতালে যেতে হবে। যক্ষ্মারোগ আক্রান্ত মা যদি নিয়মিত চিকিৎসা নিতে থাকেন তবে শিশুকে বুকের দুধ খাওয়াতে পারবেন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a person in a purple shirt sneezing or blowing their nose into a yellow handkerchief.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/a3cef5d56ff390f06d19c369d14c8ade9a8fd56a94ddb744c8b0fdb51157ee7b.jpg'}}, {'type': 'image', 'attrs': {'alt': 'মাস্ক ব্যবহার\nমাস্ক ব্যবহার করুন, সুস্থ থাকুন\nMASK USAGE\nUse mask, stay healthy\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক পরুন\nমাস্ক…', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/bf7905339ffcb67cec59b057872e48d7feb03372ea00f229f67961fb2d1d16d0.jpg'}}]

### Card 10 (id: 3cadd84e-5c56-4c4b-acdd-7ee9a9c8e141)
Title (bn): যক্ষ্মা কর্মসূচিতে CHW এর দায়িত্ব ও কর্তব্য
Body (bn): যক্ষ্মা কর্মসূচিতে কমিউনিটি হেলথ ওয়ার্কার (CHW) এর কাজ হলো প্রতিদিন সকাল আটটা ত্রিশ মিনিটের মধ্যে নির্দিষ্ট কর্ম এলাকায় উপস্থিত হয়ে সেবিকাকে সাথে নিয়ে খানা পরিদর্শন করে সম্ভাব্য যক্ষ্মা রোগীর কফ সংগ্রহ করা। টিউবারকুলোসিস ডায়াগনোসিস সেন্টার (TDC) তে রোগী রেফার করা। যেখানে TDC নেই সেখানে স্মেয়ারিং সেন্টারে রোগী রেফার করা।


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
