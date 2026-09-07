# Golden expansion prompt — documentation (batch 0/0)

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

DOMAIN: documentation
Generate exactly 12 new golden records distributed per the generation plan.

## FEW-SHOT EXAMPLES
[
  {
    "question_en": "The EPI card does not have IPV-2 information, but the mother says the child was vaccinated. What should I do in this situation?",
    "expected_answer_en": "Do not rely solely on verbal information. Re-verify the EPI card and confirm with the respective Health Assistant. Do not guess information until confirmed.",
    "question_bn": "EPI কার্ডে IPV-2-এর তথ্য লেখা নেই, কিন্তু মা বলছেন শিশুকে টিকা দেওয়া হয়েছে। এ অবস্থায় আমি কী করব?",
    "expected_answer_bn": "শুধুমাত্র মৌখিক তথ্যের ওপর ভিত্তি করবেন না। EPI কার্ড পুনরায় যাচাই করুন এবং সংশ্লিষ্ট হেলথ অ্যাসিস্ট্যান্টের সাথে নিশ্চিত করুন। নিশ্চিত না হওয়া পর্যন্ত তথ্য অনুমান করবেন না।",
    "source_card_id": [
      "c5a75002-e4b6-46e3-ad4a-3fc55d3b3921",
      "44051a6f-21c2-434f-996e-4c5fbc5992d6"
    ],
    "query_type": "Scenario-based",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Documentation Verification & Coordination",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "065e5a37-6dcf-4fe4-9450-b05176ad13ac"
    ]
  },
  {
    "question_en": "The child missed IPV-2. Does the child need to restart all doses, or just get the missed dose?",
    "expected_answer_en": "There is no need to restart the entire schedule. Just give the missed IPV-2 dose as soon as possible. Consult the Health Assistant for final decisions.",
    "question_bn": "শিশুটিকে IPV-2 মিস করেছে। এখন কি তাকে প্রথম থেকে আবার সব ডোজ দিতে হবে, নাকি শুধু মিসড ডোজটাই দিলে হবে?",
    "expected_answer_bn": "পুরো শিডিউল পুনরায় শুরু করার প্রয়োজন নেই। শুধুমাত্র মিসড IPV-2 ডোজটি যত দ্রুত সম্ভব দিতে হবে। চূড়ান্ত সিদ্ধান্তের জন্য হেলথ অ্যাসিস্ট্যান্টের পরামর্শ নিন।",
    "source_card_id": [
      "44051a6f-21c2-434f-996e-4c5fbc5992d6",
      "c5a75002-e4b6-46e3-ad4a-3fc55d3b3921"
    ],
    "query_type": "Procedural",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Immunization Catch-up Rule",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "065e5a37-6dcf-4fe4-9450-b05176ad13ac"
    ]
  },
  {
    "question_en": "It was discovered from the EPI card that a child missed a scheduled vaccine. As an SK, how will you enlist the child as a 'missed vaccination child'?",
    "expected_answer_en": "Include the child's information in the 'missed vaccination child' list/form according to the prescribed method and provide this information to the respective Health Assistant, also informing them verbally if necessary.",
    "question_bn": "একজন শিশুর নির্ধারিত সময়ের একটি টিকা দেওয়া হয়নি বলে EPI কার্ড দেখে জানা গেল। একজন SK হিসেবে আপনি কীভাবে শিশুটিকে missed vaccination child হিসেবে তালিকাভুক্ত করবেন?",
    "expected_answer_bn": "নির্ধারিত পদ্ধতি অনুযায়ী 'missed vaccination child'-এর তালিকা/ফর্মে শিশুর তথ্য অন্তর্ভুক্ত করুন এবং সংশ্লিষ্ট হেলথ অ্যাসিস্ট্যান্টকে তথ্যটি দিন, প্রয়োজনে মৌখিকভাবেও জানান।",
    "source_card_id": [
      "c5a75002-e4b6-46e3-ad4a-3fc55d3b3921"
    ],
    "query_type": "Procedural",
    "linguistic_variation": "Standard Written Bengali",
    "chw_pattern": "Tracking & Reporting Defaulters",
    "answerable": "yes",
    "confidence": "high",
    "module_id": [
      "065e5a37-6dcf-4fe4-9450-b05176ad13ac"
    ]
  }
]

