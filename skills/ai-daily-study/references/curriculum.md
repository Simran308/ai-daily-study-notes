# Tech Stack curriculum

Work through these in order on 🧱 Tech Stack days, skipping anything already in `progress.json`. Each line is one lesson. A news event can bump a later item forward. When the list runs out, start "part 2" lessons that go deeper on the most important items (marked ★).

## 1. Foundations
1. ★ Tokens, context windows and pricing: how to estimate what a call costs
2. ★ Prompt engineering that still matters (system prompts, examples, XML structure)
3. Structured outputs and JSON schemas
4. ★ Tool use / function calling: the loop behind every agent
5. Streaming responses
6. Prompt caching: cutting cost and latency
7. Reasoning / "thinking" models and effort levels: when they're worth it

## 2. Retrieval (RAG)
8. ★ Embeddings: what they are and how similarity search works
9. ★ RAG basics: chunk → embed → retrieve → generate
10. Vector databases compared: pgvector, Chroma, Qdrant, Pinecone, Weaviate
11. Chunking strategies and why they make or break RAG
12. Hybrid search (BM25 + vectors) and reranking
13. GraphRAG and knowledge graphs
14. Long context vs RAG: when you don't need retrieval

## 3. Agents
15. ★ What makes something an agent (and when not to build one)
16. ★ Model Context Protocol (MCP): servers, clients, tools and resources
17. Agent Skills: packaging know-how for agents
18. Claude Agent SDK and OpenAI Agents SDK
19. LangGraph: stateful graph-based agents
20. CrewAI / AutoGen: multi-agent frameworks
21. Memory for agents: short-term, long-term, vector memory
22. Computer use and browser agents
23. Agent safety: prompt injection and guardrails

## 4. Quality
24. ★ Evals: building a test set for an LLM app
25. LLM-as-a-judge
26. Observability and tracing: Langfuse, LangSmith, Arize Phoenix, OpenTelemetry
27. Hallucination: causes and mitigation

## 5. Models & customisation
28. Open-weights models: Llama, Qwen, Mistral, DeepSeek, Gemma and how to choose
29. Running models locally: Ollama, LM Studio, llama.cpp
30. Quantization (GGUF, AWQ, 4-bit), with the actual tradeoffs
31. ★ Fine-tuning vs prompting vs RAG: decision guide
32. LoRA / QLoRA fine-tuning in practice
33. Distillation and small language models
34. Multimodal models: vision, audio and video input

## 6. Shipping
35. Inference serving: vLLM, TGI, SGLang
36. Hugging Face ecosystem tour: Hub, Transformers, Datasets, Spaces
37. Building AI UIs fast: Gradio, Streamlit, Vercel AI SDK
38. Deploying an LLM app: FastAPI + Docker + a cloud host
39. Cost optimisation: model routing, batching, caching
40. AI security and privacy: PII, data retention, red-teaming
