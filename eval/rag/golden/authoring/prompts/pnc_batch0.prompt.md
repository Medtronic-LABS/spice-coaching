# Golden expansion prompt — pnc (batch 0/2)

Expected records: 25

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

DOMAIN: pnc
Generate exactly 25 new golden records distributed per the generation plan.

## FEW-SHOT EXAMPLES
[
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
    "question_en": "What are the danger signs for the mother and when should they be referred?",
    "expected_answer_en": "Severe fever, foul-smelling vaginal discharge, severe abdominal pain, excessive bleeding, shortness of breath, palpitations, breast pain or redness, fainting or seizures, incontinence of urine or stool, etc.—refer immediately if any of these occur.",
    "question_bn": "প্রসূতির বিপদজনক লক্ষণ কি কি এবং কখন রেফার করতে হবে?",
    "expected_answer_bn": "তীব্র জ্বর, দুর্গন্ধযুক্ত যোনি স্রাব, প্রচণ্ড পেটে ব্যথা, অতিরিক্ত রক্তক্ষরণ, শ্বাসকষ্ট, বুক ধড়ফড় করা, স্তন ব্যথা বা লাল হওয়া, অজ্ঞান হওয়া বা খিঁচুনি, প্রস্রাব-পায়খানা বের হওয়া ইত্যাদি দেখা দিলে দ্রুত রেফার করতে হবে।",
    "source_card_id": [
      "19f02ebc-872f-49e8-8f47-f53ec29e2a03",
      "13c7f1e4-e3a8-4fec-94d6-7a87b42aaa75",
      "a030c69d-1621-4ae3-abe6-e9b63e99798c",
      "d3e6a17d-109f-4501-ab76-2387763363dc",
      "fe9b6e01-0413-42f1-908c-d2a3352bbbf9",
      "beb97eea-32a1-4ded-abe9-0a5804028904",
      "68cc6c0f-5126-416b-95d1-53458109dee4",
      "7a50059a-985c-45fc-a2ff-30c2781c8919",
      "1c1a7dfa-542c-44e4-af87-9baa63a335f2"
    ],
    "query_type": "Factual",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Maternal Danger Signs & Referral",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "19ebc229-ee76-4706-962d-8f5a6392b838",
      "6fa7a48b-fce5-48f6-8eaa-afbb56438bf6"
    ]
  },
  {
    "question_en": "How should the nursing mother take care of her breasts?",
    "expected_answer_en": "Clean breasts with a clean cotton cloth before and after feeding daily. Massage with oil if nipples are inverted. Consult a doctor if nipples are cracked, and express milk if there is pain due to excessive milk production.",
    "question_bn": "প্রসূতি মা তার স্তনের যত্ন কিভাবে করবেন?",
    "expected_answer_bn": "প্রতিদিন দুধ খাওয়ানোর আগে ও পরে স্তন পরিষ্কার সুতি কাপড় দিয়ে পরিষ্কার করুন। নিপল ভিতরের দিকে হলে তেল দিয়ে মালিশ করুন। নিপল ফেটে গেলে ডাক্তারের পরামর্শ নিন এবং অতিরিক্ত দুধের জন্য ব্যথা হলে দুধ বের করে ফেলুন।",
    "source_card_id": [
      "a02d552c-5628-45b9-8474-46ca14c6dce1",
      "3938ebeb-3516-4c7c-b4e9-8501e8e36b42",
      "8b57b4e9-118b-4463-8a6f-91106388c519",
      "18c3171f-d17c-496d-b0fb-a2f4e4402517"
    ],
    "query_type": "Procedural",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Self-care & Breast Care",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "102da01a-b99c-44c1-8469-5f09d87639be",
      "3a6dc0b6-21c7-4570-ad70-c71166b6b634",
      "f2e10590-9fa6-420c-a131-5f0f070df449"
    ]
  },
  {
    "question_en": "How can you tell if the postpartum mother's uterus is shrinking normally back to its previous state?",
    "expected_answer_en": "After delivery, the uterine height is at the umbilicus, decreases by 1 finger daily, reaches the pubic bone by the 10th day, and returns to the pre-pregnancy state by 42 days.",
    "question_bn": "প্রসবের পর প্রসূতি মায়ের জরায়ু স্বাভাবিকভাবে সংকুচিত হয়ে আগের অবস্থায় ফিরে আসছে কি না কীভাবে বুঝবেন?",
    "expected_answer_bn": "প্রসবের পর জরায়ুর উচ্চতা নাভি বরাবর থাকে, প্রতিদিন ১ আঙ্গুল করে কমে ১০ দিনের মাথায় তলপেটের হাড় বরাবর চলে আসে এবং ৪২ দিনের মাথায় পূর্বের অবস্থায় ফিরে যায়।",
    "source_card_id": [
      "9c727744-b4c5-4abb-a7ee-7ed1903941a0",
      "e7a28a00-6503-4edc-a34c-1476a9379837"
    ],
    "query_type": "Factual",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Physiological Assessment",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "d476db69-92ee-4973-b2c5-068a23a01bff",
      "e7b05394-a774-4ae1-a5c4-955a9483a131"
    ]
  },
  {
    "question_en": "Vaginal discharge is continuing 2 weeks after delivery. How to determine if it is normal postnatal discharge or a complication?",
    "expected_answer_en": "Normal discharge (lochia) changes color over time (red to white). However, if there is excessive bleeding, foul-smelling discharge, fever, or lower abdominal pain, it may be a sign of infection. Refer immediately in such cases.",
    "question_bn": "প্রসবের ২ সপ্তাহ পরও মায়ের যোনিপথ দিয়ে স্রাব যাচ্ছে। কীভাবে বুঝবেন এটি প্রসব-পরবর্তী স্বাভাবিক স্রাব, নাকি কোনো জটিলতার লক্ষণ?",
    "expected_answer_bn": "স্বাভাবিক স্রাব (লোকিয়া) সময়ের সাথে রঙ পরিবর্তন করে (লাল থেকে সাদা)। কিন্তু যদি প্রচুর রক্তক্ষরণ হয়, দুর্গন্ধযুক্ত স্রাব থাকে, জ্বর বা তলপেটে ব্যথা থাকে, তবে এটি সংক্রমণের লক্ষণ হতে পারে। এমন অবস্থায় দ্রুত রেফার করুন।",
    "source_card_id": [
      "216731e1-4c7c-49fa-a220-c94483d0b742",
      "c811296b-41ad-4a36-a650-d6b8c0502b77",
      "501bebad-6197-4c9d-9b58-aa62737f220e",
      "a030c69d-1621-4ae3-abe6-e9b63e99798c"
    ],
    "query_type": "Scenario-based",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Differential Diagnosis & Complication Recognition",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "19ebc229-ee76-4706-962d-8f5a6392b838",
      "d476db69-92ee-4973-b2c5-068a23a01bff",
      "e7b05394-a774-4ae1-a5c4-955a9483a131"
    ]
  }
]