## GENERATION PLAN
[
  {
    "module_id": "84ace972-b78f-4caa-a504-510bb8b61984",
    "module_title": "Tested for module Test",
    "record_count": 4,
    "suggested_query_types": [
      "Factual",
      "Situational",
      "Procedural",
      "Referral Decision"
    ],
    "card_ids": [
      "ae6a4e38-7c01-4ea8-949d-2f873a75d1db",
      "6fe4b38f-17e1-4aca-8435-54b00d06a2c2"
    ]
  },
  {
    "module_id": "6fa7a48b-fce5-48f6-8eaa-afbb56438bf6",
    "module_title": "মা, নবজাতক ও শিশুস্বাস্থ্য তথ্য কার্ডের গুরুত্ব",
    "record_count": 8,
    "suggested_query_types": [
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
      "30249dcf-fc1a-4255-a91e-6dbc2cfbb552",
      "f66c1d46-ee81-4e9b-8abd-1c3e0b2b9767",
      "99ce0bb8-3b99-48d9-87f5-c5fd25c8ba78",
      "c6390e1c-4558-469d-a13f-985ca2cb0ab5",
      "af773e4f-1d36-4a7e-a380-a4d2c68dab33",
      "638c5a89-2709-4065-bd37-867e9cd75f4b",
      "6fb98ab8-badc-4dcd-acb2-df859b89776f",
      "e0ecece8-56ae-43be-8e93-19c0c03118fb",
      "71dab24a-7552-490b-8788-8c5e981b1561",
      "1c1a7dfa-542c-44e4-af87-9baa63a335f2"
    ]
  }
]

## TAXONOMY
query_type: ["Factual", "Situational", "Scenario-based", "Procedural", "Referral Decision", "Drug / Dosage", "Cross-card Synthesis", "Negative", "Counseling", "Ambiguous"]
chw_pattern: ["None", "Clinical Protocol & Escalation", "Counseling & Home Management", "Counseling & Birth Preparedness", "Clinical Escalation & Patient Counseling", "Lifestyle Counseling", "Chronic Disease Counseling", "Motivational Counseling & Overcoming Reluctance", "Motivational Counseling & Risk Awareness", "Symptom Identification", "Emergency Management & Referral", "Etiology Understanding", "Prevention & Patient Education", "Postnatal Maternal Counseling", "Newborn Care Counseling", "Danger Signs & Referral Criteria", "Maternal Danger Signs & Referral", "Problem Identification & Escalation", "Self-care & Breast Care", "Physiological Assessment", "Differential Diagnosis & Complication Recognition", "Documentation Verification & Coordination", "Immunization Catch-up Rule", "Tracking & Reporting Defaulters", "Diagnostic Procedure", "Treatment Protocol", "Referral & Escalation", "Patient Education", "Cross-module Integration", "Out-of-scope Refusal"]
linguistic_variation: ["Standard Written Bengali", "Colloquial Spoken Bengali", "Roman Transliteration", "Banglish"]

## MODULE CORPUS
## Module: Tested for module Test
module_id: 84ace972-b78f-4caa-a504-510bb8b61984
cards: 2

### Card 1 (id: ae6a4e38-7c01-4ea8-949d-2f873a75d1db)
Title (bn): Tested for card
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'Card body Test', 'type': 'text'}]}]

### Card 2 (id: 6fe4b38f-17e1-4aca-8435-54b00d06a2c2)
Title (bn): Tested card two
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'New Cads for documentation', 'type': 'text'}]}]

## Module: মা, নবজাতক ও শিশুস্বাস্থ্য তথ্য কার্ডের গুরুত্ব
module_id: 6fa7a48b-fce5-48f6-8eaa-afbb56438bf6
cards: 10

