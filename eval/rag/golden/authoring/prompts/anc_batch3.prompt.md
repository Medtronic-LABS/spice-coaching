# Golden expansion prompt — anc (batch 3/3)

Expected records: 17

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

DOMAIN: anc
Generate exactly 17 new golden records distributed per the generation plan.

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
  }
]

## GENERATION PLAN
[
  {
    "module_id": "d64bc859-b83c-4ad9-b371-fd1b752cf039",
    "module_title": "বমিবমি ভাব এবং বমি",
    "record_count": 11,
    "suggested_query_types": [
      "Cross-card Synthesis",
      "Counseling",
      "Drug / Dosage",
      "Situational",
      "Factual",
      "Situational",
      "Procedural",
      "Referral Decision",
      "Factual",
      "Procedural",
      "Cross-card Synthesis"
    ],
    "card_ids": [
      "0e3627f6-116a-4d2f-b07a-1373340347c6",
      "82a406f3-44d7-4abb-8806-8c05d09eba39",
      "e0082935-b43c-4ff2-b608-10c6f3e2138c",
      "95435831-d293-4bfc-8506-086b0468527d",
      "7bc1d4f8-e718-4d92-aa71-fa2f4eb203a4",
      "8e6442e2-abf9-4ca3-b611-817538b7d339",
      "92fded14-0a02-474c-a542-f9083d7d06cd",
      "e1efae73-03a0-4e72-bd08-d31097fb9f37",
      "2406a238-d5ec-4a7e-b7dd-aa45302139b8"
    ]
  },
  {
    "module_id": "3f751ce8-c5fc-4a45-9bd2-6f7c4807e396",
    "module_title": "যোনীপথে ফোঁটা ফোঁটা রক্তক্ষরণ",
    "record_count": 6,
    "suggested_query_types": [
      "Counseling",
      "Drug / Dosage",
      "Situational",
      "Factual",
      "Situational",
      "Procedural"
    ],
    "card_ids": [
      "9ff9eff5-8fb4-48b5-8194-2f66e9ba137e",
      "d003d658-350c-4c3b-898d-01038d09e9b5",
      "2504fd7f-e3e5-42b3-924f-51c75d754231",
      "e4ac0dd2-e641-434d-a4b2-18449786df89",
      "1f5fb32d-13d7-4ebb-beb7-d60b6fbfab26",
      "1df55677-2c08-4fbd-a898-ed15ce76b18f",
      "86f1fffb-ad1c-4b04-bd92-f19f40ede2fc"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: বমিবমি ভাব এবং বমি
module_id: d64bc859-b83c-4ad9-b371-fd1b752cf039
cards: 9

### Card 1 (id: 0e3627f6-116a-4d2f-b07a-1373340347c6)
Title (bn): বমিবমি ভাব এবং বমি
Body (bn): গর্ভাবস্থায় বমিবমি ভাব এবং বমি হলে শুকনো খাবার খেতে হবে যেমন মুড়ি, বিস্কুট। বারে বারে অল্প পরিমাণ করে খেতে হবে।

### Card 2 (id: 82a406f3-44d7-4abb-8806-8c05d09eba39)
Title (bn): রক্তস্বল্পতা ও অপুষ্টি
Body (bn): রক্তস্বল্পতা ও অপুষ্টির জন্য আয়রন এবং ফলিক এসিড ট্যাবলেট দিনে দুবার একমাসের জন্য খেতে বলতে হবে। আয়রন ও ভিটামিন সি সমৃদ্ধ খাবার খেতে বলতে হবে।

### Card 3 (id: e0082935-b43c-4ff2-b608-10c6f3e2138c)
Title (bn): বুক জ্বালাপোড়া
Body (bn): বুক জ্বালাপোড়া হলে বারে বারে অল্প পরিমানে খাবার খেতে হবে। মশলা যুক্ত এবং তৈলাক্ত খাবার এড়িয়ে চলতে হবে। খাওয়ার পর পরই শোয়া থেকে বিরত থাকতে হবে।

### Card 4 (id: 95435831-d293-4bfc-8506-086b0468527d)
Title (bn): পিঠের নিম্নাংশে ব্যাথা
Body (bn): পিঠের নিম্নাংশে ব্যাথা হলে সামনে ঝুঁকে কোন কাজ করা যাবে না। ভারী জিনিস ওঠানো যাবে না। চিকিৎসকের পরামর্শ অনুযায়ী একটি করে প্যারাসিটামল ট্যাবলেট খেতে দিতে হবে। শক্ত বিছানাতে ঘুমাতে হবে।

### Card 5 (id: 7bc1d4f8-e718-4d92-aa71-fa2f4eb203a4)
Title (bn): কোষ্ঠ কাঠিন্য
Body (bn): কোষ্ঠ কাঠিন্য হলে অনেক শাক সব্জী এবং ফলমূল খেতে হবে। প্রতিদিন ইসবগুলের ভূষি দিয়ে পানি বা শরবত পান করতে হবে। বেশি করে পানি পান করতে হবে।

### Card 6 (id: 8e6442e2-abf9-4ca3-b611-817538b7d339)
Title (bn): ঘনঘন প্রসাব
Body (bn): ঘনঘন প্রসাব হলে পরিমানমতো পানি পান করতে হবে। যদি জ্বর বা শীতকম্পন হয় তাহলে চিকিৎসকের পরামর্শ নিতে হবে।

### Card 7 (id: 92fded14-0a02-474c-a542-f9083d7d06cd)
Title (bn): পায়ের স্ফীত শিরা
Body (bn): পায়ের স্ফীত শিরা হলে অনেকক্ষণ দাঁড়িয়ে থাকা এড়িয়ে চলতে হবে। বসার সময় পা উঁচু করে রাখতে হবে। নিয়মিত হালকা ব্যায়াম করতে হবে। প্রয়োজনে ক্রেপ ব্যান্ডেজ ব্যবহার করতে হবে।

### Card 8 (id: e1efae73-03a0-4e72-bd08-d31097fb9f37)
Title (bn): অর্শ্ব (পাইলস)
Body (bn): অর্শ্ব বা পাইলস হলে শাক-সবজি এবং ফলমূল খেতে হবে। প্রচুর পরিমানে পানি পান করতে হবে। কোষ্ঠকাঠিন্য এড়িয়ে চলতে হবে। গরম পানির বা ঠান্ডা পানির সেক দিতে হবে। মলদ্বারে ব্যবহারের কোন মলম ব্যবহার করতে হবে।

### Card 9 (id: 2406a238-d5ec-4a7e-b7dd-aa45302139b8)
Title (bn): পায়ে ব্যাথা বা পা কামড়ানো
Body (bn): পায়ে ব্যাথা বা পা কামড়ালে ম্যাসেজ করতে হবে। ক্যালসিয়াম বড়ি একটি করে দিনে দুবার খেতে হবে।

## Module: যোনীপথে ফোঁটা ফোঁটা রক্তক্ষরণ
module_id: 3f751ce8-c5fc-4a45-9bd2-6f7c4807e396
cards: 7

### Card 1 (id: 9ff9eff5-8fb4-48b5-8194-2f66e9ba137e)
Title (bn): যোনীপথে ফোঁটা ফোঁটা রক্তক্ষরণ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যদি গর্ভবতী মায়ের যোনীপথে ফোঁটা ফোঁটা রক্তক্ষরণ হয়, তাহলে তাকে বিছানায় শুয়ে সম্পূর্ণরূপে বিশ্রাম নিতে বলুন। তাকে ভারী কাজ করতে নিষেধ করুন। পরিষ্কার স্যানিটারী ন্যাপকিন পরে থাকতে বলুন। ঘন ঘন তরল খাবার যেমন স্যালাইন, পানি, শরবত, ইত্যাদি খেতে বলুন। যদি অল্প সময়ের মধ্যে রক্তক্ষরণ না কমে বা বেড়ে যায়, তাহলে তাকে দ্রুত হাসপাতালে রেফার করুন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'গর্ভঅবস্থায় রক্তস্রাব\nপ্রসবের সময় বা প্রসবের পর খুব বেশি রক্তস্রাব, গর্ভফুল না পড়া\nরক্তস্রাব\nগর্ভঅবস্থায়, প্রসবকালে ও প্রসবের পরে শরীরে পানি আসা, খুব বেশি মাথাব্যথা, চোখে ঝাপসা দেখা\nমাথাব্যথা ও ঝাপসা দেখা\nখিঁচুনি\nগর্ভঅবস্থায়, প্রসবের সময় বা প্রসবের পরে খিঁচুনি\nThis figure illustrates various danger signs during pregnancy and after childbirth, such as bleeding, excessive bleeding or retained placenta, swelling, severe headache, blurred vision, and convulsions. These symptoms are shown pointing towards a hospital building, indicating the need for medical attention.', 'object_name': 'ingest/figures/6df5e3b2-50df-4bcc-809a-154fed18363c/8ec0d1ec59742a14615e4cb10c240bf6ffcd2c596abdef2e56ba0fc4855ae913.jpg'}}]

