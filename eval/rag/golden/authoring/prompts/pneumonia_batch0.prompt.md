# Golden expansion prompt — pneumonia (batch 0/0)

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

DOMAIN: pneumonia
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
    "module_id": "944d2b28-d0df-4f69-8ec9-ea4354c50fd5",
    "module_title": "শ্বাসতন্ত্র কী?",
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
      "9ef4e6c3-ae2a-4c4f-a0c9-9060621242d1",
      "9636d88f-1b81-4da3-9e27-858c6417cd22",
      "610320ac-c1d7-43a3-a084-bbe76637ca52",
      "606ee3d0-17da-41f3-8c41-275e60350154",
      "0baa3edc-fcc5-4d39-a3c0-65c2c9a74db8",
      "d90a791b-9192-4afa-ab4c-382a4e252035",
      "0df837e5-15c8-459d-866d-abe6c9bf7e5b"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: শ্বাসতন্ত্র কী?
module_id: 944d2b28-d0df-4f69-8ec9-ea4354c50fd5
cards: 7

### Card 1 (id: 9ef4e6c3-ae2a-4c4f-a0c9-9060621242d1)
Title (bn): শ্বাসতন্ত্র কী?
Body (bn): যে সকল অঙ্গ দিয়ে শ্বাস নেয়া হয় যেমন- নাক, মুখ, গলা, ফুসফুস এগুলোকে একসাথে শ্বাসতন্ত্র বলে।

### Card 2 (id: 9636d88f-1b81-4da3-9e27-858c6417cd22)
Title (bn): শ্বাসতন্ত্রের সংক্রমণ কী?
Body (bn): শ্বাসতন্ত্রের যে কোন অংশের হঠাৎ সংক্রমণ কে শ্বাসতন্ত্রে সংক্রমণ বলে। শ্বাসতন্ত্রের যে কোন অংশের হঠাৎ সংক্রমণ হলে তাকে এআরআই (Acute Respiratory tract Infection) বা শ্বাসতন্ত্রের তীব্র সংক্রমণ বলে।

### Card 3 (id: 610320ac-c1d7-43a3-a084-bbe76637ca52)
Title (bn): শ্বাসতন্ত্রের সংক্রমণের লক্ষণ
Body (bn): শ্বাসতন্ত্রের সংক্রমণের লক্ষণগুলো হলো নাক দিয়ে পানি পড়া, কাশি, গলা ব্যাথা, বাধাগ্রস্থ শ্বাসপ্রশ্বাস, কানের সমস্যা এবং জ্বর।

### Card 4 (id: 606ee3d0-17da-41f3-8c41-275e60350154)
Title (bn): নিউমোনিয়া কী এবং এর লক্ষণ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শুধুমাত্র ফুসফুসের সংক্রমণ কে নিউমোনিয়া বলা হয়। নিউমোনিয়ার লক্ষণগুলো হলো দ্রুত শ্বাস, বুকের খাঁচা ডেবে যাওয়া, জ্বর, কাশি এবং শ্বাসকষ্ট।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a woman holding a distressed infant, with three circular insets highlighting symptoms: rapid breathing, lung issues (possibly pneumonia), and chest indrawing.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/e22744cbee3bf6ba008664e85a93abbf82564e846a739c1d083b06c1cf8ec0f8.jpg'}}]

### Card 5 (id: 0baa3edc-fcc5-4d39-a3c0-65c2c9a74db8)
Title (bn): শ্বাসতন্ত্রের সংক্রমণের কারণ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শ্বাসতন্ত্রের সংক্রমণের প্রত্যক্ষ কারণ হলো ব্যাকটেরিয়া এবং ভাইরাস উভয়ই, যার মধ্যে অধিকাংশ ক্ষেত্রে ব্যাকটেরিয়ার কারণে নিউমোনিয়া হয়ে থাকে। পরোক্ষ কারণগুলোর মধ্যে রয়েছে শিশুর জন্মকালীন ওজন যদি দুই দশমিক পাঁচ কেজির কম হয়, শিশুকে যদি জন্মের পর পর গোসল দেয়া হয়, শিশু যদি পুষ্টিহীনতায় ভোগে, শিশুকে যদি জন্মের পর শাল দুধ খাওয়ানো না হয়, শিশুকে যদি ছয় মাস পর্যন্ত শুধুমাত্র বুকের দুধ খাওয়ানো না হয়, শিশুকে যদি রোগ প্রতিষেধক টীকা না দেয়া হয়, শিশুর যদি ভিটামিন এ এর অভাব থাকে, বাড়ির ভেতরের আবহাওয়া যদি বদ্ধ, ঠান্ডা, ভেজা বা স্যাঁতস্যাঁতে হয়, এবং যদি এক ঘরের মধ্যে অনেক লোক একসাথে বসবাস করে (ঘন বসতি)।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'dreamstime.com\nA stylized illustration depicts a fetus or newborn baby lying on a weighing scale. The baby is light orange, and the scale is grey with a dial and needle.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/01bb0b0dd884677bdf162f4b19b0913098b4bdb8aff7396f29d729d71eeb9468.jpg'}}, {'type': 'image', 'attrs': {'alt': 'নবজাতকের অত্যাবশ্যকীয় পরিচর্যা\nমোছানো\nজন্মের সাথে সাথে পরিষ্কার ও শুকনো\nনরম সুতি কাপড় দিয়ে মোছানো\nনাড়ীর যত্ন\nএকবার ক্লোরহেক্সিডিন লাগানোর পর\nনাড়ীতে অন্য কোন কিছুই না লাগানো\nও শুষ্ক রাখা\nউষ্ণতা বজায় রাখা\nমোছানোর সাথে সাথে মায়ের ত্বকে\nত্বক স্পর্শে রাখা এবং পরবর্তীতে মাথা\nও শরীর কাপড়ে জড়িয়ে উষ্ণ রাখা\nবুকের দুধ খাওয়ানো\nজন্মের সাথে সাথে, অবশ্যই ১ ঘণ্টার\nমধ্যেই বুকের দুধ খাওয়ানো\nনা\nগোসল না করানো\nজন্মের তিন দিনের মধ্যে কোনভাবেই\nশিশুকে গোসল না করানো\nমা ও নবজাতক বাঁচানোর সাফ কথা:\nThis is a public health poster in Bengali titled "Essential Care for Newborns". It illustrates five key practices for newborn care: wiping, umbilical cord care, maintaining warmth, breastfeeding, and not bathing the baby immediately after birth. Each practice is accompanied by an illustration and a short descriptive text.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/157e79f5b7dd179dda8e277f02617c5b94429947704cf0a043df65f175be89cd.png'}}, {'type': 'image', 'attrs': {'alt': 'An illustration depicting a mother breastfeeding her baby, supported by a man (likely the father) and a healthcare worker in a white coat. The Save the Children logo is in the top right corner.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/0a630586278c2df62ada04857531407601fea69ca4ac9f0b5e5f7b66eab57121.jpg'}}, {'type': 'image', 'attrs': {'alt': 'An illustration of a baby lying down, receiving an injection in the upper arm from a hand holding a syringe.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/5183cfe600608a553dcf2d329bf7a0b4de6f89391b966820616a1cb930870e96.jpg'}}]