### Card 1 (id: 30249dcf-fc1a-4255-a91e-6dbc2cfbb552)
Title (bn): মা, নবজাতক ও শিশুস্বাস্থ্য তথ্য কার্ডের গুরুত্ব
Body (bn): মা, নবজাতক ও শিশুস্বাস্থ্য তথ্য কার্ড সঠিকভাবে পূরণ করতে পারা গুরুত্বপূর্ণ। এই কার্ড পূরণের মাধ্যমে অনেক তথ্য জানা যায়, যার ফলে গর্ভবতীর কোনো ছোটখাট সমস্যা বা জটিলতার দ্রুত ব্যবস্থা গ্রহণ করা সম্ভব। এজন্য কার্ড অত্যন্ত যত্ন, ধৈর্য ও মনোযোগ সহকারে সঠিকভাবে পূরণ করা প্রয়োজন।

### Card 2 (id: f66c1d46-ee81-4e9b-8abd-1c3e0b2b9767)
Title (bn): গর্ভবতী মহিলার প্রাথমিক তথ্য লিপিবদ্ধকরণ
Body (bn): গর্ভবতী মহিলার নাম এই ঘরে লিখতে হবে। গর্ভবতীর বয়স যে তারিখে গর্ভবতী মহিলা চিহ্নিত হয়েছেন সেই তারিখে নির্ণয় করে লিখতে হবে। জাতীয় পরিচয়পত্র বা টিটি টিকার কার্ড দেখে বয়স লেখা যাবে। স্বাস্থ্যকর্মী ট্যাব অনুযায়ী গর্ভবতী মহিলা যে খানায় অবস্থান করছেন সেই খানার নম্বর লিখতে হবে। গর্ভকালীন পরিচর্যা প্রদানকারী স্বাস্থ্যকর্মী তার নাম ও মোবাইল নম্বর এই ঘরে লিখবেন। গর্ভবতী মহিলার সাথে কথা বলে শেষ মাসিক শুরুর তারিখ বাংলা অথবা ইংরেজী মাস অনুসারে লিখতে হবে। প্রসবের সম্ভাব্য তারিখ শেষ মাসিক শুরুর তারিখের সাথে 9 মাস 7 দিন যোগ করে যে তারিখটি পাওয়া যাবে তা লিখতে হবে।

### Card 3 (id: 99ce0bb8-3b99-48d9-87f5-c5fd25c8ba78)
Title (bn): পূর্বের গর্ভের জটিলতার তথ্য লিপিবদ্ধকরণ
Body (bn): গর্ভবতী মহিলার সাথে আলাপ করে কার্ডে উল্লেখিত সমস্যাগুলির (সিজারিয়ান অপারেশন, গর্ভপাত, প্রসব পূর্ব বা পরবর্তী রক্তক্ষরণ, প্রিএকলাম্পশিয়া, একলাম্পশিয়া) কোনটির ইতিহাস থাকলে তার উপর টিক (√) চিহ্ন দিতে হবে।

### Card 4 (id: c6390e1c-4558-469d-a13f-985ca2cb0ab5)
Title (bn): গর্ভবতী মহিলার ভিজিট ও শারীরিক পরিমাপের তথ্য
Body (bn): স্বাস্থ্যকর্মী যে দিন গর্ভবতী মহিলাকে এএনসি সেবা দিবেন সেই ভিজিটের তারিখ লিখতে হবে। স্বাস্থ্যকর্মী গর্ভের যে মাসে গর্ভবতী মহিলাকে এএনসি সেবা দিবেন সংখ্যা অনুযায়ী সেই মাস লিখতে হবে। এএনসি চেকআপের সময় গর্ভবতী মহিলার ওজন (কেজিতে) সঠিকভাবে নির্ণয় করে সংখ্যায় লিখতে হবে। প্রথম এএনসি চেকআপে গর্ভবতী মহিলার উচ্চতা (সেন্টিমিটারে) সঠিকভাবে নির্ণয় করে সংখ্যায় লিখতে হবে। থার্মোমিটারে গর্ভবতী মহিলার শরীরের তাপমাত্রা (ফারেনহাইট ডিগ্রিতে) সঠিকভাবে মেপে সংখ্যায় লিখতে হবে। গর্ভবতী মহিলার রক্তচাপ সঠিকভাবে পরীক্ষা করে সংখ্যায় লিখতে হবে, যেমন 120 over 80 mmHg। ফিতা (মেজারিং টেপ) দিয়ে গর্ভবতী মায়ের জরায়ুর উচ্চতা (সেন্টিমিটারে) সঠিকভাবে মেপে সংখ্যায় লিখতে হবে।

