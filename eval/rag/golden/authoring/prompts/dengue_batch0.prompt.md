# Golden expansion prompt — dengue (batch 0/0)

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

DOMAIN: dengue
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
    "module_id": "cd582b9e-f7e0-48fe-baaf-af0a8b74a162",
    "module_title": "ডেঙ্গু র‍্যাপিড ডায়াগনস্টিক টেস্ট (RDT) কিট ব্যবহারের প্রস্তুতি",
    "record_count": 6,
    "suggested_query_types": [
      "Factual",
      "Situational",
      "Procedural",
      "Referral Decision",
      "Factual",
      "Procedural"
    ],
    "card_ids": [
      "036086d7-3020-4398-b7de-dcf7a869ffcc",
      "fc5b8d54-21c1-4ad1-8f52-f81c8c9032dc",
      "0e9076bf-6d24-4365-9175-907cbecdce56",
      "b2040cef-e132-49f0-baa7-1bb12d93afab"
    ]
  },
  {
    "module_id": "3225755c-2c2a-405c-b043-8690a0b9975e",
    "module_title": "ডেঙ্গু র‍্যাপিড ডায়াগনোস্টিক টেস্ট (RDT) কী?",
    "record_count": 6,
    "suggested_query_types": [
      "Cross-card Synthesis",
      "Counseling",
      "Drug / Dosage",
      "Situational",
      "Factual",
      "Situational"
    ],
    "card_ids": [
      "3eecdf33-3fb5-4a1f-9ce7-d6f9916f4651",
      "938fc837-22de-4294-ab35-0087ad2f36d1",
      "c04f4186-1c01-4458-bf7d-8bf5e868b0b3",
      "405c0231-bdca-4a61-a117-8e908d70b061",
      "7c5122e3-ca93-4175-89fa-23603a844984"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: ডেঙ্গু র‍্যাপিড ডায়াগনস্টিক টেস্ট (RDT) কিট ব্যবহারের প্রস্তুতি
module_id: cd582b9e-f7e0-48fe-baaf-af0a8b74a162
cards: 4

### Card 1 (id: 036086d7-3020-4398-b7de-dcf7a869ffcc)
Title (bn): ডেঙ্গু র‍্যাপিড ডায়াগনস্টিক টেস্ট (RDT) কিট ব্যবহারের প্রস্তুতি
Body (bn): ডেঙ্গু র‍্যাপিড ডায়াগনস্টিক টেস্ট (RDT) কিট ব্যবহারের আগে নিশ্চিত করুন যে কিটটি ঘরের তাপমাত্রায় আছে। যদি কিটটি ফ্রিজে রাখা থাকে, তবে ব্যবহারের কমপক্ষে 30 মিনিট আগে ফ্রিজ থেকে বের করে ঘরের তাপমাত্রায় আনুন। কিটটি খোলার আগে প্যাকেটের মেয়াদ উত্তীর্ণের তারিখ পরীক্ষা করুন। মেয়াদ উত্তীর্ণ কিট ব্যবহার করবেন না। কিটটি খোলার পর যত দ্রুত সম্ভব ব্যবহার করুন।

### Card 2 (id: fc5b8d54-21c1-4ad1-8f52-f81c8c9032dc)
Title (bn): ডেঙ্গু র‍্যাপিড ডায়াগনস্টিক টেস্ট (RDT) কিট ব্যবহারের পদ্ধতি
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'প্রথমে রোগীর আঙুল থেকে রক্ত সংগ্রহ করুন। সংগৃহীত রক্তের এক ফোঁটা কিটের গোলাকার গর্তে (স্যাম্পল ওয়েল) দিন। এরপর বাফার সলিউশনের দুই ফোঁটা একই গোলাকার গর্তে দিন। 15 থেকে 20 মিনিট অপেক্ষা করুন। এই সময়ের মধ্যে ফলাফল দেখা যাবে। 20 মিনিটের বেশি সময় ধরে ফলাফল দেখলে তা সঠিক নাও হতে পারে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'Square hole\n(for blood)\nResults window\nRound hole\n(for buffer)\nC\nA\nC- control line\nT- test line\nA diagram of a rapid diagnostic test cassette, showing the square hole for blood, the round hole for buffer, the results window, and the control and test lines.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/a705bc4ec9550f274df5a77c85737ecc70aaef8195b6561dfd8592b46046a273.jpg'}}, {'type': 'image', 'attrs': {'alt': 'brac\nAn illustration of a healthcare worker in a white coat performing a finger-prick test on a seated woman, with medical supplies and a book on a table.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/41955a4c7b2bfe67b4cec93d332cea5eec9dbcfcf350cbafd1d4a22e31c4b919.jpg'}}]

### Card 3 (id: 0e9076bf-6d24-4365-9175-907cbecdce56)
Title (bn): ডেঙ্গু র‍্যাপিড ডায়াগনস্টিক টেস্ট (RDT) ফলাফলের ব্যাখ্যা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যদি কন্ট্রোল লাইন (C) এবং টেস্ট লাইন (T) উভয় স্থানেই রেখা দেখা যায়, তবে ফলাফল পজিটিভ। যদি শুধুমাত্র কন্ট্রোল লাইন (C) স্থানে রেখা দেখা যায়, তবে ফলাফল নেগেটিভ। যদি কন্ট্রোল লাইন (C) স্থানে কোনো রেখা না দেখা যায়, তবে পরীক্ষাটি অকার্যকর হয়েছে এবং পুনরায় পরীক্ষা করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'Square hole\n(for blood)\nResults window\nRound hole\n(for buffer)\nC\nA\nC- control line\nT- test line\nA diagram of a rapid diagnostic test cassette, showing the square hole for blood, the round hole for buffer, the results window, and the control and test lines.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/a705bc4ec9550f274df5a77c85737ecc70aaef8195b6561dfd8592b46046a273.jpg'}}, {'type': 'image', 'attrs': {'alt': 'A white rectangular area is centered on a pink background. The pink background is visible on the top, left, and right sides of the white rectangle, with some curved shapes on the top right and bottom right.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/4d2a73d5bce755476d72827eb9ee9521c204939b933b59d422f1b6282373b8bc.png'}}, {'type': 'image', 'attrs': {'alt': 'A white rectangular background with two vertical pink bars on the left and right edges.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/d21817ba81549fc6fd0c6a12bb832ce480a19f9b5e4681f1b8fae11e0baf6da7.png'}}, {'type': 'image', 'attrs': {'alt': 'A blank white rectangular area with a pink border on the left and bottom, and a partial pink border with curved edges on the top-left and bottom-right corners.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/2c4d83b77d0c7d1012ffe7e8b96c5f83e7904b2e100861f2539df1496fe638ec.png'}}]

