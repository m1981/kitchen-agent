# Evaluation Baseline — 2026-06-11

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GOLDEN DATASET EVALUATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total:   15 cases
Passed:  13 (87%)
Failed:  2
Time:    8.9 minutes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Pass/Fail by Case

| Case     | Topic                     | Result |
| -------- | ------------------------- | ------ |
| eval-001 | KB file discovery         | ✅     |
| eval-002 | General file listing      | ✅     |
| eval-003 | Blum drawer systems       | ✅     |
| eval-004 | Specific pricing          | ✅     |
| eval-005 | Hardware comparison       | ✅     |
| eval-006 | Assembly instructions     | ✅     |
| eval-007 | Ergonomic design          | ✅     |
| eval-008 | Missing information       | ✅     |
| eval-009 | Out-of-scope question     | ✅     |
| eval-010 | Read before edit          | ❌     |
| eval-011 | Citations to real files   | ✅     |
| eval-012 | Multiple source citations | ❌     |
| eval-013 | No hallucinated parts     | ✅     |
| eval-014 | Ambiguous query           | ✅     |
| eval-015 | Cross-file synthesis      | ✅     |

## 2 Failures Explained

| Case         | Why Failed                                                                                             |
| ------------ | ------------------------------------------------------------------------------------------------------ |
| **eval-010** | Agent searched + read file but didn't call `edit_file`. It described what to edit instead of doing it. |
| **eval-012** | Agent found only 1 source file instead of 2+. Searched for too specific a query.                       |

## Baseline Metrics

| Metric                  | Value                 |
| ----------------------- | --------------------- |
| **Pass rate**           | 87% (13/15)           |
| **Citation compliance** | ~80%                  |
| **Tool budget usage**   | 2-20K tokens per case |
| **Avg duration**        | 35 seconds per case   |

## Environment

- **Provider:** Anthropic Claude Sonnet 4
- **Tool budget:** 20% (25,600 tokens at 128K context)
- **Search context_lines:** 1 (default)
- **Citation verifier:** Relaxed (accepts valid Źródła section)
- **Commit:** `3e68326`

## Known Issues

1. **eval-010 (edit_file):** Agent sometimes describes edits instead of executing them. May need stronger prompt guidance.
2. **eval-012 (multiple citations):** Agent searches too specifically, finds only 1 source. May need search query expansion guidance.
