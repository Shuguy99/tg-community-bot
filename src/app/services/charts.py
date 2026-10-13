import io


def format_chat_summary(rows) -> str:
    if not rows:
        return "Нет данных за выбранный период."
    total = sum(r.messages for r in rows)
    joins = sum(r.joins for r in rows)
    leaves = sum(r.leaves for r in rows)
    peak = max(r.active_users for r in rows)
    return (
        f"Сообщений: {total}\n"
        f"Входы: +{joins} · Выходы: -{leaves}\n"
        f"Пик активных за день: {peak}\n"
        f"Дней в выборке: {len(rows)}"
    )


def format_top(rows) -> str:
    if not rows:
        return "Нет данных."
    lines = ["Топ участников:"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. id{r.user_id} — {r.messages} сообщ. ({r.deleted} удалено)")
    return "\n".join(lines)


def render_growth_chart(rows) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 3))
    dates = [r.date for r in rows]
    ax.plot(dates, [r.messages for r in rows], marker="o", label="messages")
    ax.plot(dates, [r.joins - r.leaves for r in rows], marker="s", label="net joins")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
