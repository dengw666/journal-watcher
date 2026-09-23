import json
from datetime import datetime, timezone, timedelta
from src.db import get_connection, init_db, mark_notified

BJT = timezone(timedelta(hours=8))


def _is_real_abstract(ab: str | None) -> bool:
    """Filter out placeholder abstracts like 'Journal of ... DOI: ...'"""
    if not ab: return False
    ab = ab.strip()
    if len(ab) < 80: return False
    lower = ab.lower()
    if 'published online:' in lower and 'doi:' in lower: return False
    if lower.startswith('journal of') and 'doi:' in lower: return False
    return True


def _today_bj() -> str:
    """Today's date string in Beijing time."""
    return datetime.now(BJT).strftime('%Y-%m-%d')


def _fmt_bj(ts: str | None) -> str | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BJT).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return ts


def generate_digest(date_str: str | None = None) -> str:
    """指定日期的论文列表，按 published_online 匹配。默认今天（北京时间）。"""
    init_db()
    target = date_str or _today_bj()
    conn = get_connection()
    rows = conn.execute("""
        SELECT id,title,journal,doi,url,authors,abstract,keywords_matched,discovered_at,published_online
        FROM papers
        WHERE published_online IS NOT NULL AND substr(published_online, 1, 10) = ?
        ORDER BY journal, title
    """, (target,)).fetchall()
    conn.close()

    if not rows:
        return f"# Journal Watch — {target}\n\n今天暂无新论文。\n"

    lines = [f"# Journal Watch — {target}", f"共 {len(rows)} 篇\n"]

    for idx, (_,title,journal,_,_,_,_,_,_,_) in enumerate(rows, 1):
        lines.append(f"{idx}. 【{journal}】{title}")

    lines.append(f"\n> 对哪几篇感兴趣？告诉我编号。")
    return '\n'.join(lines)


def generate_recent_digest(hours: int = 24, only_unnotified: bool = True, mark_sent: bool = False) -> str:
    """按最近 N 小时新入库 / 尚未推送的论文生成 digest。默认只看未推送论文。"""
    init_db()
    conn = get_connection()
    status_clause = "AND status != 'notified'" if only_unnotified else ""
    rows = conn.execute(f"""
        SELECT id,title,journal,doi,url,authors,abstract,keywords_matched,discovered_at,published_online,status
        FROM papers
        WHERE discovered_at IS NOT NULL
          AND datetime(discovered_at) >= datetime('now', ?)
          {status_clause}
        ORDER BY datetime(discovered_at) DESC, journal, title
    """, (f'-{hours} hours',)).fetchall()
    conn.close()

    if not rows:
        return f"# Journal Watch — 最近 {hours} 小时\n\n最近 {hours} 小时暂无新入库论文。\n"

    lines = [f"# Journal Watch — 最近 {hours} 小时", f"共 {len(rows)} 篇\n"]
    ids = []
    for idx, (pid, title, journal, _, _, _, _, _, discovered_at, published_online, _) in enumerate(rows, 1):
        ids.append(pid)
        extra = []
        if published_online:
            extra.append(f"online {published_online[:10]}")
        if discovered_at:
            extra.append(f"入库 {_fmt_bj(discovered_at)}")
        suffix = f"（{'，'.join(extra)}）" if extra else ""
        lines.append(f"{idx}. 【{journal}】{title}{suffix}")

    lines.append("\n> 对哪几篇感兴趣？告诉我编号。")
    if mark_sent:
        mark_notified(ids)
    return '\n'.join(lines)


def show_papers(paper_nums: list[int], date_str: str | None = None) -> str:
    """按编号返回指定日期论文的详细信息。"""
    init_db()
    target = date_str or _today_bj()
    conn = get_connection()
    rows = conn.execute("""
        SELECT id,title,journal,doi,url,authors,abstract,keywords_matched,discovered_at,published_online
        FROM papers
        WHERE published_online IS NOT NULL AND substr(published_online, 1, 10) = ?
        ORDER BY journal, title
    """, (target,)).fetchall()
    conn.close()

    if not rows:
        return f"{target} 无论文数据。"

    lines = []
    for num in paper_nums:
        if num < 1 or num > len(rows):
            lines.append(f"#{num}: 编号超出范围（{target} 共 {len(rows)} 篇）\n")
            continue
        _,title,journal,doi,url,auth_j,abstract,kw_j,_,pub_online = rows[num - 1]
        lines.append(f"### #{num}. {title}\n")
        lines.append(f"- 期刊: {journal}")
        if pub_online:
            lines.append(f"- 发表日期: {pub_online[:10]}")
        if doi:
            lines.append(f"- DOI: https://doi.org/{doi}")
        elif url:
            lines.append(f"- URL: {url}")
        if auth_j:
            a = json.loads(auth_j)
            lines.append(f"- 作者: {', '.join(a)}")
        if abstract and _is_real_abstract(abstract):
            lines.append(f"- 摘要: {abstract}")
        if kw_j:
            kws = json.loads(kw_j)
            lines.append(f"- 匹配关键词: {', '.join(kws)}")
        lines.append("")
    return '\n'.join(lines)
