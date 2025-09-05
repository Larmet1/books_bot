import asyncio
from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
import app.keyboards as kb
from app.settings import menus, menu_texts, user_menus
from app.db import (
    add_book_for_user,
    list_all_books,
    get_book,
    count_all_books,
    get_all_book_by_index,
    count_user_books_by_status_m2m,
    get_user_book_by_status_and_index_m2m,
    toggle_favorite,
    count_user_favorites,
    get_user_favorite_by_index,
    toggle_status,
    list_book_statuses,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


router = Router()


# --- FSM для додавання книги ---
class Reg(StatesGroup):
    name = State()
    author = State()
    genre = State()
    photo = State()


# --- Helpers ---
def _map_statuses_ua(statuses: list[str]) -> str:
    """Перекладає технічні статуси в українські підписи для відображення."""
    mapping = {"in": "Хочу прочитати", "read": "Прочитано"}
    return ", ".join(mapping.get(s, s) for s in statuses) if statuses else "-"


def _build_book_details_text(
    header: str | None,
    page: int | None,
    total: int | None,
    book: dict,
    include_statuses: bool = True,
) -> str:
    """Створює текст з докладними даними про книгу (назва, автор, жанр, id, статус, улюблене)."""
    parts: list[str] = []
    if header is not None:
        parts.append(header)
        parts.append("")
    if page is not None and total is not None:
        parts.append(f"{page}/{total}")
        parts.append("")
    parts.append(f"📖 Назва: {book['name']}")
    parts.append(f"👤 Автор: {book['author']}")
    parts.append(f"🎭 Жанр: {book['genre']}")
    parts.append(f"🆔 ID: {book['id']}")
    if "is_favorite" in book:
        parts.append(f"⭐ Улюблена: {'Так' if book.get('is_favorite') else 'ні'}")
    if include_statuses:
        # list_book_statuses повертає список технічних кодів статусів
        statuses = _map_statuses_ua(list_book_statuses(book["id"]))
        parts.append(f"📌 Статус: {statuses}")
    return "\n".join(parts)


# --- Показ головного меню ---
async def show_main_menu(callback: CallbackQuery):
    """Редагує поточне меню в головне меню (текст + клавіатура)."""
    text = "📚 Головне меню"
    await edit_menu_message(callback, text=text, reply_markup=kb.first_menu)
    await callback.answer()


# --- Старт ---
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обробляє /start: видаляє старе меню, відправляє нове."""
    if message.from_user.id in user_menus:
        try:
            await message.bot.delete_message(
                message.chat.id, user_menus[message.from_user.id]
            )
        except TelegramBadRequest:
            pass
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    msg = await message.answer(
        text=(
            "👋 Привіт! Я *Book_bot* 📚\n\n"
            "Оберіть пункт меню"
        ),
        reply_markup=kb.first_menu,
    )
    user_menus[message.from_user.id] = msg.message_id


# --- Хендлери для кожного меню ---
@router.callback_query(F.data == "book_list")
async def open_book_list(callback: CallbackQuery):
    """Відкриває карусель книг (з бібліотеки) з нульового індексу."""
    await render_book_carousel(callback, scope="lib", index=0)
    await callback.answer()


@router.callback_query(F.data == "library_open")
async def library_open(callback: CallbackQuery):
    """Альтернативний тригер відкрити бібліотеку."""
    await render_book_carousel(callback, scope="lib", index=0)
    await callback.answer()


@router.callback_query(F.data == "add_book")
async def open_add_book(callback: CallbackQuery, state: FSMContext):
    """Початок FSM додавання книги — просимо назву."""
    await callback.message.edit_text(
        menu_texts["add_book"] + "\n\nВведіть назву книги:",
        reply_markup=menus["add_book"],
    )
    await state.set_state(Reg.name)
    await callback.answer()


@router.callback_query(F.data == "in_process")
async def open_in_process(callback: CallbackQuery):
    """Відкриває карусель книг зі статусом 'Хочу прочитати'."""
    await render_status_carousel(callback, status="in", index=0)
    await callback.answer()


@router.callback_query(F.data == "favorite_books")
async def open_favorite_books(callback: CallbackQuery):
    """Відкриває карусель улюблених книг."""
    await render_favorites_carousel(callback, index=0)
    await callback.answer()


@router.callback_query(F.data == "read_books")
async def open_read_books(callback: CallbackQuery):
    """Відкриває карусель прочитаних книг."""
    await render_status_carousel(callback, status="read", index=0)
    await callback.answer()


@router.callback_query(F.data == "help")
async def open_help(callback: CallbackQuery):
    """Показує меню допомоги."""
    await callback.message.edit_text(menu_texts["help"], reply_markup=menus["help"])
    await callback.answer()


# --- Деталі книги ---
@router.callback_query(F.data.startswith("book:"))
async def open_book_details(callback: CallbackQuery):
    """
    Показує деталі конкретної книги.
    Підтримуються формати callback.data:
      - book:<book_id>
      - book:<book_id>:<scope>:<index>
    scope/index використовуються для коректного повернення у карусель.
    """
    parts = callback.data.split(":")
    book_id = None
    scope = None
    index = None
    try:
        if len(parts) >= 2:
            book_id = int(parts[1])
        if len(parts) >= 4:
            scope = parts[2]
            index = int(parts[3])
    except Exception:
        book_id = None
    if book_id is None:
        await callback.answer()
        return
    book = get_book(book_id)
    if not book:
        await callback.answer("Книгу не знайдено", show_alert=True)
        return

    text = _build_book_details_text(None, None, None, book, include_statuses=True)
    builder = InlineKeyboardBuilder()
    # Дії зі статусом (перемикання)
    builder.button(
        text="📕 Хочу прочитати ↔", callback_data=f"sttoggle:in:{book['id']}"
    )
    builder.button(text="❤️ Улюблена ↔", callback_data=f"favtoggle:{book['id']}")
    builder.button(text="✅ Прочитано ↔", callback_data=f"sttoggle:read:{book['id']}")
    # Кнопка для видалення книги — додаємо scope/index, якщо є
    if scope is not None and index is not None:
        builder.button(
            text="🗑 Видалити", callback_data=f"delete:{book['id']}:{scope}:{index}"
        )
    else:
        builder.button(text="🗑 Видалити", callback_data=f"delete:{book['id']}")
    # Повернення: або в бібліотеку на ту ж сторінку, або в головне меню
    back_to_library_cb = (
        f"lib:{index}" if scope == "lib" and isinstance(index, int) else "book_list"
    )
    builder.row(
        InlineKeyboardButton(text="📚 До бібліотеки", callback_data=back_to_library_cb),
        InlineKeyboardButton(text="🔙 Головне меню", callback_data="back_main"),
    )
    await edit_menu_message(
        callback=callback,
        text=text,
        reply_markup=builder.as_markup(),
        photo_id=book.get("photo_id"),
    )
    await callback.answer()


# --- Карусель книг ---
async def render_book_carousel(callback: CallbackQuery, scope: str, index: int):
    """Рендерить карусель всієї бібліотеки (по індексу)."""
    if scope == "lib":
        total = count_all_books()
        book = get_all_book_by_index(index)
        header = menu_texts["book_list"]
        left_cb = f"lib:{index-1}"
        right_cb = f"lib:{index+1}"
    else:
        # Fallback: показуємо бібліотеку
        total = count_all_books()
        book = get_all_book_by_index(index)
        header = menu_texts["book_list"]
        left_cb = f"lib:{index-1}"
        right_cb = f"lib:{index+1}"

    builder = InlineKeyboardBuilder()

    if total == 0 or not book:
        text = header + (
            "\n\nНічого не знайдено." if scope == "lib" else "\n\nУ вас ще немає книг."
        )
        builder.button(text="🔙 Назад у головне меню", callback_data="back_main")
        builder.adjust(1)
        await edit_menu_message(callback, text=text, reply_markup=builder.as_markup())
        return

    page = index + 1
    text = _build_book_details_text(header, page, total, book, include_statuses=True)

    # Навігація: вліво, деталі, вправо, назад
    builder.button(text="⬅️", callback_data=left_cb if index > 0 else "noop")
    builder.button(text="🔎 Деталі", callback_data=f"book:{book['id']}:lib:{index}")
    builder.button(text="➡️", callback_data=right_cb if index < total - 1 else "noop")
    builder.row(InlineKeyboardButton(text="🔙 Головне меню", callback_data="back_main"))
    await edit_menu_message(
        callback=callback,
        text=text,
        reply_markup=builder.as_markup(),
        photo_id=book.get("photo_id"),
    )


# --- Карусель за статусом користувача ---
async def render_status_carousel(callback: CallbackQuery, status: str, index: int):
    """Рендер каруселі для статусів 'in' та 'read'."""
    user_id = callback.from_user.id
    if status == "in":
        header = menu_texts["in_process"]
        total = count_user_books_by_status_m2m(user_id, "in")
        book = get_user_book_by_status_and_index_m2m(user_id, "in", index)
        left_cb = f"in:{index-1}"
        right_cb = f"in:{index+1}"
    elif status == "fav":
        # За сумісництвом; фактично використовується окрема карусель
        header = menu_texts["favorite_books"]
        total = count_user_favorites(user_id)
        book = get_user_favorite_by_index(user_id, index)
        left_cb = f"fav:{index-1}"
        right_cb = f"fav:{index+1}"
    elif status == "read":
        header = menu_texts["read_books"]
        total = count_user_books_by_status_m2m(user_id, "read")
        book = get_user_book_by_status_and_index_m2m(user_id, "read", index)
        left_cb = f"read:{index-1}"
        right_cb = f"read:{index+1}"
    else:
        # некоректний статус -> показуємо бібліотеку
        await render_book_carousel(callback, scope="lib", index=0)
        return

    builder = InlineKeyboardBuilder()

    if total == 0 or not book:
        text = header + "\n\nУ вас ще немає книг."
        builder.button(text="🔙 Назад у головне меню", callback_data="back_main")
        builder.adjust(1)
        await edit_menu_message(callback, text=text, reply_markup=builder.as_markup())
        return

    page = index + 1
    text = _build_book_details_text(header, page, total, book, include_statuses=False)

    builder.button(text="⬅️", callback_data=left_cb if index > 0 else "noop")
    builder.button(text="🔎 Деталі", callback_data=f"book:{book['id']}:in:{index}")
    builder.button(text="➡️", callback_data=right_cb if index < total - 1 else "noop")
    builder.row(InlineKeyboardButton(text="🔙 Головне меню", callback_data="back_main"))
    await edit_menu_message(
        callback=callback,
        text=text,
        reply_markup=builder.as_markup(),
        photo_id=book.get("photo_id"),
    )


# --- Карусель улюблених ---
async def render_favorites_carousel(callback: CallbackQuery, index: int):
    """Рендерує карусель улюблених книг користувача."""
    user_id = callback.from_user.id
    header = menu_texts["favorite_books"]
    total = count_user_favorites(user_id)
    book = get_user_favorite_by_index(user_id, index)

    builder = InlineKeyboardBuilder()

    if total == 0 or not book:
        text = header + "\n\nУ вас ще немає улюблених книг."
        builder.button(text="🔙 Назад у головне меню", callback_data="back_main")
        builder.adjust(1)
        await edit_menu_message(callback, text=text, reply_markup=builder.as_markup())
        return

    page = index + 1
    text = _build_book_details_text(header, page, total, book, include_statuses=False)

    builder.button(text="⬅️", callback_data=(f"fav:{index-1}" if index > 0 else "noop"))
    builder.button(text="🔎 Деталі", callback_data=f"book:{book['id']}:fav:{index}")
    builder.button(
        text="➡️", callback_data=(f"fav:{index+1}" if index < total - 1 else "noop")
    )
    builder.row(InlineKeyboardButton(text="🔙 Головне меню", callback_data="back_main"))
    await edit_menu_message(
        callback=callback,
        text=text,
        reply_markup=builder.as_markup(),
        photo_id=book.get("photo_id"),
    )


@router.callback_query(F.data.startswith("lib:"))
async def carousel_lib_nav(callback: CallbackQuery):
    try:
        index = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    if index < 0:
        index = 0
    await render_book_carousel(callback, scope="lib", index=index)
    await callback.answer()


@router.callback_query(F.data.startswith("my:"))
async def carousel_my_nav(callback: CallbackQuery):
    # Маршрут застарів після видалення "Мої книги". Відправляємо у бібліотеку.
    await render_book_carousel(callback, scope="lib", index=0)
    await callback.answer()


@router.callback_query(F.data.startswith("in:"))
async def carousel_in_nav(callback: CallbackQuery):
    try:
        index = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    if index < 0:
        index = 0
    await render_status_carousel(callback, status="in", index=index)
    await callback.answer()


@router.callback_query(F.data.startswith("fav:"))
async def carousel_fav_nav(callback: CallbackQuery):
    try:
        index = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    if index < 0:
        index = 0
    await render_favorites_carousel(callback, index=index)
    await callback.answer()


@router.callback_query(F.data.startswith("read:"))
async def carousel_read_nav(callback: CallbackQuery):
    try:
        index = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    if index < 0:
        index = 0
    await render_status_carousel(callback, status="read", index=index)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_btn(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("sttoggle:"))
async def toggle_status_handler(callback: CallbackQuery):
    try:
        _, status, book_id_str = callback.data.split(":", 2)
        book_id = int(book_id_str)
        if status not in {"in", "read"}:
            await callback.answer()
            return
    except Exception:
        await callback.answer()
        return

    try:
        new_val = toggle_status(book_id, status)
        # взаємовиключність забезпечена у БД: якщо вмикаємо один — вимикається інший
        ua = "Хочу прочитати" if status == "in" else "Прочитана"
        await callback.answer(
            ("Додано статус " + ua) if new_val else ("Знято статус " + ua)
        )
    except Exception:
        await callback.answer("Помилка оновлення статусу", show_alert=True)
        return

    try:
        await open_book_details(callback)
    except Exception:
        await callback.answer()


@router.callback_query(F.data.startswith("favtoggle:"))
async def toggle_fav(callback: CallbackQuery):
    try:
        book_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    try:
        new_val = toggle_favorite(book_id)
        await callback.answer(
            "Додано до улюблених" if new_val else "Прибрано з улюблених"
        )
    except Exception:
        await callback.answer("Помилка оновлення улюбленого", show_alert=True)
        return
    try:
        await open_book_details(callback)
    except Exception:
        await callback.answer()


# --- Допоміжне: показ у одному повідомленні (фото+підпис або текст) ---
async def edit_menu_message(
    callback: CallbackQuery, text: str, reply_markup, photo_id: str | None = None
):
    msg = callback.message
    chat_id = msg.chat.id
    user_id = callback.from_user.id
    # Ефективна стратегія: якщо є photo_id — віддаємо перевагу фото
    # 1) якщо повідомлення вже фото — редагуємо медіа
    # 2) якщо повідомлення текст — замінюємо на фото
    # 3) якщо фото немає — редагуємо текст
    if photo_id and msg.photo:
        try:
            await msg.edit_media(
                media=InputMediaPhoto(media=photo_id, caption=text),
                reply_markup=reply_markup,
            )
            return
        except Exception:
            pass
    if photo_id and not msg.photo:
        try:
            await msg.delete()
        except Exception:
            pass
        sent = await callback.bot.send_photo(
            chat_id=chat_id, photo=photo_id, caption=text, reply_markup=reply_markup
        )
        user_menus[user_id] = sent.message_id
        return
    # Якщо потрібно показати текст, а поточне повідомлення з фото — замінюємо коректно
    if not photo_id and msg.photo:
        try:
            await msg.delete()
        except Exception:
            pass
        sent = await callback.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=reply_markup
        )
        user_menus[user_id] = sent.message_id
        return
    try:
        await msg.edit_text(text=text, reply_markup=reply_markup)
        return
    except Exception:
        pass
    # Fallback: відправляємо нове повідомлення того ж типу, без зайвих delete
    if photo_id:
        sent = await callback.bot.send_photo(
            chat_id=chat_id, photo=photo_id, caption=text, reply_markup=reply_markup
        )
    else:
        sent = await callback.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=reply_markup
        )
    user_menus[user_id] = sent.message_id


# --- Повернення у головне меню ---
@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    await show_main_menu(callback)


# --- КРОК 1: Назва книги ---
@router.message(Reg.name)
async def add_book_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)

    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    menu_id = user_menus.get(message.from_user.id)
    if menu_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=menu_id,
                text="✍️ Введіть автора книги:",
                reply_markup=kb.add_book,
            )
        except TelegramBadRequest:
            pass

    await state.set_state(Reg.author)


# --- КРОК 2: Автор книги ---
@router.message(Reg.author)
async def add_book_author(message: types.Message, state: FSMContext):
    await state.update_data(author=message.text)

    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    menu_id = user_menus.get(message.from_user.id)
    if menu_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=menu_id,
                text="📚 Введіть жанр книги:",
                reply_markup=kb.add_book,
            )
        except TelegramBadRequest:
            pass

    await state.set_state(Reg.genre)


# --- КРОК 3: Жанр книги ---
@router.message(Reg.genre)
async def add_book_genre(message: types.Message, state: FSMContext):
    await state.update_data(genre=message.text)

    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    menu_id = user_menus.get(message.from_user.id)
    if menu_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=menu_id,
                text="📷 Надішліть фото книги (або напишіть 'пропустити'):",
                reply_markup=kb.add_book,
            )
        except TelegramBadRequest:
            pass

    await state.set_state(Reg.photo)


# --- КРОК 4: Фото книги ---
@router.message(Reg.photo, F.content_type.in_({"photo", "text"}))
async def add_book_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()

    # Якщо користувач надіслав фото
    if message.photo:
        await state.update_data(photo=message.photo[-1].file_id)
    else:
        await state.update_data(photo=None)

    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    # Отримуємо фінальні дані
    data = await state.get_data()

    # Зберігаємо книгу в базу
    try:
        book_id = add_book_for_user(
            tg_user_id=message.from_user.id,
            name=data["name"],
            author=data["author"],
            genre=data["genre"],
            photo_id=data.get("photo"),
            status="my",
        )
    except Exception:
        book_id = None

    # Формуємо підтвердження
    confirm_text = (
        "✅ Книга успішно додана!\n\n"
        f"📖 Назва: {data['name']}\n"
        f"👤 Автор: {data['author']}\n"
        f"🎭 Жанр: {data['genre']}" + (f"\n🆔 ID: {book_id}" if book_id else "")
    )

    # Повертаємо користувача в головне меню
    menu_id = user_menus.get(message.from_user.id)
    if menu_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=menu_id,
                text=confirm_text,
                reply_markup=kb.first_menu,
            )
        except TelegramBadRequest:
            pass

    # Завершуємо FSM
    await state.clear()


# --- Easter egg ---
@router.message(F.text == "drivin in my car")
async def asgore(message: types.Message):
    # Видаляємо повідомлення користувача
    await message.delete()

    # Відправляємо гіфку
    gif_message = await message.answer_animation(
        "https://i.redd.it/vpu9786tw89f1.gif"
    )

    # Чекаємо 3 секунди
    await asyncio.sleep(3)

    # Видаляємо гіфку
    await gif_message.delete()


@router.callback_query(F.data.startswith("delete:"))
async def delete_book_handler(callback: CallbackQuery):
    try:
        parts = callback.data.split(":")
        book_id = int(parts[1])
        scope = parts[2] if len(parts) >= 3 else None
        index = int(parts[3]) if len(parts) >= 4 else 0
    except Exception:
        await callback.answer("Невірні дані", show_alert=True)
        return

    from app.db import (
        delete_book,
        count_all_books,
        count_user_books_by_status_m2m,
        count_user_favorites,
    )

    # Спроба видалити книгу
    if delete_book(book_id):
        await callback.answer("Книгу видалено")
    else:
        await callback.answer("Не вдалося видалити книгу", show_alert=True)
        return

    # Оновлюємо перегляд залежно від scope
    user_id = callback.from_user.id
    if scope == "lib":
        total = count_all_books()
        new_index = index if index < total else max(total - 1, 0)
        await render_book_carousel(callback, scope="lib", index=new_index)
    elif scope == "in":
        from app.db import get_user_book_by_status_and_index_m2m

        total = count_user_books_by_status_m2m(user_id, "in")
        new_index = index if index < total else max(total - 1, 0)
        await render_status_carousel(callback, status="in", index=new_index)
    elif scope == "read":
        from app.db import get_user_book_by_status_and_index_m2m

        total = count_user_books_by_status_m2m(user_id, "read")
        new_index = index if index < total else max(total - 1, 0)
        await render_status_carousel(callback, status="read", index=new_index)
    elif scope == "fav":
        total = count_user_favorites(user_id)
        new_index = index if index < total else max(total - 1, 0)
        await render_favorites_carousel(callback, index=new_index)
    else:
        await show_main_menu(callback)