### Card 5 (id: af773e4f-1d36-4a7e-a380-a4d2c68dab33)
Title (bn): গর্ভস্থ শিশুর নড়াচড়া ও ইডিমা লিপিবদ্ধকরণ
Body (bn): গর্ভবতী মহিলার সাথে কথা বলে গর্ভস্থ শিশু সাধারণত দৈনিক (অর্থাৎ 24 ঘন্টায়) যতবার নড়াচড়া করে তা সংখ্যায় লিখতে হবে। 20 সপ্তাহ (5 মাস) থেকে গর্ভস্থ শিশুর নড়াচড়া অনুভব করা যায় এবং এক্ষেত্রে সংশ্লিষ্ট ঘর পূরণ করতে হবে। স্বাভাবিক অবস্থায় গর্ভস্থ শিশু দিনে 8 থেকে 10 বার নড়াচড়া করে। নড়াচড়া না করলে অথবা কম নড়াচড়া করলে হাসপাতালে রেফার করতে হবে। এএনসি চেকআপের সময় সঠিকভাবে পরীক্ষা করে গর্ভবতী মহিলার ইডিমা পাওয়া গেলে '+' চিহ্ন দিতে হবে। অন্যথায় '-' চিহ্ন দিতে হবে।

### Card 6 (id: 638c5a89-2709-4065-bd37-867e9cd75f4b)
Title (bn): গর্ভবতী মহিলার রক্ত ও প্রস্রাব পরীক্ষার ফলাফল
Body (bn): এএনসি চেকআপের সময় গ্লুকোমিটারে গর্ভবতীর গ্লুকোজ নির্ণয় করা হয়ে থাকলে (অথবা প্যাথলজিক্যাল পরীক্ষার রিপোর্ট থাকলে) ফলাফল লিখতে হবে, যেমন 7.0 মিলিমোল/লিটার। এএনসি চেকআপের সময় হিমোগ্লোবিনোমিটারে গর্ভবতীর রক্তের হিমোগ্লোবিনের মাত্রা নির্ণয় করে সংখ্যায় লিখতে হবে, যেমন 12.5 gm/dl। ইউরিন স্ট্রিপের মাধ্যমে গর্ভবতীর প্রস্রাব পরীক্ষা করে প্রাপ্ত ফলাফল চিহ্ন দিয়ে লিখতে হবে। যেমন - অস্বাভাবিক/পজেটিভ হলে কৌটার নির্দেশনা অনুযায়ী টিক চিহ্ন দিয়ে (+/++/+++) ফলাফল লিখতে হবে। ফলাফল স্বাভাবিক থাকলে (-) টিক চিহ্ন দিয়ে ফলাফল লিখতে হবে। বিলিরুবিন পরীক্ষার ক্ষেত্রেও একই পদ্ধতি অনুসরণ করতে হবে।

