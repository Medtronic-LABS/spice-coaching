# Golden expansion prompt — diarrhea (batch 0/0)

Expected records: 24

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

DOMAIN: diarrhea
Generate exactly 24 new golden records distributed per the generation plan.

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
    "module_id": "85ae8ad2-16b9-4107-a202-4d2f0c6c3913",
    "module_title": "ডায়রিয়া: ভয়াবহতা",
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
      "8bd827ba-a0c8-4361-b4cf-5418de3991b0",
      "c63a93e5-3a60-40d4-9bbd-7b7afcf8b555",
      "02a024c8-f21a-4661-85bb-5d4fb5a93c72",
      "537ca10a-a8ab-415a-bb1f-9d8ce33900d4",
      "6efe5da6-591e-4a73-8d44-e3666e1b5cf3",
      "b9681e3d-9ec6-4656-bfa9-d56d2a4c63d9",
      "522966e7-7f56-4c18-b44b-307f8a1febf2",
      "e51cfb16-4d92-4d6e-b9d8-f25f2b0fe9f6",
      "92b24c6a-61f1-41cc-8e86-53912235b834",
      "be8c4ca1-ebe2-4647-992b-efb17f66feac"
    ]
  },
  {
    "module_id": "890105e8-3ffa-422b-8cf2-6eb0579e923f",
    "module_title": "ডায়রিয়ার লক্ষণ",
    "record_count": 12,
    "suggested_query_types": [
      "Procedural",
      "Referral Decision",
      "Factual",
      "Procedural",
      "Cross-card Synthesis",
      "Counseling",
      "Drug / Dosage",
      "Situational",
      "Factual",
      "Situational",
      "Procedural",
      "Referral Decision"
    ],
    "card_ids": [
      "de5d311c-468c-47bf-90ab-13a19fc98a23",
      "0e2a4b02-69de-4952-964f-3b292af56704",
      "85396f37-ff7b-4af0-94eb-2314fd271886",
      "303adc50-b915-49a6-af85-9b65d3337da7",
      "1e85afd9-dbe3-4b3d-819e-32351790f018",
      "86eb7454-05dc-45c4-a523-7ab56af81fc8",
      "dc54fbb1-4526-44ad-ab5c-1048e9958ee2",
      "bcd23281-ce80-49b4-9d4c-977c53eae9c1",
      "f078f79c-4985-4121-8c93-eaf75b755636",
      "badeb79e-cf94-4738-87bf-350856acbafc"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: ডায়রিয়া: ভয়াবহতা
module_id: 85ae8ad2-16b9-4107-a202-4d2f0c6c3913
cards: 10

### Card 1 (id: 8bd827ba-a0c8-4361-b4cf-5418de3991b0)
Title (bn): ডায়রিয়া: ভয়াবহতা
Body (bn): ডায়রিয়া এবং তা থেকে সৃষ্ট অপুষ্টি সারা বিশ্বে, বিশেষ করে বাংলাদেশে, শিশুর অসুস্থতা ও মৃত্যুর অন্যতম প্রধান কারণ। আমাদের ও আমাদের পার্শ্ববর্তী দেশসমূহে পাঁচ বছরের কম বয়সী শিশুরা বছরে অন্তত দুই থেকে পাঁচ বার ডায়রিয়ায় ভোগে এবং এই রোগে অন্তত বিশ থেকে ত্রিশ দিন অসুস্থ থাকে। বেশিরভাগ ডায়রিয়া কিছুদিনের মধ্যেই সেরে যায় এবং কোনো প্রকার ঔষধের দরকার হয় না। তবে, শুধু দশ শতাংশ ডায়রিয়ায় মারাত্মক পানিস্বল্পতার সৃষ্টি হয় এবং তা থেকে পাঁচ বছরের কম বয়সী বাচ্চা মারা যেতে পারে। বাংলাদেশে বছরে প্রায় এক লক্ষ দশ হাজার শিশু ডায়রিয়া থেকে মারা যায়।

### Card 2 (id: c63a93e5-3a60-40d4-9bbd-7b7afcf8b555)
Title (bn): ডায়রিয়া কি?
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'চব্বিশ ঘন্টায় তিন বারের বেশি নরম থকথকে পাতলা (মলে পানির পরিমাণ বেশি) বা পানির মতো ঘন ঘন পায়খানা হওয়াকে (তিন বারের বেশি) ডায়রিয়া বলে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'A person holds their stomach, indicating abdominal pain, with a translucent overlay of the digestive system (intestines) highlighted in white lines and a red glow in the stomach area. The background is a plain light gray.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/adbea571d18a56d36890fc4c09e349433f8daeb1b6df1f63798feb2b5a1f4103.jpg'}}]

### Card 3 (id: 02a024c8-f21a-4661-85bb-5d4fb5a93c72)
Title (bn): ডায়রিয়ার প্রধান কারণ
Body (bn): সাধারণত জীবাণুর আক্রমণে ডায়রিয়া হয়ে থাকে। যেমন ভাইরাস (রোটাভাইরাস), ব্যাকটেরিয়া (ই কোলাই, সিগেলা, ভিবরিও কলেরা), এবং প্যারাসাইট (এন্টামিবা হিস্টোলাইটিকা, জিয়ারডিয়া)।

### Card 4 (id: 537ca10a-a8ab-415a-bb1f-9d8ce33900d4)
Title (bn): ডায়রিয়া ছড়ানোর কারণ
Body (bn): ডায়রিয়া ছড়ানোর প্রধান কারণগুলো হলো: রান্না ও খাওয়ার জন্য বিশুদ্ধ পানি ব্যবহার না করা, পঁচা বা বাসি খাবার খাওয়া, খাবার ঢেকে না রাখা, মলত্যাগের পরে ও খাবার খাওয়ার আগে সাবান ও নিরাপদ পানি দিয়ে হাত না ধোয়া, স্যানিটারি ল্যাট্রিন ব্যবহার না করা, এবং মাংস, দুধ ও ডিম ভালোভাবে সিদ্ধ করে না খাওয়া।

### Card 5 (id: 6efe5da6-591e-4a73-8d44-e3666e1b5cf3)
Title (bn): ডায়রিয়া ছড়ানোর পদ্ধতি: 5F
Body (bn): ডায়রিয়া রোগ 5F এর মাধ্যমে ছড়ায়: Food (খাদ্য), Finger (হাত), Fly (মাছি), Faeces (মল), Fomite (রোগীর ব্যবহৃত বাসনপত্র বা সচরাচর ব্যবহৃত অন্যান্য জিনিসপত্র)।

### Card 6 (id: b9681e3d-9ec6-4656-bfa9-d56d2a4c63d9)
Title (bn): ডায়রিয়া হলে স্যালাইন খাওয়ানোর নিয়ম
Body (bn): বয়স ভেদে ডায়রিয়ার চিকিৎসা নিম্নরূপ: স্বাভাবিক খাবার অর্থাৎ ডায়রিয়া হওয়ার আগে রোগী যে খাবার খেত, সেই খাবার খাওয়াতে হবে এবং যেসব শিশু মায়ের দুধ খায় তাদেরকে দুধ খাওয়ানো চালিয়ে যেতে হবে।

### Card 7 (id: 522966e7-7f56-4c18-b44b-307f8a1febf2)
Title (bn): ডায়রিয়া হলে বেবী জিংক খাওয়ানোর নিয়ম
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ডায়রিয়া হলে স্যালাইনের পাশাপাশি প্রতিদিন একটি করে মোট দশটি বড়ি খাওয়াতে হবে। একটা চামচে একটু পানি নিয়ে একটা জিংক দিতে হবে। বড়ি গলে গেলে শিশুকে খাওয়াতে হবে। শিশু বমি করে দিলে ত্রিশ মিনিট অপেক্ষা করে আবার একটি বড়ি খাওয়াতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'Baby Zinc\nবেবি জিঙ্ক\nশিশুদের জন্য, সুস্বাদু ও সহজ সেব্য\n50 x 24 = 25 Sachets\nসুস্থ সবল\nও উজ্জ্বল ভবিষ্যৎ\nA product box for "Baby Zinc" with text in Bangla and English. The box features an illustration of children on a bicycle and mentions it is for children, delicious, and easy to take.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/88a4c636826aa1ab274e32d876c8eb53d5e37a9db4945d602fe5938de6d439ad.jpg'}}]

