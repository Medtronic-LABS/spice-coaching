# Golden expansion prompt — malaria (batch 0/0)

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

DOMAIN: malaria
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
    "module_id": "eefe9cbd-a89e-4c61-a1da-bb54fd091571",
    "module_title": "ম্যালেরিয়া কী এবং এর জীবাণু",
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
      "6fa44741-a196-4f8c-a1a5-46d4510cecb7",
      "87fad262-44e6-4495-962e-0e7633eb3666",
      "eff2e0ec-5c72-41b5-ab9b-0bb6d6fd0c55",
      "e913229c-bdfe-4c65-af80-be947012af50",
      "a90ab753-7a28-4ee1-a0df-b584293a59c3",
      "81f8a19e-9e8d-43be-9ab5-1cc9e804bbdf",
      "83968078-f54d-4652-a517-224142ee0c04",
      "5f3c3659-d3b0-4ace-b4ed-0fd2b133c791",
      "6ac5fbdc-494d-4d3e-87a2-bbbd61c7c590",
      "bda7e012-24f5-45d7-b583-eaa64a81b833"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: ম্যালেরিয়া কী এবং এর জীবাণু
module_id: eefe9cbd-a89e-4c61-a1da-bb54fd091571
cards: 10

### Card 1 (id: 6fa44741-a196-4f8c-a1a5-46d4510cecb7)
Title (bn): ম্যালেরিয়া কী এবং এর জীবাণু
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ম্যালেরিয়া এক প্রকার সংক্রামক রোগ যা প্লাজমোডিয়াম প্রজাতির এক প্রকার পরজীবী দ্বারা সংগঠিত হয় এবং জ্বরের মাধ্যমে প্রকাশ পায়। এই রোগ স্ত্রী অ্যানোফিলিস মশার কামড়ের মাধ্যমে হয়ে থাকে। ম্যালেরিয়ার জীবাণুর নাম প্লাজমোডিয়াম যা অ্যানোফিলিস জাতীয় স্ত্রী মশার দ্বারা সংক্রমিত হয়। খাদ্যগ্রহণ, বংশবৃদ্ধি ও রোগ তৈরী করার ক্ষমতা অর্জনের জন্য প্লাজমোডিয়াম জীবাণুকে মানুষ ও মশার উপর নির্ভর করতে হয়। পৃথিবীতে পাঁচ ধরণের প্লাজমোডিয়াম জীবাণু দেখা যায়: প্লাজমোডিয়াম ফ্যালসিপেরাম, প্লাজমোডিয়াম ভাইভেক্স, প্লাজমোডিয়াম ওভালি, প্লাজমোডিয়াম ম্যালেরি এবং প্লাজমোডিয়াম নোলেসি। বাংলাদেশে মূলত প্লাজমোডিয়াম ফ্যালসিপেরাম ও প্লাজমোডিয়াম ভাইভেক্স এই দুই ধরণের জীবাণু দেখা যায়। এই দুটির মধ্যে প্লাজমোডিয়াম ফ্যালসিপেরাম জীবাণু অধিকাংশ ম্যালেরিয়া মৃত্যুর জন্য দায়ী।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'Malaria\n→102°F\nAn illustration depicting malaria, showing a mosquito, a thermometer indicating a fever of 102°F, and a sick person in bed holding a thermometer.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/36969ce41b4ab3c4f7e3e8ec4f7577d51ab009a76dd58cd8f59c18ac40953494.jpg'}}]

