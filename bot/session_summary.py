"""Conversation-level memory summarization for long sessions."""


def summarize_memory_entries(entries: list[tuple[float, str, str]], max_points: int = 4) -> str:
    """Build a concise summary from older conversation turns."""
    if not entries:
        return ""
    points: list[str] = []
    for _, role, text in entries:
        if role != "user":
            continue
        t = (text or "").strip()
        if not t:
            continue
        points.append(t[:80])
        if len(points) >= max_points:
            break
    if not points:
        points = [(entries[-1][2] or "")[:80]]
    joined = "；".join(p for p in points if p)
    return f"历史会话摘要：用户近期主要关注 {joined}"