### Card 8 (id: e51cfb16-4d92-4d6e-b9d8-f25f2b0fe9f6)
Title (bn): ডায়রিয়ার রোগীকে হাসপাতালে রেফার করার মানদণ্ড
Body (bn): পাতলা পায়খানার সাথে বমি হলে, মলে রক্ত থাকলে, প্রস্রাব বন্ধ হলে, জ্বর ও খিঁচুনি হলে, তিনদিন বা বাহাত্তর ঘণ্টায় পায়খানা বন্ধ না হলে রোগীকে অবশ্যই হাসপাতালে পাঠাতে হবে।

### Card 9 (id: 92b24c6a-61f1-41cc-8e86-53912235b834)
Title (bn): ডায়রিয়া প্রতিরোধে করণীয়: নিরাপদ পানি ও খাবার
Body (bn): রান্না ও খাওয়াসহ গৃহস্থালি সকল কাজে সব সময় নিরাপদ পানি ব্যবহার করতে হবে। সব সময় টাটকা ও গরম খাবার খেতে হবে। খাবার সবসময় ঢেকে রাখতে হবে যাতে মাছি, তেলাপোকা খাবার নষ্ট করতে না পারে। কাঁচা শাকসবজি ও ফলমূল কাটা ও খাওয়ার আগে নিরাপদ পানি দিয়ে ভালোভাবে ধুয়ে নিতে হবে। মাংস, দুধ ও ডিম ভালো করে সিদ্ধ করে খেতে হবে, অর্ধসিদ্ধ খাওয়া যাবে না।