### Card 2 (id: 87fad262-44e6-4495-962e-0e7633eb3666)
Title (bn): ম্যালেরিয়া কীভাবে ছড়ায় এবং মশার বৈশিষ্ট্য
Body (bn): যখন একটি ম্যালেরিয়া রোগীকে মশা কামড় দেয় তখন রোগীর রক্তের সাথে সেই জীবাণু মশার পাকস্থলীতে বা পেটে চলে যায়। পরবর্তী সময়ে সেই মশা যখন সুস্থ মানুষের শরীরে কামড় দেয় তখন মশার লালাগ্রন্থী থেকে সেই জীবাণু মশার লালার মাধ্যমে সুস্থ মানুষের শরীরে প্রবেশ করে। এই সুস্থ মানুষ পরবর্তী সময়ে ম্যালেরিয়া রোগী হয়ে যায়। ম্যালেরিয়ার মশা সাধারণত সূর্যাস্ত থেকে সূর্যোদয় পর্যন্ত মানুষকে কামড়িয়ে থাকে। অ্যানোফিলিস জাতীয় স্ত্রী মশা সাধারণত স্থির বা ধীরগতিসম্পন্ন পরিষ্কার পানিতে ডিম পাড়ে ও বংশ বৃদ্ধি করে। কিউলেক্স মশা ময়লা পানিতে এবং এডিস মশা জমে থাকা পানিতে বংশ বৃদ্ধি করে।

### Card 3 (id: eff2e0ec-5c72-41b5-ab9b-0bb6d6fd0c55)
Title (bn): ম্যালেরিয়া প্রবণ জেলাসমূহ
Body (bn): বাংলাদেশের কক্সবাজার, চট্টগ্রাম, পাবর্ত্য চট্টগ্রাম (বান্দরবান, রাঙ্গামাটি, খাগড়াছড়ি), সিলেট, হবিগঞ্জ, মৌলভীবাজার, সুনামগঞ্জ, কুড়িগ্রাম, নেত্রকোণা, শেরপুর ও ময়মনসিংহ সহ এই 13টি জেলায় ম্যালেরিয়া বেশী হয়।

### Card 4 (id: e913229c-bdfe-4c65-af80-be947012af50)
Title (bn): ম্যালেরিয়া আক্রান্ত হওয়ার ঝুঁকিতে কারা আছেন
Body (bn): ম্যালেরিয়ার প্রকোপ আছে এমন অঞ্চলের বসবাসরত শিশু বিশেষত পাঁচ বছরের কম বয়সী শিশু, ম্যালেরিয়ার প্রকোপ আছে এমন অঞ্চলের বসবাসরত গর্ভবতী নারী বিশেষত প্রথম সন্তান সম্ভবা, কম ম্যালেরিয়ার প্রকোপ অঞ্চল বা একেবারেই ম্যালেরিয়া নেই এরূপ অঞ্চলে বসবাসরত জনগোষ্ঠী যারা ভ্রমণ বা জীবিকার প্রয়োজনে ম্যালেরিয়া প্রবণ অঞ্চলে আসেন, উচ্চ ম্যালেরিয়া প্রবণ বা ম্যালেরিয়া প্রকোপ অঞ্চলে বসবাসরত জনগোষ্ঠী যারা 6 মাস বা তার বেশী সময় যাবত কম ম্যালেরিয়ার প্রকোপ অঞ্চলে কিংবা একেবারেই ম্যালেরিয়া নেই এরূপ অঞ্চলে অবস্থান করে পুনরায় নিজেদের অঞ্চলে ফিরে আসেন, জুম চাষী, কাঠুরে, রাবার বা চা বাগানের কর্মী বা অন্যান্য যারা জীবিকার প্রয়োজনে ম্যালেরিয়া প্রবণ এলাকায় কয়েক সপ্তাহ বা মাস বাড়ির বাইরে খোলা জায়গায় রাত্রিযাপন করেন, এবং ম্যালেরিয়া প্রকোপ অঞ্চলে সীমান্ত অতিক্রম করে পার্শ্ববর্তী দেশে বা এলাকায় গমনকারী জনগোষ্ঠী, আইন শৃঙ্খলা কাজে নিয়োজিত বাহিনী, ধর্মীয় কাজে গমনকারী, পর্যটক ইত্যাদি ম্যালেরিয়া আক্রান্ত হওয়ার ঝুঁকিতে আছেন।