## GENERATION PLAN
[
  {
    "module_id": "3a6dc0b6-21c7-4570-ad70-c71166b6b634",
    "module_title": "প্রসব পরবর্তী সাধারণ সমস্যা: স্তনের বোঁটা ফেটে যাওয়া বা ঘা হওয়া",
    "record_count": 3,
    "suggested_query_types": [
      "Factual",
      "Situational",
      "Procedural"
    ],
    "card_ids": [
      "3938ebeb-3516-4c7c-b4e9-8501e8e36b42",
      "8b57b4e9-118b-4463-8a6f-91106388c519"
    ]
  },
  {
    "module_id": "8441d848-a42f-4848-a557-85037831a8f6",
    "module_title": "প্রসব পরবর্তী রক্তস্বল্পতা বা সাধারণ দুর্বলতা",
    "record_count": 4,
    "suggested_query_types": [
      "Referral Decision",
      "Factual",
      "Procedural",
      "Cross-card Synthesis"
    ],
    "card_ids": [
      "a11fc9cd-5f88-4663-88bc-104ba459f09d",
      "303ea72c-6f0c-4fc9-b1fd-be6e036308f1",
      "56f19ae0-5cdd-48dd-94fe-22f7e28354cc"
    ]
  },
  {
    "module_id": "e7b05394-a774-4ae1-a5c4-955a9483a131",
    "module_title": "প্রসব পরবর্তী সেবা কী?",
    "record_count": 8,
    "suggested_query_types": [
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
      "8573f5d0-f5e1-4dad-982e-29498d360893",
      "e31e406d-91fe-47b2-b9da-07e727406d65",
      "91c9f66a-1ce4-466f-b8e7-7e25d8a3b642",
      "d2f017e6-fbb2-491e-80ed-9801dfdf7109",
      "b2cb2b3c-a7d0-4e71-9d34-8a32551275a7",
      "e7a28a00-6503-4edc-a34c-1476a9379837",
      "501bebad-6197-4c9d-9b58-aa62737f220e",
      "b5e0a4ce-c38d-437e-a59d-a53df4040387",
      "34b6d1de-544c-4f13-8305-d893088b1aef"
    ]
  },
  {
    "module_id": "d476db69-92ee-4973-b2c5-068a23a01bff",
    "module_title": "প্রসব পরবর্তী সেবা (Puerperium) কী?",
    "record_count": 10,
    "suggested_query_types": [
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
      "297a3b21-d417-4597-b036-5be754e99fd5",
      "ea25a5f5-a51c-4670-b49f-3a46639ba193",
      "17686bf8-b77f-4317-a234-351e1c195b9d",
      "e0300ed9-d9b7-411f-93e0-99f53864c4a7",
      "b69f15d5-6645-4d8a-b6e7-0f8a8bffc2bb",
      "ccdc0470-e178-410e-ad12-51c357f4e407",
      "9c727744-b4c5-4abb-a7ee-7ed1903941a0",
      "216731e1-4c7c-49fa-a220-c94483d0b742",
      "c811296b-41ad-4a36-a650-d6b8c0502b77",
      "12450c9c-6380-4680-b543-ff7e27391ded"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: প্রসব পরবর্তী সাধারণ সমস্যা: স্তনের বোঁটা ফেটে যাওয়া বা ঘা হওয়া
module_id: 3a6dc0b6-21c7-4570-ad70-c71166b6b634
cards: 2

### Card 1 (id: 3938ebeb-3516-4c7c-b4e9-8501e8e36b42)
Title (bn): প্রসব পরবর্তী সাধারণ সমস্যা: স্তনের বোঁটা ফেটে যাওয়া বা ঘা হওয়া
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'প্রসব পরবর্তী সময়ে মায়েদের স্তনের বোঁটা ফেটে যাওয়া বা ঘা হওয়া একটি সাধারণ সমস্যা। এর কারণ হলো শিশুকে সঠিক পদ্ধতিতে স্তন পান না করানো। এর ফলে স্তনের বোঁটা ফেটে যায় বা ঘা হয় এবং মা ব্যথা অনুভব করেন। এই সমস্যা সমাধানের জন্য মাকে সঠিক পদ্ধতিতে স্তন পান করানোর বিষয়ে পরামর্শ দিতে হবে। শিশুকে স্তন পান করানোর সময় মায়ের স্তন এবং শিশুর মুখ সঠিক অবস্থানে আছে কিনা তা নিশ্চিত করতে হবে। শিশুকে স্তন পান করানোর পর স্তনের বোঁটায় মায়ের দুধ লাগিয়ে শুকিয়ে নিতে হবে। এতে স্তনের বোঁটা নরম থাকবে এবং ঘা শুকিয়ে যাবে। যদি স্তনের বোঁটা ফেটে যায় বা ঘা হয় এবং মা ব্যথা অনুভব করেন, তবে তাকে নিকটস্থ স্বাস্থ্যকেন্দ্রে রেফার করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'width': 423, 'height': 321, 'object_name': 'ingest/figures/1c587fda-9beb-4024-acbb-b90450c0521c/a876893ebe84f9f6cdc5073f564adc94bc9ecaf915f9ac26a0223f338eaa4905.jpg'}}, {'type': 'image', 'attrs': {'width': 407, 'height': 155, 'object_name': 'ingest/figures/1c587fda-9beb-4024-acbb-b90450c0521c/317cd2f3383d5ca0a8a43f18a69212ed4f7676aa4ccc76aaf09540cc0a3f5507.jpg'}}, {'type': 'image', 'attrs': {'width': 480, 'height': 355, 'object_name': 'ingest/figures/1c587fda-9beb-4024-acbb-b90450c0521c/bd0f447b3bbb0965814bd54eecb1c4b1cca4950ab430490bb5e1ba1988edd545.jpg'}}, {'type': 'paragraph', 'content': [{'text': '', 'type': 'text'}]}]

### Card 2 (id: 8b57b4e9-118b-4463-8a6f-91106388c519)
Title (bn): প্রসব পরবর্তী সাধারণ সমস্যা: স্তন ফুলে যাওয়া ও ব্যথা হওয়া
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'প্রসব পরবর্তী সময়ে মায়েদের স্তন ফুলে যাওয়া ও ব্যথা হওয়া আরেকটি সাধারণ সমস্যা। এর কারণ হলো শিশুকে সঠিক পদ্ধতিতে স্তন পান না করানো অথবা শিশুকে পর্যাপ্ত পরিমাণে স্তন পান না করানো। এর ফলে স্তনে দুধ জমে যায় এবং স্তন ফুলে যায় ও ব্যথা হয়। এই সমস্যা সমাধানের জন্য মাকে সঠিক পদ্ধতিতে স্তন পান করানোর বিষয়ে পরামর্শ দিতে হবে এবং শিশুকে ঘন ঘন স্তন পান করাতে উৎসাহিত করতে হবে। শিশুকে স্তন পান করানোর আগে স্তনে গরম সেঁক দিতে হবে এবং স্তন পান করানোর পর ঠান্ডা সেঁক দিতে হবে। যদি স্তন ফুলে যায় ও ব্যথা হয় এবং মা জ্বর অনুভব করেন, তবে তাকে নিকটস্থ স্বাস্থ্যকেন্দ্রে রেফার করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'object_name': 'ingest/figures/1c587fda-9beb-4024-acbb-b90450c0521c/a876893ebe84f9f6cdc5073f564adc94bc9ecaf915f9ac26a0223f338eaa4905.jpg'}}, {'type': 'image', 'attrs': {'object_name': 'ingest/figures/1c587fda-9beb-4024-acbb-b90450c0521c/317cd2f3383d5ca0a8a43f18a69212ed4f7676aa4ccc76aaf09540cc0a3f5507.jpg'}}, {'type': 'image', 'attrs': {'object_name': 'ingest/figures/1c587fda-9beb-4024-acbb-b90450c0521c/bd0f447b3bbb0965814bd54eecb1c4b1cca4950ab430490bb5e1ba1988edd545.jpg'}}]

## Module: প্রসব পরবর্তী রক্তস্বল্পতা বা সাধারণ দুর্বলতা
module_id: 8441d848-a42f-4848-a557-85037831a8f6
cards: 3

### Card 1 (id: a11fc9cd-5f88-4663-88bc-104ba459f09d)
Title (bn): প্রসব পরবর্তী রক্তস্বল্পতা বা সাধারণ দুর্বলতা
Body (bn): প্রসব পরবর্তী সময়ে মা রক্তস্বল্পতা বা সাধারণ দুর্বলতায় ভুগতে পারেন। এই সমস্যা সমাধানে আয়রন সমৃদ্ধ খাবার যেমন সবুজ শাক-সবজি, মাছ, মাংস, ডিম, দুধ গ্রহণ করতে উৎসাহিত করুন। মাকে এক বেলার খাবার বেশি খেতে বলুন। এছাড়াও, আয়রন বড়ি প্রতিদিন দুইটি করে এক মাস গ্রহণ করতে পরামর্শ দিন।

### Card 2 (id: 303ea72c-6f0c-4fc9-b1fd-be6e036308f1)
Title (bn): প্রসব পরবর্তী তলপেটে ব্যথা
Body (bn): প্রসব পরবর্তী সময়ে মায়ের তলপেটে ব্যথা হতে পারে। এই ক্ষেত্রে রোগীকে আশ্বস্ত করুন। প্রয়োজনে প্যারাসিটামল ট্যাবলেট একটি করে দিনে তিনবার খেতে দিন।

### Card 3 (id: 56f19ae0-5cdd-48dd-94fe-22f7e28354cc)
Title (bn): প্রসব পরবর্তী পিঠে বা গায়ে ব্যথা
Body (bn): প্রসব পরবর্তী সময়ে মায়ের পিঠে বা গায়ে ব্যথা হতে পারে। এই সমস্যায় বেদনাশক ঔষধ আগের মতো গ্রহণ করতে বলুন। উষ্ণ পানিতে গোসল করতে উৎসাহিত করুন এবং রোগীকে আশ্বস্ত করুন। ক্যালসিয়াম ট্যাবলেট গ্রহণ করতে পরামর্শ দিন।

## Module: প্রসব পরবর্তী সেবা কী?
module_id: e7b05394-a774-4ae1-a5c4-955a9483a131
cards: 9

### Card 1 (id: 8573f5d0-f5e1-4dad-982e-29498d360893)
Title (bn): প্রসব পরবর্তী সেবা কী?
Body (bn): প্রসবের পর মায়ের জরায়ু ও অন্যান্য প্রজনন অঙ্গ স্বাভাবিক অবস্থায় ফিরে আসতে সাধারণত ছয় সপ্তাহ সময় লাগে। এই সময়কালকে প্রসব পরবর্তী সময় বা পিউরপেরিয়াম বলে। এই সময়ে প্রসূতি ও নবজাতককে যে সেবা দেওয়া প্রয়োজন তাকে একত্রে প্রসব পরবর্তী সেবা বলা হয়।

### Card 2 (id: e31e406d-91fe-47b2-b9da-07e727406d65)
Title (bn): প্রসব পরবর্তী সেবা কেন প্রয়োজন?
Body (bn): প্রসব পরবর্তী সেবা প্রয়োজন কারণ এর মাধ্যমে প্রসব পরবর্তী মা ও শিশুর জটিলতা চিহ্নিতকরণ ও ব্যবস্থা গ্রহণ করে মা ও শিশু মৃত্যু প্রতিরোধ করা যায়। এটি পরিবার পরিকল্পনা পরামর্শ দিতে এবং মা ও পরিবারকে মা ও শিশুর যত্নের পরামর্শ দিতে সাহায্য করে।

### Card 3 (id: 91c9f66a-1ce4-466f-b8e7-7e25d8a3b642)
Title (bn): প্রসব পরবর্তী পরিচর্যার উপাদান
Body (bn): প্রসব পরবর্তী পরিচর্যার উপাদানগুলো হলো প্রসব পরবর্তী ভিজিট, প্রসব পরবর্তী পরীক্ষা, প্রসব পরবর্তী পরামর্শ এবং প্রসব পরবর্তী জটিলতা চিহ্নিতকরণ ও ব্যবস্থা গ্রহণ।

### Card 4 (id: d2f017e6-fbb2-491e-80ed-9801dfdf7109)
Title (bn): প্রসব পরবর্তী ভিজিট (পিএনসি ভিজিট)
Body (bn): প্রসব পরবর্তী ভিজিটগুলো হলো: প্রথম ভিজিট চব্বিশ ঘন্টার মধ্যে, দ্বিতীয় ভিজিট তিন দিনের মধ্যে, তৃতীয় ভিজিট সাত থেকে চৌদ্দ দিনের মধ্যে এবং চতুর্থ ভিজিট বিয়াল্লিশ দিনের মধ্যে।

### Card 5 (id: b2cb2b3c-a7d0-4e71-9d34-8a32551275a7)
Title (bn): প্রসব পরবর্তী প্রদত্ত সেবাসমূহ
Body (bn): প্রসব পরবর্তী প্রদত্ত সেবাসমূহ হলো শারীরিক পরীক্ষা (মা ও নবজাতক উভয়ের), নবজাতকের জন্ম ওজন (আটচল্লিশ ঘন্টার মধ্যে), প্যাথলজিক্যাল পরীক্ষা যেমন রক্তে হিমোগ্লোবিন ও গ্লুকোজ পরীক্ষা, ইউরিনে অ্যালবুমিন ও বিলিরুবিন পরীক্ষা এবং প্রসব পরবর্তী পরামর্শ।

### Card 6 (id: e7a28a00-6503-4edc-a34c-1476a9379837)
Title (bn): মায়ের জরায়ুর উচ্চতা হ্রাস (ইনভলুশন)
Body (bn): বাচ্চা ভূমিষ্ঠ হওয়ার পরপরই জরায়ুর উচ্চতা মায়ের নাভী বরাবর থাকবে। এরপর প্রতিদিন এক আঙ্গুল করে কমতে থাকবে। দশ দিনের মাথায় তলপেটের ত্রিকোন হাড় বরাবর চলে আসবে এবং বিয়াল্লিশ দিনের মাথায় পূর্বের অবস্থায় ফেরত যাবে।

### Card 7 (id: 501bebad-6197-4c9d-9b58-aa62737f220e)
Title (bn): লকিয়া পর্যবেক্ষণ
Body (bn): প্রসবের পর সাধারণত সব মায়েদের রক্ত মিশ্রিত স্রাব বা লকিয়া দুই সপ্তাহ থেকে চার সপ্তাহ পর্যন্ত বের হয়। এর রং সময়ের উপর নির্ভর করে। প্রথম এক থেকে চার দিনে লাল, পাঁচ থেকে নয় দিনে হলুদ এবং দশ থেকে পনেরো দিনে এটা সাদা হয়ে যায়। যদি প্রসব পরবর্তী সময়ে পাঁচশো মিলি লিটার বা বেশি অথবা প্রতি ঘন্টায় একটি প্যাড ভিজে যায় তবে বুঝতে হবে উহা প্রসব পরবর্তী রক্তক্ষরণ। যদি বেশি দিন লকিয়ার রং লাল থাকে অথবা প্রচুর পরিমাণে যায় অথবা জ্বর ও তলপেটে ব্যথা সহ লকিয়া দুর্গন্ধযুক্ত হয় তাহলে বুঝতে হবে সংক্রমণ হয়েছে।

### Card 8 (id: b5e0a4ce-c38d-437e-a59d-a53df4040387)
Title (bn): পেরিনিয়ামের যত্ন
Body (bn): পেরিনিয়াম হলো শরীরের বাহিরের যোনিপথ ও মলদ্বারের মাঝে অবস্থিত একটি মাংসল অংশ। পেরিনিয়ামে কোনো সেলাই থাকলে তা শুকনা ও পরিষ্কার রাখতে হবে। প্রতিদিন প্রস্রাব ও পায়খানার পর বেশি পানি ব্যবহার করতে হবে যেন পেরিনিয়াম পরিষ্কার থাকে। চিকিৎসকের পরামর্শ অনুযায়ী অ্যান্টিবায়োটিক এবং অ্যান্টিসেপটিক মলম ব্যবহার করতে হবে। পেরিনিয়াম ও পেটের পেশীর ব্যায়াম করতে হবে।

### Card 9 (id: 34b6d1de-544c-4f13-8305-d893088b1aef)
Title (bn): প্রসূতি মায়ের জন্য পুষ্টি পরামর্শ
Body (bn): প্রসূতি মা প্রতিদিন নিচের ছয় ধরনের খাবার খাবেন: মাছ, মাংস, কলিজার যেকোনো একটি; ডিম; ঘন ডাল; দুধ বা দুগ্ধ জাতীয় যেকোনো খাবার; হলুদ ও কমলা রঙের সবজি বা ফল যেমন গাজর, মিষ্টি কুমড়া, আম, কাঁঠাল; এবং গাঢ় সবুজ শাক সবজি। প্রতিদিন তিনবেলা প্রধান খাবারের সাথে দুই বেলা নাস্তা খেতে হবে। পূর্ববর্তী খাবারের পরিমাণের সাথে অন্তত একমুঠ বেশি খেতে হবে। প্রতিদিন আট থেকে দশ গ্লাস পানি পান করতে হবে। প্রসবের পর বিয়াল্লিশ দিনের মধ্যে মাকে একটি উচ্চক্ষমতা সম্পন্ন দুই লক্ষ আই.ইউ ভিটামিন এ ক্যাপসুল খাওয়াতে হবে।

## Module: প্রসব পরবর্তী সেবা (Puerperium) কী?
module_id: d476db69-92ee-4973-b2c5-068a23a01bff
cards: 10

### Card 1 (id: 297a3b21-d417-4597-b036-5be754e99fd5)
Title (bn): প্রসব পরবর্তী সেবা (Puerperium) কী?
Body (bn): প্রসবের পর মায়ের জরায়ু ও অন্যান্য প্রজনন অঙ্গ স্বাভাবিক অবস্থায় ফিরে আসতে সাধারণত ছয় সপ্তাহ সময় লাগে। এই সময়কালকে প্রসব পরবর্তী সময় বা পিউরপেরিয়াম বলে। এই সময়ে প্রসূতি ও নবজাতককে যে সেবা দেওয়া প্রয়োজন তাকে একত্রে প্রসব পরবর্তী সেবা বলা হয়।

### Card 2 (id: ea25a5f5-a51c-4670-b49f-3a46639ba193)
Title (bn): প্রসব পরবর্তী সেবা কেন প্রয়োজন?
Body (bn): প্রসব পরবর্তী সেবা প্রয়োজন কারণ এর মাধ্যমে মা ও শিশুর জটিলতা চিহ্নিতকরণ ও ব্যবস্থা গ্রহণ করে মা ও শিশু মৃত্যু প্রতিরোধ করা যায়। এছাড়াও, পরিবার পরিকল্পনা বিষয়ে পরামর্শ দেওয়া হয় এবং মা ও পরিবারকে মা ও শিশুর যত্নের পরামর্শ দেওয়া হয়।

### Card 3 (id: 17686bf8-b77f-4317-a234-351e1c195b9d)
Title (bn): প্রসব পরবর্তী পরিচর্যার উপাদানসমূহ
Body (bn): প্রসব পরবর্তী পরিচর্যার উপাদানগুলো হলো: প্রসব পরবর্তী ভিজিট, প্রসব পরবর্তী পরীক্ষা, প্রসব পরবর্তী পরামর্শ এবং প্রসব পরবর্তী জটিলতা চিহ্নিতকরণ ও ব্যবস্থা গ্রহণ।

### Card 4 (id: e0300ed9-d9b7-411f-93e0-99f53864c4a7)
Title (bn): প্রসব পরবর্তী ভিজিটের সময়সূচী
Body (bn): প্রসব পরবর্তী ভিজিট বা পিএনসি ভিজিট চারটি ধাপে সম্পন্ন হয়। প্রথম ভিজিট ২৪ ঘন্টার মধ্যে, দ্বিতীয় ভিজিট তিন দিনের মধ্যে, তৃতীয় ভিজিট সাত থেকে চৌদ্দ দিনের মধ্যে এবং চতুর্থ ভিজিট বিয়াল্লিশ দিনের মধ্যে করতে হবে।

### Card 5 (id: b69f15d5-6645-4d8a-b6e7-0f8a8bffc2bb)
Title (bn): প্রসুতি মায়ের শারিরীক পরীক্ষা: সাধারণ বিষয়সমূহ
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'বাচ্চা ভূমিষ্ঠ হওয়ার পর প্রসুতি মায়ের শারিরীক পরীক্ষা করা প্রয়োজন। এই পরীক্ষাগুলোর মধ্যে রয়েছে মায়ের ওজন, রক্তচাপ, ইডিমা, তাপমাত্রা, নাড়ির গতি এবং জরায়ুর উচ্চতা হ্রাস পরীক্ষা করা। এছাড়াও, রক্তে হিমোগ্লোবিন ও গ্লুকোজ পরীক্ষা এবং ইউরিনে অ্যালবুমিন ও বিলিরুবিন পরীক্ষা করা দরকার। পেরিনিয়ামে সেলাই থাকলে তাতে কোনো সংক্রমণ হয়েছে কিনা, লকিয়া এবং স্তনে পর্যাপ্ত দুধ আসছে কিনা তাও পরীক্ষা করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a healthcare professional in a white coat holding a clipboard, speaking to a mother holding a baby. A medical cross symbol is in the background.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/a876893ebe84f9f6cdc5073f564adc94bc9ecaf915f9ac26a0223f338eaa4905.jpg'}}, {'type': 'image', 'attrs': {'alt': 'An illustration depicts a healthcare worker in a white coat and head covering examining the arm of a woman. Another woman stands nearby, holding a baby wrapped in a blue blanket. The background suggests an indoor setting with bamboo-like walls.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/317cd2f3383d5ca0a8a43f18a69212ed4f7676aa4ccc76aaf09540cc0a3f5507.jpg'}}]