### Card 7 (id: 6fb98ab8-badc-4dcd-acb2-df859b89776f)
Title (bn): আল্ট্রাসোনোগ্রাম, টিটি টিকা ও আয়রন/ক্যালসিয়াম ট্যাবলেট
Body (bn): আল্ট্রাসোনোগ্রাম করা হয়ে থাকলে টিক (✓) চিহ্ন দিতে হবে। 20 সপ্তাহের মাঝে আল্ট্রাসোনোগ্রাম করার জন্য উৎসাহিত করা। আল্ট্রাসোনোগ্রাম করা না হয়ে থাকলে (X) চিহ্ন দিতে হবে। গর্ভবতী মহিলার সাথে কথা বলে অথবা টিটি টিকার কার্ড দেখে লিখতে হবে। টিকার কার্ড না থাকলে টিটি টিকার সম্পর্কিত ডোজ সংখ্যায় লিখে পাশে '+' দিতে হবে। পূর্বে টিটি টিকার ডোজ সম্পূর্ণ করে থাকলে কার্ডে সম্পূর্ণ কথাটি লিখতে হবে। এএনসি চেকআপের সময় গর্ভবতী মহিলাকে সেবা প্রদান করার সময় আয়রন বড়ি নিয়ম অনুযায়ী খাচ্ছে কিনা তা জিজ্ঞাসা করে এই ঘরে টিক (✓) চিহ্ন দিতে হবে। আয়রন বড়ি না খেলে (X) চিহ্ন দিতে হবে। আয়রন বড়ি অনিয়মিত খেলে ঘরে টিক (✓) চিহ্ন দিয়ে অনিয়মিত কথাটি লিখতে হবে। ক্যালসিয়াম ট্যাবলেটের ক্ষেত্রেও একই পদ্ধতি অনুসরণ করতে হবে।

### Card 8 (id: e0ecece8-56ae-43be-8e93-19c0c03118fb)
Title (bn): নবজাতকের জন্ম ও শারীরিক অবস্থার তথ্য
Body (bn): [{'type': 'paragraph', 'content': [{'text': 'নবজাতকের জন্ম তারিখ লিখতে হবে। চিকিৎসক/স্বাস্থ্যকর্মীর ব্যবস্থাপত্র দেখে অথবা প্রসূতি বা পরিবারের অন্য সদস্যদের সাথে আলাপ করে নবজাতকের জন্ম ওজন লিখতে হবে। নবজাতকের শ্বাসের হার ফাঁকা ঘরে লিখতে হবে। নবজাতকের শ্বাস অস্বাভাবিক থাকলে অর্থাৎ শ্বাসকষ্ট অথবা শ্বাসের অস্বাভাবিক শব্দ যেমন ঘড়ঘড় বা বাঁশির মত শাঁইশাঁই আওয়াজ থাকলে এবং শান্ত অবস্থায় শ্বাসের গতি মিনিটে 60 বারের বেশি থাকলে চিকিৎসকের কাছে রেফার করতে হবে। নবজাতকের নাভী শুকনো ও স্বাভাবিক থাকলে টিক (√) চিহ্ন দিতে হবে। নাভী অস্বাভাবিক থাকলে অস্বাভাবিক এর উপর (✔) চিহ্ন দিতে হবে এবং চিকিৎসকের কাছে রেফার করতে হবে। নবজাতকের চোখ স্বাভাবিক হলে টিক (√) চিহ্ন দিতে হবে। অস্বাভাবিক থাকলে চিকিৎসকের কাছে রেফার করতে হবে। নবজাতকের ত্বক স্বাভাবিক হলে স্বাভাবিক এর উপর টিক (√) চিহ্ন দিতে হবে। অস্বাভাবিক থাকলে চিকিৎসকের কাছে রেফার করতে হবে।', 'type': 'text'}]}, {'type': 'image', 'attrs': {'alt': 'A drawing of a newborn baby lying on its back, with the umbilical cord still attached and clamped. The baby is depicted with its head turned to the left and arms bent.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/7153e5231e96388d4119747854d68ec6c98c80c33441232a917475e90b220b55.jpg'}}, {'type': 'image', 'attrs': {'alt': 'dreamstime.com\nA stylized illustration depicts a fetus or newborn baby lying on a weighing scale. The baby is light orange, and the scale is grey with a dial and needle.', 'object_name': 'ingest/figures/6f9cf896-2849-4823-8962-367fac6c7ed2/01bb0b0dd884677bdf162f4b19b0913098b4bdb8aff7396f29d729d71eeb9468.jpg'}}]

