from typing import List, Tuple

def make_ranges(start: int, end: int, size: int) -> List[Tuple[int, int]]:
    ranges = []
    p = start
    while p <= end:
        q = min(p + size - 1, end)
        ranges.append((p, q))
        p = q + 1
    return ranges
