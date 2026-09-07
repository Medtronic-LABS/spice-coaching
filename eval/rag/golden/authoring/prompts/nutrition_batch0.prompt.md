# Golden expansion prompt — nutrition (batch 0/2)

Expected records: 8

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
Generate exactly 8 new golden records distributed per the generation plan.

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
    "module_id": "41c7bb53-12bc-4385-a1ce-8a79a8e208f9",
    "module_title": "পারিবারিক খাবার কি?",
    "record_count": 8,
    "suggested_query_types": [
      "Factual",
      "Situational",
      "Procedural",
      "Referral Decision",
      "Factual",
      "Procedural",
      "Cross-card Synthesis",
      "Counseling"
    ],
    "card_ids": [
      "27c7b1ff-97c1-4d3f-a838-8b13d29d5b9f",
      "db6caa6f-a3f1-42db-9843-21c49d1bdf87",
      "b5354c00-0ec6-4f08-8556-0f0872f995a1",
      "a7653ae6-2560-4321-8772-415f3aa6b719",
      "0804277e-0dc3-49d2-81fa-937bdfde47f5",
      "bc2aa259-7525-48d1-8636-fb6a79d66812",
      "d7899089-e934-4130-80a0-641a101fd32e",
      "7231df47-09b2-450b-8301-0a4c08cfa19d"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: পারিবারিক খাবার কি?
module_id: 41c7bb53-12bc-4385-a1ce-8a79a8e208f9
cards: 8

### Card 1 (id: 27c7b1ff-97c1-4d3f-a838-8b13d29d5b9f)
Title (bn): পারিবারিক খাবার কি?
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শিশুর ছয় মাস পূর্ণ হবার পর মায়ের দুধের পাশাপাশি পরিবারের সবার জন্য রান্না করা খাবার থেকে যে খাবার নিয়ে শিশুকে খাওয়ানো হয় তাকে পারিবারিক খাবার বলে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a woman in a purple sari feeding a baby from a bowl. The woman is holding the baby on her lap and appears to be offering food with a spoon.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/2bb7aed0520f8c3c024fdd606d72d3c3f5f54981b40efb2726619953f2da0466.jpg'}}]

### Card 2 (id: db6caa6f-a3f1-42db-9843-21c49d1bdf87)
Title (bn): ৬ মাসের পর কেন পারিবারিক খাবার প্রয়োজন?
Body (bn): ছয় মাসের পর শুধু মায়ের দুধ শিশুর জন্য যথেষ্ট নয়। প্রয়োজনীয় পুষ্টির জন্য শিশুকে অন্যান্য খাবার দিতে হবে। ছয় মাস বয়স থেকে অন্যান্য খাবার না দিলে শিশুর স্বাভাবিক বৃদ্ধি ঘটবে না এবং শিশু অপুষ্টিতে ভুগবে।

### Card 3 (id: b5354c00-0ec6-4f08-8556-0f0872f995a1)
Title (bn): পারিবারিক খাবার খাওয়ানোর প্রয়োজনীয়তা ও উপকারিতা
Body (bn): বাড়তি খাবার কেনার প্রয়োজন হয় না এবং খরচ কম হয়। শারীরিক বৃদ্ধি ও মানসিক বিকাশ ভালোভাবে হয়, ফলে শিশু সুস্থ ও হাসিখুশি থাকে। রোগ প্রতিরোধ ক্ষমতা বাড়ে ফলে রোগ-ব্যাধি কম হয়, শিশু অসুস্থ হলে তাড়াতাড়ি সুস্থ হয়ে উঠে। ঝামেলা কম ও সময় কম লাগে।

### Card 4 (id: a7653ae6-2560-4321-8772-415f3aa6b719)
Title (bn): ৬ মাস পূর্ণ বয়সের পর বাড়তি খাবার শুরু করার কারণ
Body (bn): ছয় মাস বয়স পূর্ণ হলে শিশু বাড়তি খাবার সহজে খেতে ও গিলতে শিখে, পাশাপাশি হজমও করতে পারে। ছয় মাস পূর্ণ হওয়ার আগে শিশুকে বাড়তি খাবার দিলে মায়ের দুধ খাওয়া কমিয়ে দিবে ফলে, শিশুর শারীরিক চাহিদা অনুযায়ী সঠিক পরিমাণে পুষ্টি পাবে না। ছয় মাস পূর্ণ হওয়ার পর পরই বাড়তি খাবার অভ্যাস না করালে পরে সে ঘন, শক্ত খাবার খেতে শিখবে না। অর্থাৎ এইটাই শিশুর বাড়তি খাবার খাওয়ার উপযুক্ত বয়স।

### Card 5 (id: 0804277e-0dc3-49d2-81fa-937bdfde47f5)
Title (bn): বয়স অনুযায়ী শিশুর খাবারের ঘনত্ব
Body (bn): ছয় মাস থেকে আট মাস বয়সী শিশুদের চটকানো খাবার দিতে হবে। নয় মাস থেকে এগারো মাস বয়সী শিশুদের খাবার ছোট ছোট টুকরা করে দিতে হবে। বারো মাস থেকে চব্বিশ মাস বয়সী উপরের শিশুদের বড়দের মতো খাবার দিতে হবে।

### Card 6 (id: bc2aa259-7525-48d1-8636-fb6a79d66812)
Title (bn): বয়স অনুযায়ী শিশুর খাবারের পরিমাণ ও বার
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'ছয় মাস থেকে আট মাস পূর্ণ শিশুর খাবার ২৫০ মিলি লিটার বাটির অর্ধেক বাটি দিনে দুই বার সাথে পুষ্টিকর নাশতা এক থেকে দুই বার। নয় মাস থেকে এগারো মাস পূর্ণ শিশুর খাবার ২৫০ মিলি লিটার বাটির অর্ধেক বাটি দিনে তিন বার সাথে পুষ্টিকর নাশতা এক থেকে দুই বার। বারো মাস থেকে তেইশ মাস পূর্ণ শিশুর খাবার ২৫০ মিলি লিটার বাটির এক বাটি দিনে তিন বার সাথে পুষ্টিকর নাশতা এক থেকে দুই বার। বাড়তি খাবারের সঙ্গে কমপক্ষে দুই বছর বয়স পর্যন্ত মায়ের দুধ খাওয়াতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'বাড়তি খাবারের সঙ্গে কমপক্ষে দুই বছর বয়স পর্যন্ত মায়ের দুধ খাওয়াতে হবে\n৬-৮ মাস পূর্ণ শিশুর খাবার ২৫০ মি.লি.\nবাটির ১/২ বাটি দিনে ২ বার + সঙ্গে\nপুষ্টিকর নাশতা ১-২ বার\n৯-১১ মাস পূর্ণ শিশুর খাবার\n২৫০ মি.লি. বাটির ১/২ বাটি\nদিনে ৩ বার + সঙ্গে\nপুষ্টিকর নাশতা\n১-২ বার\n১২-২৩ মাস পূর্ণ\nশিশুর খাবার\n২৫০ মি.লি. বাটির ১ বাটি\nদিনে ৩ বার + সঙ্গে\nপুষ্টিকর নাশতা ১-২ বার\nThe figure illustrates feeding guidelines for children from 6 months to 23 months, emphasizing continued breastfeeding up to two years alongside complementary foods. It shows three stages of child development (6-8 months, 9-11 months, 12-23 months) with corresponding food quantities, meal frequencies, and snack recommendations.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/e3c89f042c5f96d01d337d15a32c7a0ea2a30186d7e303c4f1c69dbc756b5895.jpg'}}]

### Card 7 (id: d7899089-e934-4130-80a0-641a101fd32e)
Title (bn): শিশুর জন্য পুষ্টিকর পারিবারিক খাবার তৈরির নিয়ম
Body (bn): প্রথমে সাবান ও নিরাপদ পানি দিয়ে ভালোভাবে হাত ধুয়ে নিন এবং ২৫০ মিলি লিটার মাপের বাটি ধুয়ে নিন। বাটিতে একটুকরা মাছ, মাংস, ডিম, কলিজা যে কোন একটি নিয়ে চটকে নিন। এরপর বাটিতে ঘন ডাল, সবজি এবং বাকি টুকু ভাত দিয়ে পূরণ করুন। সবকিছু নেওয়ার পর একসঙ্গে মাখান। খেয়াল রাখতে হবে মোট তৈরি করা খাবারের পরিমাণ যাতে বয়স অনুযায়ী ঠিক থাকে। প্রতিদিন একবেলার খাবারের সঙ্গে পুষ্টিকণা মেশাতে হবে।

### Card 8 (id: 7231df47-09b2-450b-8301-0a4c08cfa19d)
Title (bn): শিশুর জন্য বিভিন্ন ধরনের খাদ্য নির্বাচন
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শিশুর খাবার তৈরি করার সময় পরিবারের জন্য রান্না করা খাবার থেকে শিশুর জন্য পুষ্টিকর খাবার নির্বাচন করা খুবই গুরুত্বপূর্ণ। এতে করে শিশু সব ধরনের পুষ্টি পাবে যা শিশুর ব্রেনের বৃদ্ধি ও শারীরিক গঠনের জন্য প্রয়োজন। শিশুর খাবার নির্বাচনের সময় লক্ষ্য রাখতে হবে কমপক্ষে দিনে একবার হলেও যেন প্রাণিজ খাবার যেমন - মাছ, মাংস, মুরগির কলিজা, ডিম ইত্যাদি থাকে। ছোট মাছ বা মাংস হলে পাটায় পিশে নিয়ে ভাতের সাথে মাখানো যায়। পনির বা দই নাস্তা হিসাবে দেওয়া যায়। এছাড়া মিষ্টি কুমড়া, পাকা আম, পাকা পেঁপে, কাঁঠাল ইত্যাদি খাবারও শিশুকে দিতে হবে। শিশুর খাবারে এক চা চামচ তেল দিয়ে মাখালে খাবার আরও পুষ্টিকর হবে। তবে শিশু যদি তেলে ভাজা খাবার খায় তবে তার খাবারে আলাদা ভাবে তেল না দিলেও হবে। শিশুকে খাবার খাওয়ানোর সময় আলাদা ভাবে পানি খাওয়ানোর দরকার নেই এতে তার ছোট পেট ভরে যাবে এবং তার জন্য তৈরি করা পুষ্টিকর খাবারটি খেতে পারবে না। শিশুকে পানির পরিবর্তে বুকের দুধ খাওয়াবেন। এতে শিশু পুষ্টি পাবে। মনে রাখতে হবে শিশুরা বিভিন্ন ধরনের খাবার খেতে ভালোবাসে, তাই তার খাবারে নতুন খাবার যোগ করা যায় বা তৈরি করা যায়।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': '(illegible text along the left rim of the plate)\nA watercolor illustration depicts a traditional meal served on a round wooden plate lined with a banana leaf. The meal includes a mound of white rice, various small bowls of curries or side dishes, a fried fish, a piece of flatbread, and lime wedges.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/9e246a809acf570102cbc967b3ede66e6ead7356535992da887eeb42b69873ab.jpg'}}]


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
