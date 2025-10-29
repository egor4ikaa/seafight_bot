import copy
import random
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
load_dotenv()

# Создаем объекты бота и диспетчера
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# Инициализируем константу размера игрового поля
FIELD_SIZE = 8
MINE_COUNT = 10


# Создаем словарь соответствий
LEXICON = {
    "/start": "Вот твоё поле. Можешь делать ход",
    "/help": "Сапёр — классическая игра! Нажимай на клетки, чтобы открыть их. "
             "Не попадись на мину! 💣\nНажми /start, чтобы начать.",
    "closed": "⬜",
    "mine": "💣",
    "empty": " ",
    "used": "Вы уже открывали эту клетку!",
    "hit_mine": "💥 Вы попали на мину! Игра окончена.",
    "next_move": "Делайте ваш следующий ход",
    "win": "🎉 Поздравляем! Вы нашли все безопасные клетки!",
    "flags": "🚩",
}

# Хардкодим расположение кораблей на игровом поле
users: dict[int, dict] = {}


# Создаём свой класс фабрики коллбэков, указывая префикс
# и структуру callback_data
class FieldCallbackFactory(CallbackData, prefix="minesweeper"):
    x: int
    y: int


# Функция, которая пересоздает новое поле для каждого игрока
def generate_mines(seed_field: list[list[int]], mine_count: int):
    "Генерирует случайные мины на поле."
    positions = [(i, j) for i in range(FIELD_SIZE) for j in range(FIELD_SIZE)]
    mine_positions = random.sample(positions, mine_count)
    for x, y in mine_positions:
        seed_field[x][y] = -1  # -1 означает мину

def count_mines_around(field: list[list[int]], x: int, y: int) -> int:
    "Считает количество мин вокруг клетки (x, y)."
    count = 0
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            nx, ny = x + dx, y + dy
            if 0 <= nx < FIELD_SIZE and 0 <= ny < FIELD_SIZE:
                if field[nx][ny] == -1:
                    count += 1
    return count
def generate_hint_field(mine_field: list[list[int]]) -> list[list[int]]:
    """Создаёт поле с подсказками (числа вокруг мин)."""
    hint_field = [[0 for _ in range(FIELD_SIZE)] for _ in range(FIELD_SIZE)]
    for i in range(FIELD_SIZE):
        for j in range(FIELD_SIZE):
            if mine_field[i][j] == -1:
                hint_field[i][j] = -1
            else:
                hint_field[i][j] = count_mines_around(mine_field, i, j)
    return hint_field

# ... (всё, что до reset_game, остаётся без изменений)

def reset_game(user_id: int):
    """Сбрасывает игру для пользователя."""
    mine_field = [[0 for _ in range(FIELD_SIZE)] for _ in range(FIELD_SIZE)]
    generate_mines(mine_field, MINE_COUNT)
    hint_field = generate_hint_field(mine_field)
    revealed = [[0 for _ in range(FIELD_SIZE)] for _ in range(FIELD_SIZE)]
    flags = [[0 for _ in range(FIELD_SIZE)] for _ in range(FIELD_SIZE)]  # <-- ИСПРАВЛЕНО: инициализация flags

    users[user_id] = {
        "mine_field": mine_field,
        "hint_field": hint_field,
        "revealed": revealed,
        "game_over": False,
        "won": False,
        "flags": flags
    }

# ... (get_field_keyboard остаётся почти без изменений, но исправим опечатку)

def get_field_keyboard(user_id: int) -> InlineKeyboardMarkup:
    user_data = users[user_id]
    revealed = user_data["revealed"]
    flags = user_data["flags"]
    hint_field = user_data["hint_field"]
    mine_field = user_data["mine_field"]
    game_over = user_data["game_over"]

    buttons = []
    for i in range(FIELD_SIZE):
        row = []
        for j in range(FIELD_SIZE):
            if revealed[i][j] == 1:
                if hint_field[i][j] == -1:
                    row.append(InlineKeyboardButton(text=LEXICON["mine"], callback_data="noop"))
                elif hint_field[i][j] == 0:
                    row.append(InlineKeyboardButton(text=LEXICON["empty"], callback_data="noop"))
                else:
                    row.append(InlineKeyboardButton(text=str(hint_field[i][j]), callback_data="noop"))
            else:
                if flags[i][j] == 1:
                    # Показываем флажок
                    row.append(
                        InlineKeyboardButton(
                            text=LEXICON["flags"],  # <-- ИСПРАВЛЕНО: было "flag", но в LEXICON ключ "flags"
                            callback_data="noop",   # флажки не кликабельны напрямую
                        )
                    )
                elif game_over and mine_field[i][j] == -1:
                    row.append(InlineKeyboardButton(text=LEXICON["mine"], callback_data="noop"))
                else:
                    row.append(
                        InlineKeyboardButton(
                            text=LEXICON["closed"],
                            callback_data=FieldCallbackFactory(x=i, y=j).pack(),
                        )
                    )
        buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ... (reveal_empty_area и check_win без изменений)