### Card 9 (id: 71dab24a-7552-490b-8788-8c5e981b1561)
Title (bn): নবজাতকের জন্মগত ত্রুটি ও খাওয়ানোর তথ্য
Body (bn): নবজাতকের কোন দৃশ্যমান জন্মগত ত্রুটি (তালু কাটা, মুগুর পা ইত্যাদি) স্বাস্থ্যকর্মী নিজে পর্যবেক্ষণ করে অথবা অন্য কোন ত্রুটি থাকলে চিকিৎসকের ব্যবস্থাপত্র অনুযায়ী স্পষ্টভাবে লিখতে হবে। প্রসূতি মা/যত্নকারির সাথে আলাপ করে নবজাতককে জন্মের পর প্রথম 1 ঘন্টায় যে খাবার (মায়ের বুকের দুধ, পানি, চিনির পানি, গরুর দুধ ইত্যাদি) খাওয়ানো হয়েছে তা সংক্ষেপে লিখতে হবে। প্রসূতি মা/যত্নকারির সাথে আলাপ করে নবজাতককে গত 24 ঘন্টায় যে খাবার (মায়ের বুকের দুধ, পানি, চিনির পানি, গরুর দুধ ইত্যাদি) খাওয়ানো হয়েছে তা সংক্ষেপে লিখতে হবে।

### Card 10 (id: 1c1a7dfa-542c-44e4-af87-9baa63a335f2)
Title (bn): প্রসূতি মায়ের প্রসব পরবর্তী জটিলতা ও রেফারেল
Body (bn): পিএনসি চেকআপের সময় প্রসূতি মাকে জিজ্ঞাসা করুন - লোফিয়া (প্রসব পরবর্তী রক্ত মিশ্রিত স্রাব যা সাধারণত 2 থেকে 4 সপ্তাহ পর্যন্ত হতে পারে) অস্বাভাবিক থাকলে লোফিয়ার উপর টিক (✓) চিহ্ন দিয়ে ফাঁকা ঘরে অস্বাভাবিক লিখতে হবে। দুর্গন্ধযুক্ত স্রাব থাকলে দুর্গন্ধযুক্ত স্রাব উপর টিক (✓) চিহ্ন দিয়ে ফাঁকা ঘরে অস্বাভাবিক লিখতে হবে। তলপেটে ব্যথা থাকলে তলপেটে ব্যথার উপর টিক (✓) চিহ্ন দিয়ে ফাঁকা ঘরে অস্বাভাবিক লিখতে হবে। পেরিনিয়াম সেলাই আছে কিনা থাকলে ফাঁকা ঘরে টিক (✓) চিহ্ন দিতে হবে। অতিরিক্ত রক্তস্রাব অর্থাৎ 6 ঘণ্টা পর থেকে 6 সপ্তাহ পর্যন্ত যেকোনো সময়ে 500 মিলি বা তার বেশি রক্তপাত হলে অর্থাৎ আধা ঘন্টায় 2টা প্যাড ভিজে গেলে পাশের ফাঁকা (☐) ঘরে টিক (✓) চিহ্ন দিতে হবে এবং হাসপাতাল রেফার করতে হবে। গর্ভকালীন ও প্রসবপরবর্তী সময়ে শরীরে পানি আসা, খুব বেশি মাথাব্যথা, চোখে ঝাপসা দেখা, তিনদিনের বেশি জ্বর বা দুর্গন্ধযুক্ত স্রাব, খুব বেশি রক্তস্রাব বা গর্ভফুল না পড়া, খিঁচুনি ইত্যাদি উপসর্গ/অসুবিধা/জটিলতা হলে তা এই ঘরে স্পষ্টভাবে লিখে রাখতে হবে এবং চিকিৎসকের কাছে রেফার করতে হবে।


## OUTPUT SCHEMA
Each record object must include:
question_en, question_bn, expected_answer_en, expected_answer_bn,
module_id (array of UUID strings), source_card_id (array of UUID strings),
query_type, linguistic_variation, chw_pattern, answerable, confidence.
Return {"records": [ ... ]} only.
