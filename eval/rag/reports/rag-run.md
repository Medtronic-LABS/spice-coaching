RAG Chatbot E2E Report
======================
Run ID       : rag-20260831-135548
Dataset      : eval/rag/golden/Golden_Dataset.json
K            : 5
Corpus       : published=27, embedded=27
Evaluated    : 248

RETRIEVAL
─────────────────────────────────────────────
Hit At K              :  0.982
Mrr                   :  0.849
Precision At K        :  0.214
Recall At K           :  0.973
Ndcg At K             :  0.877
Retrieval Miss Rate   :  1.000

CONTEXT (PROXY)
─────────────────────────────────────────────
Gold Card Hit         : 0.982
Card Recall At K      : 0.490
Card Mrr              : 0.344

CITATION
─────────────────────────────────────────────
Strict Citation Accuracy: 0.946
Citation Or Retrieval Accuracy: 0.982
Citation Precision    : 0.664
Citation Recall       : 0.930
Spurious Citation Rate: 0.000
Uncited But Answered Rate: 0.000

ANSWER
─────────────────────────────────────────────
Token F1 (avg)        :  0.298
Token Recall (avg)    :  0.472
Exact Match (avg)     :  0.004
Grounding Overlap     :  0.283
Partial Correct Rate  :  0.000
Abstention Rate       :  1.000
False Refusal Rate    :  1.000
Citation Accuracy     :  0.982
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
Query Error Rate      : 0.000
Json Parse Failure Rate: 0.000
Empty Answer Rate     : 0.000
False Refusal Rate    : 1.000
Uncited But Answered Rate: 0.000

PERFORMANCE
─────────────────────────────────────────────
P50 Latency (E2E)     : 8065ms
P90 Latency (E2E)     : 10470ms
P95 Latency (E2E)     : 12025ms
P50 Embed Latency     : 820ms
Cost (avg tokens)     : in=4747 out=302

PER-CATEGORY
─────────────────────────────────────────────
counseling            : token_f1=0.236 hit_at_k=1.000 strict_citation_accuracy=1.000 faithfulness=0.000
cross_card_synthesis  : token_f1=0.318 hit_at_k=1.000 strict_citation_accuracy=0.947 faithfulness=0.000
drug_dosage           : token_f1=0.260 hit_at_k=1.000 strict_citation_accuracy=1.000 faithfulness=0.000
factual               : token_f1=0.384 hit_at_k=0.980 strict_citation_accuracy=0.980 faithfulness=0.000
negative              : token_f1=0.125 hit_at_k=0.000 strict_citation_accuracy=0.000 faithfulness=0.000
procedural            : token_f1=0.319 hit_at_k=0.979 strict_citation_accuracy=0.936 faithfulness=0.000
referral_decision     : token_f1=0.319 hit_at_k=0.952 strict_citation_accuracy=0.762 faithfulness=0.000
scenario_based        : token_f1=0.215 hit_at_k=1.000 strict_citation_accuracy=1.000 faithfulness=0.000
situational           : token_f1=0.269 hit_at_k=0.977 strict_citation_accuracy=0.953 faithfulness=0.000

BY ANSWERABLE
─────────────────────────────────────────────
no                    : count=26 token_f1=0.136 abstention=1.000
yes                   : count=222 token_f1=0.317 abstention=1.000