### Card 2 (id: d003d658-350c-4c3b-898d-01038d09e9b5)
Title (bn): যোনীপথে বেশী রক্তক্ষরণ ও তলপেটে ব্যথা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যদি গর্ভবতী মায়ের যোনীপথে বেশী রক্তক্ষরণ হয় এবং তলপেটে ব্যথা থাকে, তাহলে তাকে দ্রুত হাসপাতালে রেফার করুন। তাকে পরিষ্কার স্যানিটারী ন্যাপকিন পরে থাকতে বলুন এবং ঘন ঘন তরল খাবার যেমন স্যালাইন, পানি, শরবত, ইত্যাদি খেতে বলুন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'গর্ভঅবস্থায় রক্তস্রাব\nপ্রসবের সময় বা প্রসবের পর খুব বেশি রক্তস্রাব, গর্ভফুল না পড়া\nরক্তস্রাব\nগর্ভঅবস্থায়, প্রসবকালে ও প্রসবের পরে শরীরে পানি আসা, খুব বেশি মাথাব্যথা, চোখে ঝাপসা দেখা\nমাথাব্যথা ও ঝাপসা দেখা\nখিঁচুনি\nগর্ভঅবস্থায়, প্রসবের সময় বা প্রসবের পরে খিঁচুনি\nThis figure illustrates various danger signs during pregnancy and after childbirth, such as bleeding, excessive bleeding or retained placenta, swelling, severe headache, blurred vision, and convulsions. These symptoms are shown pointing towards a hospital building, indicating the need for medical attention.', 'object_name': 'ingest/figures/6df5e3b2-50df-4bcc-809a-154fed18363c/8ec0d1ec59742a14615e4cb10c240bf6ffcd2c596abdef2e56ba0fc4855ae913.jpg'}}]