### Card 6 (id: ccdc0470-e178-410e-ad12-51c357f4e407)
Title (bn): প্রসূতি মায়ের প্যাথলজিক্যাল পরীক্ষা
Body (bn): প্রসূতি মায়ের জন্য প্রয়োজনীয় প্যাথলজিক্যাল পরীক্ষাগুলো হলো: রক্তে হিমোগ্লোবিন ও গ্লুকোজ পরীক্ষা এবং ইউরিনে অ্যালবুমিন ও বিলিরুবিন পরীক্ষা।

### Card 7 (id: 9c727744-b4c5-4abb-a7ee-7ed1903941a0)
Title (bn): মায়ের জরায়ুর উচ্চতা হ্রাস (ইনভলুশন)
Body (bn): বাচ্চা ভূমিষ্ঠ হওয়ার পর পরই জরায়ুর উচ্চতা মায়ের নাভী বরাবর থাকবে। এরপর প্রতিদিন এক আঙ্গুল করে কমতে থাকবে। দশ দিনের মাথায় জরায়ু তলপেটের ত্রিকোন হাড় বরাবর চলে আসবে এবং বিয়াল্লিশ দিনের মাথায় পূর্বের অবস্থায় ফেরত যাবে।

### Card 8 (id: 216731e1-4c7c-49fa-a220-c94483d0b742)
Title (bn): লকিয়া: স্বাভাবিক অবস্থা
Body (bn): প্রসবের পর সাধারণত সব মায়েদের রক্ত মিশ্রিত স্রাব বা লকিয়া দুই সপ্তাহ থেকে চার সপ্তাহ পর্যন্ত বের হয়। এর রং সাধারণত সময়ের উপর নির্ভর করে। প্রথম এক থেকে চার দিনে লাল, পাঁচ থেকে নয় দিনে হলুদ এবং দশ থেকে পনেরো দিনে এটা সাদা হয়ে যায়। যিনি প্রসবের পর দেরীতে হাঁটাচলা শুরু করেন তার লাল লকিয়া বেশিদিন থাকতে পারে। লকিয়া নিঃসরণ অপরিণত প্রসবে কম এবং যমজ ও হাইড্রোমনিওস-এ বেশি থাকে।

