import app.keyboards as kb

user_menus = {}

# --- Словник меню ---
menus = {
    "book_list": kb.library,
    "add_book": kb.add_book,
    "in_process": kb.in_process,
    "favorite_books": kb.favorite_books,
    "read_books": kb.read_books,
    "help": kb.help_menu,
}

# --- Опис для кожного меню ---
menu_texts = {
    "book_list": ("Бібліотека"),
    "add_book": "➕ Додати книгу:\nНадішліть дані книги:\n📖 Назва\n👤 Автор\n🎭 Жанр\n🖼 Фото (опційно)",
    "in_process": "📕 Хочу прочитати",
    "favorite_books": "❤️ Улюблені книги",
    "read_books": "✅ Прочитані книги",
    "help": "https://t.me/larmet15",
}
