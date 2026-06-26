from typing import List, Tuple, Dict, Any, Set

STOP_WORDS = {"a", "an", "the", "and", "or", "in", "on", "at", "to", "for",
              "of", "with", "by", "from", "up", "is", "it", "its", "all",
              "me", "my", "give", "get", "then"}

def _get_word_set(text: str) -> Set[str]:
    return set(text.lower().split()) - STOP_WORDS

def compute_similarity(s1: str, s2: str) -> float:
    w1 = _get_word_set(s1)
    w2 = _get_word_set(s2)
    union_len = len(w1 | w2)
    if union_len == 0:
        return 0.0
    return len(w1 & w2) / union_len

def compact_memory(executions: List[Dict[str, Any]], threshold: float = 0.6) -> Tuple[List[Dict[str, Any]], str]:
    """
    Consolidates similar executions to keep memory footprint bounded.
    Group executions that have similarity >= threshold.
    For groups of size >= 2:
      - Merges them into a single consolidated execution.
      - Keeps the most efficient (lowest api call count) successful execution's steps/path.
      - Aggregates lessons learned and constraints.
      - Retains chronological improvement trends (e.g. original call counts) in metadata.
    """
    if len(executions) < 2:
        return executions, "No compaction needed (less than 2 runs)."

    visited = set()
    compacted_list = []
    compacted_count = 0
    original_size = len(executions)
    log_messages = []

    for i, ex in enumerate(executions):
        if i in visited:
            continue
        
        # Start a new group
        group_indices = [i]
        visited.add(i)
        
        for j in range(i + 1, len(executions)):
            if j in visited:
                continue
            sim = compute_similarity(ex["instruction"], executions[j]["instruction"])
            if sim >= threshold:
                group_indices.append(j)
                visited.add(j)
        
        if len(group_indices) == 1:
            # Single execution, keep as is
            compacted_list.append(ex)
            continue
            
        # Merge group
        group = [executions[idx] for idx in group_indices]
        
        # Find best successful run
        success_runs = [g for g in group if g.get("success")]
        best_run = None
        if success_runs:
            best_run = min(success_runs, key=lambda x: x.get("total_api_calls", 999))
        else:
            # fallback to first run in group
            best_run = group[0]
            
        # Consolidate metadata
        all_lessons = set()
        all_constraints = set()
        api_call_history = []
        
        for g in group:
            all_lessons.update(g.get("lessons_learned", []))
            all_constraints.update(g.get("discovered_constraints", []))
            api_call_history.append(g.get("total_api_calls", 0))
            
        merged = dict(best_run) # copy fields from best run
        merged["lessons_learned"] = list(all_lessons)
        merged["discovered_constraints"] = list(all_constraints)
        merged["compaction_occurred"] = True
        
        # Build history metadata
        initial_calls = api_call_history[0]
        final_calls = best_run.get("total_api_calls", 0)
        reduction = initial_calls - final_calls
        
        summary = (
            f"Compacted {len(group)} runs for query target '{merged['instruction'][:40]}...'. "
            f"Consolidated API calls from chronological history {api_call_history} "
            f"to best efficiency of {final_calls} calls (saved {reduction} calls)."
        )
        merged["compaction_summary"] = summary
        merged["instruction"] = f"[Compacted] {merged['instruction']}"
        
        compacted_list.append(merged)
        compacted_count += len(group) - 1
        log_messages.append(summary)

    compaction_log = " | ".join(log_messages) if log_messages else "No groups met the similarity threshold."
    status_summary = f"Memory Compaction: Reduced runs from {original_size} to {len(compacted_list)}. {compaction_log}"
    
    return compacted_list, status_summary