### Card 4 (id: b2040cef-e132-49f0-baa7-1bb12d93afab)
Title (bn): ডেঙ্গু প্রতিরোধের উপায়
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ডেঙ্গু প্রতিরোধের জন্য মশার প্রজনন স্থান ধ্বংস করতে হবে। মশার কামড় থেকে বাঁচতে মশারি ব্যবহার করুন। দিনের বেলায়ও মশারি ব্যবহার করা উচিত, কারণ ডেঙ্গু মশা দিনের বেলায় কামড়ায়। মশা তাড়ানোর স্প্রে বা লোশন ব্যবহার করুন। বাড়ির আশেপাশে পানি জমতে দেবেন না এবং নিয়মিত পরিষ্কার রাখুন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a person sleeping in a bed covered by a mosquito net. The person is lying on their back under a blanket.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/b522d6fefa397a56374416cad48809939daca8a9e9f14234803df242e04b1caf.jpg'}}]

## Module: ডেঙ্গু র‍্যাপিড ডায়াগনোস্টিক টেস্ট (RDT) কী?
module_id: 3225755c-2c2a-405c-b043-8690a0b9975e
cards: 5

### Card 1 (id: 3eecdf33-3fb5-4a1f-9ce7-d6f9916f4651)
Title (bn): ডেঙ্গু র‍্যাপিড ডায়াগনোস্টিক টেস্ট (RDT) কী?
Body (bn): র‍্যাপিড ডায়াগনোস্টিক টেস্ট বা আরডিটি হলো দ্রুত সনাক্তকরণ পরীক্ষা। এই পরীক্ষার মাধ্যমে ডেঙ্গু এনএস-১ এন্টিজেন, আইজিজি এবং আইজিএম সনাক্ত করা যায়।

