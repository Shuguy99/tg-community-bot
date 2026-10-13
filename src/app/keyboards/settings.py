from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def parse_callback(data: str) -> tuple[int, str, str]:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "set" or not parts[1].lstrip("-").isdigit():
        raise ValueError(data)
    return int(parts[1]), parts[2], parts[3]


def build_settings_keyboard(chat_id: int, settings) -> InlineKeyboardMarkup:
    def on(v):
        return "on" if v else "off"

    rows = [
        [InlineKeyboardButton(
            text=f"Анти-спам: {on(settings.antispam_enabled) if settings else 'on'}",
            callback_data=f"set:{chat_id}:antispam_enabled:{'off' if settings and settings.antispam_enabled else 'on'}",
        )],
        [InlineKeyboardButton(text="Ссылки", callback_data=f"set:{chat_id}:delete_links:off"),
         InlineKeyboardButton(text="Капс", callback_data=f"set:{chat_id}:delete_caps:off")],
        [InlineKeyboardButton(text="Дубли", callback_data=f"set:{chat_id}:delete_duplicates:off")],
        [InlineKeyboardButton(text="Ответы на предупреждения", callback_data=f"set:{chat_id}:action:next")],
        [InlineKeyboardButton(text="Стоп-слова", callback_data=f"sw:{chat_id}:add"),
         InlineKeyboardButton(text="Список", callback_data=f"sw:{chat_id}:list")],
        [InlineKeyboardButton(text="Апгрейд", callback_data=f"sub:{chat_id}:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
