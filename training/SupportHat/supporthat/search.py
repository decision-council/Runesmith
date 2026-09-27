"""Grounded search over indexed documents for SupportHat.

Returns passages with exact source citations. Never synthesizes facts.
"""

import re
from pathlib import Path

from . import documents


def _tokenize_query(query):
    """Tokenize query into lowercase keywords."""
    words = re.findall(r'[a-zA-Z0-9]+', query.lower())
    # Filter short words
    return [w for w in words if len(w) >= 3]


def _find_matching_lines(content, keywords):
    """Find line ranges containing any keyword.
    
    Returns list of (line_start, line_end, passage) tuples.
    Line numbers are 1-based inclusive.
    """
    lines = content.split('\n')
    matches = []
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        for kw in keywords:
            if kw in line_lower:
                # Found a match - include context (1 line before, 1 line after)
                start = max(0, i - 1)
                end = min(len(lines) - 1, i + 1)
                passage_lines = lines[start:end + 1]
                passage = '\n'.join(passage_lines)
                # Convert to 1-based
                matches.append((start + 1, end + 1, passage))
                break  # Only one match per line
    
    return matches


def _merge_overlapping_passages(passages):
    """Merge overlapping or adjacent passage ranges.
    
    Input: list of (line_start, line_end, passage) tuples (1-based)
    Output: merged list with no overlaps
    """
    if not passages:
        return []
    
    # Sort by start line
    sorted_passages = sorted(passages, key=lambda x: (x[0], x[1]))
    merged = []
    
    current_start, current_end, current_passage = sorted_passages[0]
    
    for start, end, passage in sorted_passages[1:]:
        if start <= current_end + 1:  # Overlapping or adjacent
            if end > current_end:
                current_end = end
                # Recombine passages - will rebuild from source later
        else:
            merged.append((current_start, current_end, current_passage))
            current_start, current_end, current_passage = start, end, passage
    
    merged.append((current_start, current_end, current_passage))
    return merged


def _rebuild_passage(content, line_start, line_end):
    """Rebuild exact passage from content given line range (1-based inclusive)."""
    lines = content.split('\n')
    # Convert to 0-based
    start_idx = line_start - 1
    end_idx = line_end  # exclusive for slice, so line_end (1-based) maps to end_idx
    passage_lines = lines[start_idx:end_idx]
    return '\n'.join(passage_lines)


def _score_passage(passage, keywords):
    """Score a passage by keyword frequency."""
    passage_lower = passage.lower()
    score = 0
    for kw in keywords:
        score += passage_lower.count(kw)
    return score


def search_documents(conn, query):
    """Search indexed documents for passages matching query.
    
    Returns list of dicts with:
        - path: source file path
        - passage: exact source lines (not synthesized)
        - line_start: 1-based inclusive start line
        - line_end: 1-based inclusive end line
    
    Results are ordered by relevance (keyword frequency) then by path and line.
    Identical query + unchanged sources yields identical ordered results.
    Returns empty list if no matches found.
    """
    documents.init_document_schema(conn)
    
    keywords = _tokenize_query(query)
    if not keywords:
        return []
    
    # Get documents that have at least one matching keyword
    placeholders = ','.join('?' * len(keywords))
    cursor = conn.execute(
        f"""SELECT DISTINCT d.id, d.path 
            FROM documents d
            JOIN keywords k ON k.document_id = d.id
            WHERE k.keyword IN ({placeholders})
            ORDER BY d.path""",
        keywords
    )
    matching_docs = cursor.fetchall()
    
    if not matching_docs:
        return []
    
    results = []
    
    for doc_row in matching_docs:
        doc_id = doc_row['id']
        doc_path = doc_row['path']
        
        # Read actual file content to get exact passages
        try:
            content = Path(doc_path).read_text(encoding='utf-8')
        except (IOError, OSError):
            # File no longer accessible - skip
            continue
        
        # Find lines matching keywords
        passages = _find_matching_lines(content, keywords)
        if not passages:
            continue
        
        # Merge overlapping passages
        merged = _merge_overlapping_passages(passages)
        
        # Rebuild exact passages from source
        for line_start, line_end, _ in merged:
            exact_passage = _rebuild_passage(content, line_start, line_end)
            score = _score_passage(exact_passage, keywords)
            results.append({
                'path': doc_path,
                'passage': exact_passage,
                'line_start': line_start,
                'line_end': line_end,
                '_score': score
            })
    
    # Sort by score descending, then path, then line_start for determinism
    results.sort(key=lambda r: (-r['_score'], r['path'], r['line_start']))
    
    # Remove internal score field
    for r in results:
        del r['_score']
    
    return results