### Card 2 (id: 938fc837-22de-4294-ab35-0087ad2f36d1)
Title (bn): ডেঙ্গু আরডিটি পরীক্ষার জন্য প্রয়োজনীয় উপকরণ
Body (bn): ডেঙ্গু আরডিটি পরীক্ষার জন্য ক্যাসেট, সুঁই বা লেনসেট, ল্যানসিং যন্ত্র, তুলা, হেক্সিসল এবং ডেঙ্গু এন্টিজেন বাফার সলুশন প্রয়োজন।

### Card 3 (id: c04f4186-1c01-4458-bf7d-8bf5e868b0b3)
Title (bn): ডেঙ্গু আরডিটি পরীক্ষা করার পদ্ধতি
Body (bn): প্রথমে হেক্সিসল দিয়ে পরীক্ষার জন্য নির্ধারিত আঙুলটি তুলা দিয়ে মুছে নিন এবং আঙুলটি শুকানোর জন্য এক মিনিট অপেক্ষা করুন। এরপর লেনসেট হোল্ডারে লেনসেটটি সেট করুন এবং গভীরতা নির্ণায়ক চার এ নির্ধারিত করুন। কুকিং ব্যারেল টান দিয়ে লেনসেটটি সেট করুন। ক্যাসেটটি ও ড্রপারটি বের করুন। পিছনে চার আঙুল ও সামনে বৃদ্ধাঙ্গুল দিয়ে তর্জনীকে চাপ দিয়ে ধরুন। লেনসিং যন্ত্রটি খাড়া করে ধরে আঙ্গুলের চামড়ায় স্পর্শ করুন। রিলিজ বাটনে চাপ দিন এবং আঙ্গুল চেপে মাত্র পাঁচ ফোটা রক্ত ড্রপারটিতে সংগ্রহ করুন। ক্যাসেটটির রক্ত শোষণের স্থানে তিন ফোটা রক্তের নমুনা রাখুন এবং এক ফোটা ডেঙ্গু এন্টিজেন বাফার সলুশনটি দিন। এবার দশ মিনিট অপেক্ষা করুন।

### Card 4 (id: 405c0231-bdca-4a61-a117-8e908d70b061)
Title (bn): ডেঙ্গু আরডিটি ফলাফল বিশ্লেষণ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ক্যাসেটটির কন্ট্রোল অংশে একটি লাল রঙের দাগ দেখা দিলে বুঝতে হবে পরীক্ষাটি কাজ করছে। যদি ক্যাসেটটির কন্ট্রোল অংশে একটি লাল রঙের দাগ এবং টেস্ট অংশে একটি লাল রঙের দাগ, মোট দুইটি দাগ দেখা যায়, তাহলে বুঝতে হবে ডেঙ্গু পজিটিভ।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'Square hole\n(for blood)\nResults window\nRound hole\n(for buffer)\nC\nA\nC- control line\nT- test line\nA diagram of a rapid diagnostic test cassette, showing the square hole for blood, the round hole for buffer, the results window, and the control and test lines.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/a705bc4ec9550f274df5a77c85737ecc70aaef8195b6561dfd8592b46046a273.jpg'}}]

### Card 5 (id: 7c5122e3-ca93-4175-89fa-23603a844984)
Title (bn): ডেঙ্গু প্রতিরোধে করণীয়
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ডেঙ্গু প্রতিরোধে বাড়ির চারপাশ পরিষ্কার রাখুন। তিন দিনে এক দিন জমা পানি ফেলে দিন। ঘরের বাইরে ও ভেতরে কোন কৌটা বা ভাঙা হাড়ি, টায়ার, ফুলের টব, পরিত্যক্ত টায়ার, ডাবের খোসা, প্লাস্টিকের পাত্র, ভাঙ্গা বালতি, মাটির পাত্র, ফ্রিজের তলায় ইত্যাদিতে পানি জমিয়ে রাখবেন না। অব্যবহৃত পাত্র নষ্ট করে ফেলতে হবে বা উপুর করে রাখতে হবে যাতে পানি জমতে না পারে। মশারি টানিয়ে ঘুমান। বাইরে যাওয়ার সময় ফুলহাতা জামা কাপড় পড়ুন ও হাতে পায়ে রেপিলেন্ট লোশন লাগান। ঘরে মশা মারার ওষধ বা কয়েল ব্যবহার করুন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a person sleeping in a bed covered by a mosquito net. The person is lying on their back under a blanket.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/b522d6fefa397a56374416cad48809939daca8a9e9f14234803df242e04b1caf.jpg'}}]


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