@dp.message(CommandStart())
async def process_start_command(message: Message):
    user_id = message.from_user.id
    reset_game(user_id)
    await message.answer(
        text=LEXICON["/start"],
        reply_markup=get_field_keyboard(user_id)
    )


@dp.message(Command(commands='help'))
async def process_help_command(message: Message):
    await message.answer(LEXICON["/help"])


# 🔹 НОВАЯ КОМАНДА: /flag x y
@dp.message(Command(commands='flag'))
async def process_flag_command(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала начните игру командой /start.")
        return

    user_data = users[user_id]
    if user_data["game_over"]:
        await message.answer("Игра окончена! Нажмите /start для новой игры.")
        return

    try:
        parts = message.text.split()
        if len(parts) != 3:
            raise ValueError
        x = int(parts[1])
        y = int(parts[2])
        if not (0 <= x < FIELD_SIZE and 0 <= y < FIELD_SIZE):
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("Используйте: /flag X Y (например: /flag 2 3), где X и Y — координаты от 0 до 7.")
        return

    flags = user_data["flags"]
    revealed = user_data["revealed"]

    if revealed[x][y] == 1:
        await message.answer("Нельзя ставить флажок на открытую клетку!")
        return

    # Переключаем флажок
    if flags[x][y] == 1:
        flags[x][y] = 0
        await message.answer(f"Флажок с клетки ({x}, {y}) убран.")
    else:
        flags[x][y] = 1
        await message.answer(f"Флажок установлен на клетку ({x}, {y}).")

    # Обновляем поле
    try:
        await message.answer(
            text=LEXICON["next_move"],
            reply_markup=get_field_keyboard(user_id)
        )
    except TelegramBadRequest:
        pass


# 🔹 Теперь нажатие на клетку = ОТКРЫТЬ, а не ставить флажок!
@dp.callback_query(FieldCallbackFactory.filter())
async def process_cell_press(callback: CallbackQuery, callback_data: FieldCallbackFactory):
    user_id = callback.from_user.id
    x, y = callback_data.x, callback_data.y

    if user_id not in users:
        await callback.answer("Начните игру командой /start.")
        return

    user_data = users[user_id]
    if user_data["game_over"]:
        await callback.answer("Игра окончена! Нажмите /start для новой игры.")
        return

    revealed = user_data["revealed"]
    mine_field = user_data["mine_field"]
    flags = user_data["flags"]

    if revealed[x][y] == 1:
        await callback.answer(LEXICON["used"])
        return

    if flags[x][y] == 1:
        await callback.answer("Сначала уберите флажок с этой клетки командой /flag.")
        return

    # Открываем клетку
    revealed[x][y] = 1

    # Попали на мину?
    if mine_field[x][y] == -1:
        user_data["game_over"] = True
        await callback.message.edit_text(
            text=LEXICON["hit_mine"],
            reply_markup=get_field_keyboard(user_id)
        )
        return

    # Если пустая — раскрываем область
    if user_data["hint_field"][x][y] == 0:
        reveal_empty_area(user_id, x, y)

    # Проверка победы
    if check_win(user_id):
        user_data["won"] = True
        user_data["game_over"] = True
        await callback.message.edit_text(
            text=LEXICON["win"],
            reply_markup=get_field_keyboard(user_id)
        )
        return

    # Обновляем поле
    try:
        await callback.message.edit_text(
            text=LEXICON["next_move"],
            reply_markup=get_field_keyboard(user_id)
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(lambda c: c.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()