### Card 5 (id: a90ab753-7a28-4ee1-a0df-b584293a59c3)
Title (bn): ম্যালেরিয়ার সাধারণ উপসর্গ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ম্যালেরিয়ার প্রধান লক্ষণ হচ্ছে জ্বর। বর্তমানে জ্বর থাকতেও পারে আবার নাও থাকতে পারে। তবে জ্বরের ইতিহাস (বিগত 48 ঘন্টার মধ্যে জ্বর) থাকবে। তবে অন্যান্য অসুখেও এই ধরণের জ্বর হতে পারে যেমন: সর্দিকাশি, গলাব্যথা, কানপাকা, প্রস্রাবে জ্বালাপোড়া ইত্যাদি। ম্যালেরিয়া প্রবণ এলাকায় কোন রোগীর জ্বর থাকলে কিংবা জ্বরের ইতিহাস থাকলে এবং অন্য কোন রোগের লক্ষণ না থাকলে তাকে ম্যালেরিয়া বলে সন্দেহ করতে হবে। তাছাড়া, ম্যালেরিয়াপ্রবণ এলাকায় বসবাসরত কারো প্রচন্ড মাথাব্যথা, পেট ব্যথা বা ডায়রিয়া শুরু হলে বা কোন ব্যক্তি হঠাৎ অজ্ঞান হয়ে পড়লে ম্যালেরিয়া হয়েছে বলে সন্দেহ করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'A person holds their stomach, indicating abdominal pain, with a translucent overlay of the digestive system (intestines) highlighted in white lines and a red glow in the stomach area. The background is a plain light gray.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/adbea571d18a56d36890fc4c09e349433f8daeb1b6df1f63798feb2b5a1f4103.jpg'}}]

### Card 6 (id: 81f8a19e-9e8d-43be-9ab5-1cc9e804bbdf)
Title (bn): মারাত্মক ম্যালেরিয়ার লক্ষণ ও জটিলতাসমূহ
Body (bn): ম্যালেরিয়ার প্রধান উপসর্গ জ্বর। সাধারণ ম্যালেরিয়া জ্বরের সাথে জটিলতার কোন উপসর্গ যেমন: বমি, খিঁচুনী, অজ্ঞান হওয়া ইত্যাদি থাকে না। মারাত্মক ম্যালেরিয়া হলে জ্বরের সাথে কিছু জটিলতার উপসর্গ দেখা দেয়। যেমন: অজ্ঞান হওয়া, বমি হওয়া, খিঁচুনী, অস্বাভাবিক আচরণ, অত্যাধিক দূর্বলতা হেতু রোগী নিজে নিজে দাঁড়ানো বা হাঁটার অক্ষমতা, জন্ডিস, শ্বাসকষ্ট, মারাত্মক রক্তস্বল্পতা, প্রস্রাবের পরিমাণ কমে যাওয়া, শিশু মায়ের দুধ চুষতে বা টানতে না পারা। জ্বরের সাথে উপরের উপসর্গগুলোর কমপক্ষে যেকোন একটি থাকলে তাকে মারাত্মক ম্যালেরিয়া বলে। মারাত্মক ম্যালেরিয়ার জটিলতাসমূহ হলো আচরণের পরিবর্তন, অচেতনতা বা অজ্ঞান হওয়া, খিঁচুনী, শ্বাস প্রশ্বাস গভীর এবং কষ্টকর হওয়া, প্রস্রাবের পরিমাণ কমে যাওয়া ও পরবর্তী সময়ে বন্ধ হয়ে যাওয়া, মারাত্মক রক্তস্বল্পতা, প্রস্রাবে রক্তে লাল কোষ পাওয়া যাওয়া, জন্ডিস, রক্তপাতের প্রবণতা এবং অত্যধিক দুর্বলতা।

### Card 7 (id: 83968078-f54d-4652-a517-224142ee0c04)
Title (bn): ম্যালেরিয়া সনাক্তকরণ পরীক্ষা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ম্যালেরিয়া রোগ নিশ্চিত হওয়ার জন্য মানুষের শরীরের রক্ত পরীক্ষা করতে হয়। ম্যালেরিয়া জীবাণু নিশ্চিত হওয়ার জন্য 2 ধরণের রক্ত পরীক্ষা করতে হয়: রক্ত কাচ পরীক্ষা এবং দ্রুত সনাক্তকরণ পরীক্ষা বা আর.ডি.টি।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'brac\nAn illustration of a healthcare worker in a white coat performing a finger-prick test on a seated woman, with medical supplies and a book on a table.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/41955a4c7b2bfe67b4cec93d332cea5eec9dbcfcf350cbafd1d4a22e31c4b919.jpg'}}]