### Card 3 (id: 2504fd7f-e3e5-42b3-924f-51c75d754231)
Title (bn): উচ্চ রক্তচাপ ব্যবস্থাপনা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যদি গর্ভবতী মায়ের উচ্চ রক্তচাপ থাকে, তাহলে তাকে শুয়ে থাকতে বলুন। চার ঘন্টা পরে আবার রক্তচাপ মাপুন। যদি রক্তচাপ 140 over 90 মিলি মিটার মারকারীর বেশি থাকে, তাহলে তাকে সম্পূর্ণ বিশ্রামে থাকতে বলুন এবং পাতে আলগা লবন খেতে নিষেধ করুন। এই অবস্থায় তাকে দ্রুত হাসপাতালে রেফার করুন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a healthcare worker taking the blood pressure of a pregnant woman, who is seated on a stool. A man stands behind the pregnant woman, placing a hand on her shoulder.', 'object_name': 'ingest/figures/6df5e3b2-50df-4bcc-809a-154fed18363c/cf97cc61c70401131b1df3ed2fb6294827574d2fb865de533a7a8125e054f9b0.jpg'}}, {'type': 'image', 'attrs': {'alt': "An illustration depicts a pregnant woman sitting on a stool while a nurse, wearing a white uniform and cap, takes her blood pressure using a sphygmomanometer. The nurse is listening with a stethoscope and holding the pump, while the cuff is on the woman's left arm.", 'object_name': 'ingest/figures/6df5e3b2-50df-4bcc-809a-154fed18363c/bbe94caaa465fc8745da0774a99f31bf2a94c24ca6bc25972047785f23c5f4e7.jpg'}}]

### Card 4 (id: e4ac0dd2-e641-434d-a4b2-18449786df89)
Title (bn): হাতে পায়ে পানি আসা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যদি গর্ভবতী মায়ের হাতে পায়ে পানি আসে, তাহলে তাকে ঘুম বা বিশ্রামের সময় পা উঁচু করে রাখতে বলুন। রোগীকে বাম দিকে কাত হয়ে শুতে বলুন। তাকে পুষ্টিকর খাবার যেমন মাছ, মাংস, ডিম, দুধ খেতে বলুন এবং পাতে আলগা লবন খেতে নিষেধ করুন। এক সপ্তাহ পরে আবার পরীক্ষা করুন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'A.D.A.M.\nAn illustration comparing a normal human foot and ankle (left) with a swollen, edematous foot and ankle (right), showing pitting edema.', 'object_name': 'ingest/figures/6df5e3b2-50df-4bcc-809a-154fed18363c/268e872745309f7778f85c2efe631a434e0b188bb4dcb17b087eb19cf4cc2461.jpg'}}]

