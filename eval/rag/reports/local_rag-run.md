Local RAG Chatbot E2E Report
============================
Run ID       : local_rag-20260902-103021
Dataset      : eval/rag/golden/Golden_Dataset.json
K            : 5
Corpus       : published=27, embedded=201
Evaluated    : 248

RETRIEVAL
─────────────────────────────────────────────
Hit At K              :  0.842
Mrr                   :  0.765
Precision At K        :  0.178
Recall At K           :  0.829
Ndcg At K             :  0.775
Retrieval Miss Rate   :  1.000

CONTEXT (PROXY)
─────────────────────────────────────────────
Gold Card Hit         : 0.842
Card Recall At K      : 0.434
Card Mrr              : 0.314

CITATION
─────────────────────────────────────────────
Strict Citation Accuracy: 0.797
Citation Or Retrieval Accuracy: 0.842
Citation Precision    : 0.513
Citation Recall       : 0.778
Spurious Citation Rate: 1.000
Uncited But Answered Rate: 1.000

ANSWER
─────────────────────────────────────────────
Token F1 (avg)        :  0.206
Token Recall (avg)    :  0.334
Exact Match (avg)     :  0.000
Grounding Overlap     :  0.070
Partial Correct Rate  :  0.000
Abstention Rate       :  1.000
False Refusal Rate    :  0.000
Citation Accuracy     :  0.842
Safety Pass Rate      :  0.000

LLM JUDGE
─────────────────────────────────────────────
Faithfulness          : 0.000
Answer Relevance      : 0.000
Groundedness          : 0.000
Reference Correctness : 0.000
Abstention Appropriateness: 0.000
Judge Error Rate      : 0.000

ERRORS
─────────────────────────────────────────────
Query Error Rate      : 1.000
Json Parse Failure Rate: 0.000
Empty Answer Rate     : 1.000
False Refusal Rate    : 0.000
Uncited But Answered Rate: 1.000

PERFORMANCE
─────────────────────────────────────────────
P50 Latency (E2E)     : 45977ms
P90 Latency (E2E)     : 65687ms
P95 Latency (E2E)     : 72698ms
P50 Embed Latency     : 95ms
Cost (avg tokens)     : in=2558 out=314

PER-CATEGORY
─────────────────────────────────────────────
counseling            : token_f1=0.197 hit_at_k=0.842 strict_citation_accuracy=0.737 faithfulness=0.000
cross_card_synthesis  : token_f1=0.242 hit_at_k=0.842 strict_citation_accuracy=0.842 faithfulness=0.000
drug_dosage           : token_f1=0.155 hit_at_k=0.824 strict_citation_accuracy=0.765 faithfulness=0.000
factual               : token_f1=0.258 hit_at_k=0.920 strict_citation_accuracy=0.840 faithfulness=0.000
negative              : token_f1=0.075 hit_at_k=0.000 strict_citation_accuracy=0.000 faithfulness=0.000
procedural            : token_f1=0.180 hit_at_k=0.681 strict_citation_accuracy=0.681 faithfulness=0.000
referral_decision     : token_f1=0.253 hit_at_k=0.952 strict_citation_accuracy=0.857 faithfulness=0.000
scenario_based        : token_f1=0.192 hit_at_k=1.000 strict_citation_accuracy=1.000 faithfulness=0.000
situational           : token_f1=0.204 hit_at_k=0.860 strict_citation_accuracy=0.837 faithfulness=0.000

BY ANSWERABLE
─────────────────────────────────────────────
no                    : count=26 token_f1=0.093 abstention=1.000
yes                   : count=222 token_f1=0.219 abstention=1.000