### Card 8 (id: 5f3c3659-d3b0-4ace-b4ed-0fd2b133c791)
Title (bn): ম্যালেরিয়া রোগের চিকিৎসা ও রেফারেল পদ্ধতি
Body (bn): স্বাস্থ্যসেবিকা, স্বাস্থ্যকর্মী ও প্রজেক্ট এসিসট্যান্ট ম্যালেরিয়ার যেকোন লক্ষণ আছে এমন রোগীদের নিশ্চিতকরণ পরীক্ষা করে চিকিৎসা শুরু করবেন। মারাত্মক ম্যালেরিয়ার যেকোন লক্ষণ দেখা দিলে উপজেলা স্বাস্থ্য কেন্দ্র, জেলা সদর হাসপাতাল, সরকারি হাসপাতাল এ রেফার করতে হবে।

### Card 9 (id: 6ac5fbdc-494d-4d3e-87a2-bbbd61c7c590)
Title (bn): মশার কামড় থেকে আত্মরক্ষার উপায়
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ম্যালেরিয়া প্রতিরোধের উল্লেখযোগ্য ব্যবস্থার মধ্যে মশার কামড় থেকে আত্মরক্ষা করা একটি গুরুত্বপূর্ণ উপায়। মশার কামড় থেকে আত্মরক্ষার উপায়গুলি হচ্ছে: কীটনাশকযুক্ত মশারি (ITN) প্রতিদিন সন্ধ্যা হওয়ার সঙ্গে সঙ্গে টানানো ও ব্যবহার করা। জুম চাষ করতে বা বনে বাঁশ বা কাঠ কাটতে বাড়ির বাইরে অবস্থান বা রাত্রিযাপন করতে হলে ঘুমানোর সময় কীটনাশকযুক্ত মশারি (ITN) ব্যবহার করা। মশা তাড়াবার ধোঁয়া, স্প্রে ইত্যাদি ব্যবহার করা। যতটুক সম্ভব শরীর ঢেকে রাখা (ফুল হাতা শার্ট পরিধান ইত্যাদি)। সম্ভব হলে শরীরে অনাবৃত অংশে মশা বিতারক ক্রীম বা লোশন এবং শোবার ঘরে দরজা জানালায় মশা প্রতিবন্ধক জাল (Mosquito Proof Net) ব্যবহার করা।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a person sleeping in a bed covered by a mosquito net. The person is lying on their back under a blanket.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/b522d6fefa397a56374416cad48809939daca8a9e9f14234803df242e04b1caf.jpg'}}]

### Card 10 (id: bda7e012-24f5-45d7-b583-eaa64a81b833)
Title (bn): মশার জন্ম ও বংশবিস্তার রোধের ব্যবস্থা
Body (bn): ম্যালেরিয়া প্রতিরোধের জন্য মশার জন্ম ও বংশবিস্তার রোধ করা জরুরি। এর জন্য ব্যবস্থাগুলি হলো: আবদ্ধ জলাশয় যেমন অপ্রয়োজনীয় ডোবা, গর্ত, নর্দমা ইত্যাদি (যেখানে মশা ডিম পাড়ে ও বংশবিস্তার ঘটায়) ভরাট করে ফেলা। স্থায়ী আবদ্ধ জলাশয়ে শুককীট খেকো মাছ (যেমন: তেলাপিয়া, নাইলোটিকা, কার্প, গাপ্পী) চাষ করা ও পানির কিনারায় ঘাস পরিষ্কার করা। বিশেষ ক্ষেত্রে মশা ধ্বংসকারী কীটনাশক ছিটিয়ে মশা ধ্বংস করা। বসতবাড়ী ও চারপাশে বেড়ে উঠা অপ্রয়োজনীয় ঝোপঝাড় কেটে পরিষ্কার করা।


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
