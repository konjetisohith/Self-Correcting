# Local LLM Evaluation Platform

An evaluation platform for comparing locally running Large Language Models (LLMs) on sentiment analysis, question answering, tool-use decisions, and context pruning using Ollama.

## Overview

This project evaluates multiple local LLMs using benchmark datasets and a synthetic tool-use dataset. It measures task accuracy, answer quality, fabrication on unanswerable questions, tool-use behavior, inference latency, and the effect of context pruning.

A Streamlit dashboard presents the results through interactive tables and visualizations, making it easier to compare model behavior and identify failure cases.

## Key Features

- **Multi-model evaluation:** Compare Qwen 2.5:3B, Llama 3.2:3B, and Qwen 2.5 Coder:3B.
- **Sentiment analysis:** Evaluate sentiment classification using a GLUE SST-2 validation subset.
- **Question answering:** Evaluate answer quality and abstention behavior using a SQuAD 2.0 validation subset.
- **Tool-use evaluation:** Test whether models select tools appropriately using a synthetic labelled dataset.
- **Context pruning:** Compare full-context inference against a Top-K pruning configuration.
- **Performance metrics:** Measure accuracy, Exact Match (EM), token-level F1, fabrication rate, latency, and tokens per second.
- **Failure analysis:** Inspect unsuccessful predictions and model outputs.
- **Interactive dashboard:** Explore results through Streamlit.
- **Local inference:** Run models using Ollama without requiring a hosted LLM API.

## Tech Stack

- Python
- Ollama
- Streamlit
- Pandas
- Pytest
- JSONL-based evaluation records

## System Architecture

1. **Dataset loader:** Loads benchmark scenarios from local dataset files.
2. **Model interface:** Sends prompts to local Ollama models.
3. **Evaluation runner:** Executes scenarios across models and configurations.
4. **Metrics and reporting:** Computes task-specific scores and model comparisons.
5. **Results storage:** Saves evaluation records in JSONL format.
6. **Dashboard:** Displays leaderboards, pruning comparisons, latency, failure analysis, and run metadata.

## Models Evaluated

| Model | Purpose |
|---|---|
| Qwen 2.5:3B | General-purpose local LLM evaluation |
| Llama 3.2:3B | Comparative model evaluation |
| Qwen 2.5 Coder:3B | Code-oriented model evaluated on the same tasks |

## Evaluation Results

The full benchmark produced the following results in the tested configuration.

### Sentiment Analysis

| Model | Accuracy |
|---|---:|
| Qwen 2.5:3B | 96% |
| Qwen 2.5 Coder:3B | 95% |
| Llama 3.2:3B | 91% |
| Rule-based baseline | 69% |

### Question Answering

| Model | Exact Match | Token F1 | Fabrication Rate |
|---|---:|---:|---:|
| Qwen 2.5:3B | 74% | 82.1% | 46% |
| Qwen 2.5 Coder:3B | 78% | 84.6% | 65% |
| Llama 3.2:3B | 63% | 70.7% | 57% |

### Tool Use

| Model | Overall Accuracy |
|---|---:|
| Qwen 2.5:3B | 85% |
| Qwen 2.5 Coder:3B | 82.5% |
| Llama 3.2:3B | 82.5% |

### Context Pruning

The Top-K:2 configuration reduced the evaluated question-answering context by approximately 60%. However, measured success rates decreased for all three models compared with using the original context.

This illustrates the trade-off between reducing context and preserving information required for accurate answers.

## Understanding the Metrics

- **Accuracy:** Proportion of scenarios classified or completed correctly.
- **Exact Match (EM):** Proportion of answers that exactly match the reference answer under the evaluator's normalization rules.
- **Token F1:** Token-level overlap between the generated and reference answers.
- **Fabrication rate:** Proportion of unanswerable questions for which the model generated an answer instead of abstaining.
- **Latency:** Time taken to generate a response, excluding model-loading time according to the benchmark configuration.
- **Tokens per
