from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Кнопка "Назад у головне меню" ---
back_main_btn = InlineKeyboardButton(
    text="🔙 Назад у головне меню", callback_data="back_main"
)

# --- Стартове меню ---
first_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📚 Бібліотека", callback_data="book_list")],
        [InlineKeyboardButton(text="➕ Додати книгу", callback_data="add_book")],
        [
            InlineKeyboardButton(text="📕 Хочу прочитати", callback_data="in_process"),
            InlineKeyboardButton(
                text="❤️ Улюблені книги", callback_data="favorite_books"
            ),
            InlineKeyboardButton(text="✅ Прочитані книги", callback_data="read_books"),
        ],
        [InlineKeyboardButton(text="❓ Допомога", callback_data="help")],
    ]
)

# --- Бібліотека ---
library = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📜 Переглянути каталог", callback_data="library_open"
            )
        ],
        [back_main_btn],
    ]
)


# --- Універсальні меню з кнопкою "Назад" ---
def back_menu() -> InlineKeyboardMarkup:
    """Універсальне меню з однією кнопкою 'Назад у головне меню'"""
    return InlineKeyboardMarkup(inline_keyboard=[[back_main_btn]])


# Меню для конкретних розділів
add_book = back_menu()
in_process = back_menu()
favorite_books = back_menu()
read_books = back_menu()
help_menu = back_menu()


# --- Динамічна клавіатура для деталей книги ---
def book_details_kb(book_id: int, scope=None, index=None):
    """Кнопки для керування книгою (статуси, улюблене, видалення, повернення)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📕 Хочу прочитати ↔", callback_data=f"sttoggle:in:{book_id}")
    builder.button(text="❤️ Улюблена ↔", callback_data=f"favtoggle:{book_id}")
    builder.button(text="✅ Прочитано ↔", callback_data=f"sttoggle:read:{book_id}")

    # Кнопка для видалення книги
    if scope is not None and index is not None:
        builder.button(
            text="🗑 Видалити", callback_data=f"delete:{book_id}:{scope}:{index}"
        )
    else:
        builder.button(text="🗑 Видалити", callback_data=f"delete:{book_id}")

    # Кнопки повернення
    back_to_library_cb = (
        f"lib:{index}" if scope == "lib" and isinstance(index, int) else "book_list"
    )
    builder.row(
        InlineKeyboardButton(text="📚 До бібліотеки", callback_data=back_to_library_cb),
        InlineKeyboardButton(text="🔙 Головне меню", callback_data="back_main"),
    )
    return builder.as_markup()


# --- Динамічна клавіатура для каруселі книг ---
def book_carousel_kb(book_id: int, index: int, total: int, scope="lib"):
    """Кнопки для каруселі книг."""
    builder = InlineKeyboardBuilder()
    left_cb = f"{scope}:{index-1}" if index > 0 else "noop"
    right_cb = f"{scope}:{index+1}" if index < total - 1 else "noop"

    builder.button(text="⬅️", callback_data=left_cb)
    builder.button(text="🔎 Деталі", callback_data=f"book:{book_id}:{scope}:{index}")
    builder.button(text="➡️", callback_data=right_cb)
    builder.row(InlineKeyboardButton(text="🔙 Головне меню", callback_data="back_main"))
    return builder.as_markup()