### Card 10 (id: be8c4ca1-ebe2-4647-992b-efb17f66feac)
Title (bn): ডায়রিয়া প্রতিরোধে করণীয়: ব্যক্তিগত ও পরিবেশগত স্বাস্থ্যবিধি
Body (bn): মলত্যাগের পরে ও খাবার খাওয়ার আগে সাবান ও নিরাপদ পানি দিয়ে হাত ধুয়ে নিতে হবে। সর্বদা স্যানিটারি ল্যাট্রিন ব্যবহার করতে হবে।

## Module: ডায়রিয়ার লক্ষণ
module_id: 890105e8-3ffa-422b-8cf2-6eb0579e923f
cards: 10

### Card 1 (id: de5d311c-468c-47bf-90ab-13a19fc98a23)
Title (bn): ডায়রিয়ার লক্ষণ
Body (bn): ডায়রিয়ার লক্ষণগুলো হলো বার বার পাতলা পায়খানা হওয়া, অনেক সময় পায়খানার সাথে বমি হওয়া, কখনো কখনো পেটে ব্যাথা হওয়া, খুব পানি পিপাসা হওয়া, এবং রোগী নেতিয়ে পড়া বা জ্ঞান হারানো।

### Card 2 (id: 0e2a4b02-69de-4952-964f-3b292af56704)
Title (bn): ডায়রিয়ার প্রকারভেদ: ওয়াটারী ডায়রিয়া
Body (bn): ডায়রিয়ার একটি প্রকার হলো ওয়াটারী ডায়রিয়া, যেখানে মলের থেকে পানির পরিমাণ বেশি থাকে। এটি তীব্র হতে পারে অথবা দীর্ঘমেয়াদী হতে পারে, যা চৌদ্দ দিনের বেশি স্থায়ী হয়।

### Card 3 (id: 85396f37-ff7b-4af0-94eb-2314fd271886)
Title (bn): ডায়রিয়ার প্রকারভেদ: আমাশয়
Body (bn): ডায়রিয়ার আরেকটি প্রকার হলো আমাশয়, যেখানে পাতলা মলের সাথে রক্ত থাকে। এটিও তীব্র হতে পারে অথবা দীর্ঘমেয়াদী হতে পারে।

### Card 4 (id: 303adc50-b915-49a6-af85-9b65d3337da7)
Title (bn): পানিস্বল্পতা কী?
Body (bn): সুস্থ থাকার জন্য প্রয়োজনীয় পরিমাণ পানি ও লবণজাতীয় পদার্থ শরীরে না থাকলে তাকে পানিস্বল্পতা বলে। অনেকবার পাতলা পায়খানা হলে শরীর থেকে পানি আর লবণ বের হয়ে আসে, যার ফলে পানিস্বল্পতার সৃষ্টি হয়। এই পানিস্বল্পতা রকমভেদে তিন ভাগে ভাগ করা যায়, যেমন - পানিস্বল্পতা নেই, কিছু পানিস্বল্পতা ও চরম পানিস্বল্পতা। পানিস্বল্পতা থেকে শিশুর বা রোগীর মৃত্যু হতে পারে।

