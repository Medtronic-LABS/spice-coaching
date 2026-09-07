# Golden expansion prompt — pnc (batch 1/2)

Expected records: 4

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
Generate exactly 4 new golden records distributed per the generation plan.

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
    "module_id": "102da01a-b99c-44c1-8469-5f09d87639be",
    "module_title": "প্রসব পরবর্তী মায়ের যত্ন: আয়রন ও ক্যালসিয়াম বড়ি",
    "record_count": 4,
    "suggested_query_types": [
      "Procedural",
      "Cross-card Synthesis",
      "Counseling",
      "Drug / Dosage"
    ],
    "card_ids": [
      "20b93b58-d6cf-4ce2-9a3d-7d352c7c029f",
      "f1c92c05-d7b4-4b76-8c7c-41c9d21cc29f",
      "18c3171f-d17c-496d-b0fb-a2f4e4402517",
      "b66830d4-393e-49e8-90a8-3b331729ba8b"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: প্রসব পরবর্তী মায়ের যত্ন: আয়রন ও ক্যালসিয়াম বড়ি
module_id: 102da01a-b99c-44c1-8469-5f09d87639be
cards: 4

### Card 1 (id: 20b93b58-d6cf-4ce2-9a3d-7d352c7c029f)
Title (bn): প্রসব পরবর্তী মায়ের যত্ন: আয়রন ও ক্যালসিয়াম বড়ি
Body (bn): বাচ্চা হওয়ার পর তিন মাস পর্যন্ত প্রতিদিন একটি করে আয়রন বড়ি দুপুরে ভরা পেটে খেতে হবে। প্রতিদিন দুটি করে ক্যালসিয়াম বড়ি সকালে ও রাতে ভরা পেটে খেতে হবে। আয়রন ও ক্যালসিয়াম বড়ি একসাথে খাওয়া যাবে না।

### Card 2 (id: f1c92c05-d7b4-4b76-8c7c-41c9d21cc29f)
Title (bn): প্রসব পরবর্তী মায়ের যত্ন: কাজ ও বিশ্রাম
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'প্রসবের পর ৪২ দিন পর্যন্ত ভারী কাজ যেমন কলসি দিয়ে পানি টানা, ভারী কাপড় কাচা, মাটিকাটা, ধানভানা, ইটভাঙ্গা করা যাবে না। সাত থেকে দশ দিন পর্যন্ত পূর্ণ বিশ্রামে থাকতে হবে। প্রতিদিন কমপক্ষে আট ঘন্টা ঘুমাতে হবে এবং দুই ঘন্টা বিশ্রাম নিতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration shows a family scene with a new mother holding a baby, drinking water offered by a man, while an older woman sits beside her on a bed, talking. The man is seated on a stool next to the bed.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/bd0f447b3bbb0965814bd54eecb1c4b1cca4950ab430490bb5e1ba1988edd545.jpg'}}]

### Card 3 (id: 18c3171f-d17c-496d-b0fb-a2f4e4402517)
Title (bn): প্রসব পরবর্তী মায়ের যত্ন: ব্যক্তিগত পরিচ্ছন্নতা
Body (bn): প্রসবের পর চার সপ্তাহ পর্যন্ত রক্ত মিশ্রিত স্রাব বের হয়, সেজন্য কাপড় ব্যবহার না করে ন্যাপকিন ব্যবহার করতে হবে (দিনে চারটি)। প্রতিদিন গোসল করতে হবে, স্তন পরিষ্কার করতে হবে এবং স্তনের বোটা ভিতরের দিকে দেওয়া থাকলে তেল দিয়ে মালিশ করতে হবে। পেরিনিয়ামে সেলাই থাকলে তা পরিষ্কার ও শুকনো রাখতে হবে।

### Card 4 (id: b66830d4-393e-49e8-90a8-3b331729ba8b)
Title (bn): প্রসব পরবর্তী মায়ের যত্ন: পরিবার পরিকল্পনা ও বিপদ চিহ্ন
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'প্রসবের ছয় সপ্তাহ পর্যন্ত স্বামী সহবাস করা যাবে না। প্রসবের পর দ্রুততম সময়ে যেকোনো জন্ম নিয়ন্ত্রণ পদ্ধতি গ্রহণ করতে হবে। প্রসব পরবর্তী বিপদ চিহ্ন দেখা দিলে সাথে সাথে হাসপাতালে বা উপজেলা স্বাস্থ্য কেন্দ্রে রেফার করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'An illustration of a healthcare professional in a white coat holding a clipboard, speaking to a mother holding a baby. A medical cross symbol is in the background.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/a876893ebe84f9f6cdc5073f564adc94bc9ecaf915f9ac26a0223f338eaa4905.jpg'}}, {'type': 'image', 'attrs': {'alt': 'An illustration depicts a healthcare worker in a white coat and head covering examining the arm of a woman. Another woman stands nearby, holding a baby wrapped in a blue blanket. The background suggests an indoor setting with bamboo-like walls.', 'object_name': 'ingest/figures/8b8329e2-45ed-46f1-a516-f113bea0b376/317cd2f3383d5ca0a8a43f18a69212ed4f7676aa4ccc76aaf09540cc0a3f5507.jpg'}}]


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