### Card 6 (id: d90a791b-9192-4afa-ab4c-382a4e252035)
Title (bn): দ্রুত শ্বাস ও শ্বাস-প্রশ্বাসের হার গণনা
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শ্বাসের গতি স্বাভাবিকের চেয়ে বেড়ে গেলে তাকে দ্রুত শ্বাস বলে। একবার শ্বাস নেয়া ও ছাড়াকে শ্বাস-প্রশ্বাস বলা হয়, এভাবে এক মিনিটে যতবার শ্বাস নেয়া ও ছাড়া হয় সেই সংখ্যাকে শ্বাস-প্রশ্বাসের হার বলা হয়। শ্বাস গণনার সময় শিশুকে শান্ত অবস্থায় রাখতে হবে, ঘরে যথেষ্ট আলোর ব্যবস্থা থাকতে হবে। সেকেন্ডের কাঁটাযুক্ত ঘড়ি বা টাইমার শিশুর বুকের উপর রাখতে হবে। আগে ঘড়ি দেখতে হবে পরে শ্বাস গণনা করতে হবে। বুক বা পেটের যে কোন অংশের উঠানামা লক্ষ্য করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'দ্রুত শ্বাস নেওয়া অথবা\nThe image shows two illustrations within a circular segmented diagram. The left segment depicts a baby lying down, and the right segment shows a baby being breastfed by an adult.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/fc81f69a2f0e544a8cda6f7431661361944eef44bbd39008a0371382c8d2163a.jpg'}}]

### Card 7 (id: 0df837e5-15c8-459d-866d-abe6c9bf7e5b)
Title (bn): শিশুকে কখন হাসপাতালে রেফার করতে হবে?
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'শিশুকে হাসপাতালে রেফার করতে হবে যদি দ্রুত শ্বাসের সাথে বুকের পাঁজর ডেবে যায়, শিশুকে খাওয়ানো না যায়, অস্বাভাবিক ঘুম ঘুম ভাব থাকে, শ্বাস-প্রশ্বাসের সময় সাঁই সাঁই বা গড় গড় শব্দ হয়, খিঁচুনি হয়, অতিরিক্ত জ্বর বা স্বাভাবিকের চেয়ে তাপমাত্রা কমে যায়, অথবা অতিরিক্ত বমি হয়।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': "নাভি পাকা\nবুকের খাঁচা দেবে যাওয়া\nবুকের দুধ ঢানতে\nনা পারা বা না চোষা\nজ্বর বা শরীর ঠান্ডা হওয়া\nA circular diagram with a baby's face in the center, surrounded by four quadrants depicting different infant health problems: umbilical infection, chest indrawing, inability to suckle breast milk, and fever or cold body.", 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/9168e38a21c09e3a12426138100f8f4eb04b81eedf89f52334f7300707d14a1d.jpg'}}, {'type': 'image', 'attrs': {'alt': 'খিঁচুনি\nনেতিয়ে পড়া\nThe image shows two illustrations of infants, each with a Bengali label. The left illustration shows an infant convulsing, labeled "খিঁচুনি" (convulsion). The right illustration shows an infant being held, appearing limp, labeled "নেতিয়ে পড়া" (limp/flaccid).', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/78860d88b909fc6612353522e28b4e2934a06a9550d3ade6b1b428d8990bd654.jpg'}}]


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
