from __future__ import annotations

import html
from collections import defaultdict
from datetime import date

from bot.sources.registry import SOURCE_DISPLAY_NAMES, SOURCE_IDS_ORDER
from bot.sources.types import ExclusiveItem

MAX_MESSAGE_LEN = 4096


def _link_line(it: ExclusiveItem) -> str:
    u = html.escape(it.url, quote=True)
    t = html.escape(it.title)
    return f'<a href="{u}">{t}</a>'


def _grouped_report_lines(items: list[ExclusiveItem]) -> list[str]:
    """Секции по изданиям: «1. Название:», затем ссылки; порядок как в реестре."""
    if not items:
        return ["За эту дату эксклюзивов не найдено."]

    by_source: dict[str, list[ExclusiveItem]] = defaultdict(list)
    for it in items:
        by_source[it.source_id or "_unknown"].append(it)

    for sid in by_source:
        by_source[sid].sort(key=lambda x: x.published_at, reverse=True)

    lines: list[str] = []
    section_no = 0
    known = set(SOURCE_IDS_ORDER)
    order = list(SOURCE_IDS_ORDER)
    order.extend(s for s in sorted(by_source.keys()) if s not in known and s != "_unknown")
    if "_unknown" in by_source:
        order.append("_unknown")

    for sid in order:
        bucket = by_source.get(sid)
        if not bucket:
            continue
        section_no += 1
        label = SOURCE_DISPLAY_NAMES.get(sid, sid if sid != "_unknown" else "Другое")
        lines.append(f"{section_no}. {html.escape(label)}:")
        lines.append("")
        for j, it in enumerate(bucket):
            lines.append(_link_line(it))
            if j < len(bucket) - 1:
                lines.append("")
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()
    return lines


def build_telegram_chunks(
    day: date,
    tz_name: str,
    items: list[ExclusiveItem],
    failed_source_ids: list[str],
) -> list[str]:
    """HTML parse_mode chunks, each ≤ MAX_MESSAGE_LEN."""
    h0 = html.escape(f"Эксклюзивы за {day.isoformat()} ({tz_name})")
    h1 = html.escape(f"Эксклюзивы за {day.isoformat()} ({tz_name}), продолжение")
    lines = _grouped_report_lines(items)
    if failed_source_ids:
        failed_labels = [
            SOURCE_DISPLAY_NAMES.get(sid, sid) for sid in sorted(failed_source_ids)
        ]
        lines.append("")
        lines.append(
            "Нет ответа от: " + html.escape(", ".join(failed_labels))
        )

    chunks: list[str] = []
    header = h0
    buf: list[str] = []

    def emit() -> None:
        nonlocal header, buf
        if not buf:
            return
        text = header + "\n\n" + "\n".join(buf)
        chunks.append(text)
        buf = []
        header = h1

    for line in lines:
        trial = header + "\n\n" + "\n".join(buf + [line])
        if len(trial) <= MAX_MESSAGE_LEN:
            buf.append(line)
            continue
        if buf:
            emit()
        trial2 = header + "\n\n" + line
        if len(trial2) <= MAX_MESSAGE_LEN:
            buf = [line]
            continue
        # Line alone exceeds limit — split as plain text slices under header
        rest = line
        while rest:
            overhead = len(header) + 2
            room = max(1, MAX_MESSAGE_LEN - overhead)
            chunks.append(header + "\n\n" + rest[:room])
            rest = rest[room:]
            header = h1
        buf = []

    emit()
    if not chunks:
        chunks.append(h0 + "\n\n" + "\n".join(lines) if lines else h0 + "\n\n")
    return chunks