### Card 9 (id: c811296b-41ad-4a36-a650-d6b8c0502b77)
Title (bn): লকিয়া: অস্বাভাবিক অবস্থা ও বিপদচিহ্ন
Body (bn): যদি প্রসব পরবর্তী সময় পাঁচশো মিলি লিটার বা বেশি অথবা প্রতি ঘন্টায় একটি প্যাড ভিজে যায়, তবে বুঝতে হবে উহা প্রসব পরবর্তী রক্তক্ষরণ। এই রক্তক্ষরণ প্রসবের ছয় ঘন্টা পরে থেকে শুরু হয়ে ছয় সপ্তাহের মধ্যে হতে পারে। যদি বেশি দিন লকিয়ার রং লাল থাকে অথবা প্রচুর পরিমাণে যায় অথবা জ্বর ও তলপেটে ব্যথা সহ লকিয়া দুর্গন্ধযুক্ত হয়, তাহলে বুঝতে হবে সংক্রমণ হয়েছে।

### Card 10 (id: 12450c9c-6380-4680-b543-ff7e27391ded)
Title (bn): পেরিনিয়ামের যত্ন
Body (bn): শরীরের বাহিরের যোনিপথ ও মলদ্বারের মাঝে অবস্থিত একটি মাংসল অংশ হলো পেরিনিয়াম। পেরিনিয়ামে কোনো সেলাই থাকলে সেলাইয়ের জায়গা শুকনা ও পরিষ্কার রাখতে হবে। প্রতিদিন প্রস্রাব ও পায়খানার পর বেশি পানি ব্যবহার করতে হবে যেন পেরিনিয়াম পরিষ্কার থাকে। চিকিৎসকের পরামর্শ অনুযায়ী এন্টিবায়োটিক এবং এন্টিসেপটিক মলম ব্যবহার করতে হবে। পেরিনিয়াম ও পেটের পেশীর ব্যায়াম করতে হবে।


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