### Card 5 (id: 1f5fb32d-13d7-4ebb-beb7-d60b6fbfab26)
Title (bn): উচ্চ রক্তচাপ ও হাতে পায়ে পানি আসা: জরুরি রেফারেল
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যদি গর্ভবতী মায়ের উচ্চ রক্তচাপ এবং হাতে পায়ে পানি আসা উভয় লক্ষণ দেখা যায়, তাহলে তাকে দ্রুত হাসপাতালে রেফার করুন। হাসপাতালে যাওয়ার আগে রোগীকে বাম দিকে কাত হয়ে শুতে বলুন, পুষ্টিকর খাবার যেমন মাছ, মাংস, ডিম, দুধ খেতে বলুন এবং পাতে আলগা লবন খেতে নিষেধ করুন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'গর্ভঅবস্থায় রক্তস্রাব\nপ্রসবের সময় বা প্রসবের পর খুব বেশি রক্তস্রাব, গর্ভফুল না পড়া\nরক্তস্রাব\nগর্ভঅবস্থায়, প্রসবকালে ও প্রসবের পরে শরীরে পানি আসা, খুব বেশি মাথাব্যথা, চোখে ঝাপসা দেখা\nমাথাব্যথা ও ঝাপসা দেখা\nখিঁচুনি\nগর্ভঅবস্থায়, প্রসবের সময় বা প্রসবের পরে খিঁচুনি\nThis figure illustrates various danger signs during pregnancy and after childbirth, such as bleeding, excessive bleeding or retained placenta, swelling, severe headache, blurred vision, and convulsions. These symptoms are shown pointing towards a hospital building, indicating the need for medical attention.', 'object_name': 'ingest/figures/6df5e3b2-50df-4bcc-809a-154fed18363c/8ec0d1ec59742a14615e4cb10c240bf6ffcd2c596abdef2e56ba0fc4855ae913.jpg'}}]

### Card 6 (id: 1df55677-2c08-4fbd-a898-ed15ce76b18f)
Title (bn): পানি ভাঙ্গা: জরুরি অবস্থা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'যদি গর্ভবতী মায়ের ৩৭ সপ্তাহের আগে বেশী পানি ভাঙ্গে এবং পানির রং বাদামী বা সবুজ বা রক্ত মিশ্রিত হয়, তাহলে তাকে দ্রুত হাসপাতালে রেফার করুন।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'গর্ভঅবস্থায় রক্তস্রাব\nপ্রসবের সময় বা প্রসবের পর খুব বেশি রক্তস্রাব, গর্ভফুল না পড়া\nরক্তস্রাব\nগর্ভঅবস্থায়, প্রসবকালে ও প্রসবের পরে শরীরে পানি আসা, খুব বেশি মাথাব্যথা, চোখে ঝাপসা দেখা\nমাথাব্যথা ও ঝাপসা দেখা\nখিঁচুনি\nগর্ভঅবস্থায়, প্রসবের সময় বা প্রসবের পরে খিঁচুনি\nThis figure illustrates various danger signs during pregnancy and after childbirth, such as bleeding, excessive bleeding or retained placenta, swelling, severe headache, blurred vision, and convulsions. These symptoms are shown pointing towards a hospital building, indicating the need for medical attention.', 'object_name': 'ingest/figures/6df5e3b2-50df-4bcc-809a-154fed18363c/8ec0d1ec59742a14615e4cb10c240bf6ffcd2c596abdef2e56ba0fc4855ae913.jpg'}}]

### Card 7 (id: 86f1fffb-ad1c-4b04-bd92-f19f40ede2fc)
Title (bn): ৩৭ সপ্তাহের পরে অল্প অল্প পানি ভাঙ্গা
Body (bn): যদি গর্ভবতী মায়ের ৩৭ সপ্তাহের পরে অল্প অল্প পানি ভাঙ্গে এবং পানির রং স্বাভাবিক থাকে, তাহলে তাকে বিছানায় শুয়ে সম্পূর্ণরূপে বিশ্রাম নিতে বলুন। তাকে ভারী কাজ করতে নিষেধ করুন। পরিষ্কার স্যানিটারী ন্যাপকিন পরে থাকতে বলুন। ঘন ঘন তরল খাবার যেমন স্যালাইন, পানি, শরবত, ইত্যাদি খেতে বলুন। যদি পানি ভাঙ্গা না কমে বা বেড়ে যায়, তাহলে তাকে হাসপাতালে রেফার করুন।


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
