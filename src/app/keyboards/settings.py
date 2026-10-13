from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import ViolationAction

ACTION_ORDER = [ViolationAction.DELETE, ViolationAction.WARN, ViolationAction.MUTE]
ACTION_LABELS = {
    ViolationAction.DELETE: "Удалять",
    ViolationAction.WARN: "Предупреждать",
    ViolationAction.MUTE: "Мьютить",
}


def parse_callback(data: str) -> tuple[int, str, str]:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "set" or not parts[1].lstrip("-").isdigit():
        raise ValueError(data)
    return int(parts[1]), parts[2], parts[3]


def _toggle(chat_id: int, field: str, enabled: bool, label: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=f"{label}: {'вкл' if enabled else 'выкл'}",
        callback_data=f"set:{chat_id}:{field}:{'off' if enabled else 'on'}",
    )


def _action_button(chat_id: int, action: ViolationAction) -> InlineKeyboardButton:
    idx = ACTION_ORDER.index(action) if action in ACTION_ORDER else 0
    nxt = ACTION_ORDER[(idx + 1) % len(ACTION_ORDER)]
    return InlineKeyboardButton(
        text=f"Нарушение: {ACTION_LABELS[action]}",
        callback_data=f"set:{chat_id}:action:{nxt.value}",
    )


def build_settings_keyboard(chat_id: int, settings) -> InlineKeyboardMarkup:
    enabled = settings.antispam_enabled if settings else True
    links = settings.delete_links if settings else True
    caps = settings.delete_caps if settings else True
    dups = settings.delete_duplicates if settings else True
    action = settings.action if settings else ViolationAction.DELETE

    rows = [
        [_toggle(chat_id, "antispam_enabled", enabled, "Анти-спам")],
        [
            _toggle(chat_id, "delete_links", links, "Ссылки"),
            _toggle(chat_id, "delete_caps", caps, "Капс"),
        ],
        [_toggle(chat_id, "delete_duplicates", dups, "Дубли")],
        [_action_button(chat_id, action)],
        [
            InlineKeyboardButton(text="Стоп-слова", callback_data=f"sw:{chat_id}:add"),
            InlineKeyboardButton(text="Список", callback_data=f"sw:{chat_id}:list"),
        ],
        [InlineKeyboardButton(text="Апгрейд", callback_data=f"sub:{chat_id}:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_chat_picker(chat_ids: list[tuple[int, str]], prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=title, callback_data=f"{prefix}:{chat_id}:menu")]
        for chat_id, title in chat_ids
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