### Card 5 (id: 1e85afd9-dbe3-4b3d-819e-32351790f018)
Title (bn): পানিস্বল্পতার স্তর নির্ণয়
Body (bn): পানিস্বল্পতার স্তর নির্ণয়ের জন্য একটি টেবিল ব্যবহার করা হয়। এই টেবিলটি দেখে রোগীর পানিস্বল্পতার মাত্রা বোঝা যায়।

### Card 6 (id: 86eb7454-05dc-45c4-a523-7ab56af81fc8)
Title (bn): ডায়রিয়া: ভয়াবহতা
Body (bn): ডায়রিয়া এবং তা থেকে সৃষ্ট অপুষ্টি সারা বিশ্বে, বিশেষ করে বাংলাদেশে, শিশুর অসুস্থতা ও মৃত্যুর অন্যতম প্রধান কারণ। আমাদের ও আমাদের পার্শ্ববর্তী দেশসমূহে পাঁচ বছরের কম বয়সী শিশুরা বছরে অন্তত দুই থেকে পাঁচ বার ডায়রিয়ায় ভোগে এবং এই রোগে অন্তত বিশ থেকে ত্রিশ দিন অসুস্থ থাকে। বেশিরভাগ ডায়রিয়া কিছুদিনের মধ্যেই সেরে যায় এবং কোনো প্রকার ঔষধের দরকার হয় না। তবে, শুধু দশ শতাংশ ডায়রিয়ায় মারাত্মক পানিস্বল্পতার সৃষ্টি হয় এবং তা থেকে পাঁচ বছরের কম বয়সী বাচ্চা মারা যেতে পারে। বাংলাদেশে বছরে প্রায় এক লক্ষ দশ হাজার শিশু ডায়রিয়া থেকে মারা যায়।

### Card 7 (id: dc54fbb1-4526-44ad-ab5c-1048e9958ee2)
Title (bn): ডায়রিয়া কি?
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'চব্বিশ ঘন্টায় তিন বারের বেশি নরম থকথকে পাতলা (মলে পানির পরিমাণ বেশি) বা পানির মতো ঘন ঘন পায়খানা হওয়াকে (তিন বারের বেশি) ডায়রিয়া বলে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'A person holds their stomach, indicating abdominal pain, with a translucent overlay of the digestive system (intestines) highlighted in white lines and a red glow in the stomach area. The background is a plain light gray.', 'object_name': 'ingest/figures/892d7333-915b-4a5a-bfc1-99526fbd74ab/adbea571d18a56d36890fc4c09e349433f8daeb1b6df1f63798feb2b5a1f4103.jpg'}}]

### Card 8 (id: bcd23281-ce80-49b4-9d4c-977c53eae9c1)
Title (bn): ডায়রিয়ার প্রধান কারণ
Body (bn): সাধারণত জীবাণুর আক্রমণে ডায়রিয়া হয়ে থাকে। যেমন ভাইরাস (রোটাভাইরাস), ব্যাকটেরিয়া (ই কোলাই, সিগেলা, ভিবরিও কলেরা), এবং প্যারাসাইট (এন্টামিবা হিস্টোলাইটিকা, জিয়ারডিয়া)।

### Card 9 (id: f078f79c-4985-4121-8c93-eaf75b755636)
Title (bn): ডায়রিয়া ছড়ানোর কারণ
Body (bn): ডায়রিয়া ছড়ানোর প্রধান কারণগুলো হলো: রান্না ও খাওয়ার জন্য বিশুদ্ধ পানি ব্যবহার না করা, পঁচা বা বাসি খাবার খাওয়া, খাবার ঢেকে না রাখা, মলত্যাগের পরে ও খাবার খাওয়ার আগে সাবান ও নিরাপদ পানি দিয়ে হাত না ধোয়া, স্যানিটারি ল্যাট্রিন ব্যবহার না করা, এবং মাংস, দুধ ও ডিম ভালোভাবে সিদ্ধ করে না খাওয়া।

### Card 10 (id: badeb79e-cf94-4738-87bf-350856acbafc)
Title (bn): ডায়রিয়া ছড়ানোর পদ্ধতি: 5F
Body (bn): ডায়রিয়া রোগ 5F এর মাধ্যমে ছড়ায়: Food (খাদ্য), Finger (হাত), Fly (মাছি), Faeces (মল), Fomite (রোগীর ব্যবহৃত বাসনপত্র বা সচরাচর ব্যবহৃত অন্যান্য জিনিসপত্র)।


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
