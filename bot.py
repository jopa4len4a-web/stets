import os
import asyncio
import json
import base64

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# === ТОКЕН ЗАМЕНИ НА СВОЙ ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН_ОТ_BOTFATHER")

dp = Dispatcher(storage=MemoryStorage())
ACTIVE = {}   # { user_id: {"proc": ..., "chat_id": ..., "host": ..., "port": ...} }


class S(StatesGroup):
    host = State()
    port = State()
    count = State()
    answer = State()


def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚀 Запустить")],
        [KeyboardButton(text="📊 Статус"), KeyboardButton(text="⏹ Стоп")],
    ], resize_keyboard=True)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Стресс-бот Minecraft с ручным решением капч.\n\n"
        "Жми 🚀 Запустить",
        reply_markup=main_kb()
    )


@dp.message(F.text == "🚀 Запустить")
async def go(message: types.Message, state: FSMContext):
    if message.from_user.id in ACTIVE:
        await message.answer("❌ Уже запущено.")
        return
    await message.answer("Хост сервера (IP или домен):")
    await state.set_state(S.host)


@dp.message(S.host)
async def h(message: types.Message, state: FSMContext):
    await state.update_data(host=message.text.strip())
    await message.answer("Порт (обычно 25565):")
    await state.set_state(S.port)


@dp.message(S.port)
async def p(message: types.Message, state: FSMContext):
    try:
        port = int(message.text.strip())
    except ValueError:
        await message.answer("Порт — число.")
        return
    await state.update_data(port=port)
    await message.answer("Сколько ботов? (1–10, для ручного решения капч):")
    await state.set_state(S.count)


@dp.message(S.count)
async def c(message: types.Message, state: FSMContext):
    try:
        cnt = int(message.text.strip())
        if not 1 <= cnt <= 10:
            raise ValueError
    except ValueError:
        await message.answer("Число 1–10.")
        return

    data = await state.get_data()
    host, port = data["host"], data["port"]

    # Запуск Node.js воркера
    proc = await asyncio.create_subprocess_exec(
        "node", "stress.js", host, str(port), str(cnt), "500",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
    )

    ACTIVE[message.from_user.id] = {
        "proc": proc,
        "chat_id": message.chat.id,
        "host": host,
        "port": port,
        "count": cnt,
    }

    asyncio.create_task(reader_task(message.from_user.id))
    await message.answer(f"🚀 Запущено {cnt} ботов на {host}:{port}.\nЖди капчи.")
    await state.clear()


async def reader_task(uid):
    """Читает JSON из Node.js и обрабатывает."""
    entry = ACTIVE.get(uid)
    if not entry:
        return
    proc = entry["proc"]
    bot = Bot(token=BOT_TOKEN)

    while uid in ACTIVE:
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
        except asyncio.TimeoutError:
            continue

        if not line:
            ACTIVE.pop(uid, None)
            try:
                await bot.send_message(entry["chat_id"], "⏹ Процесс завершён.")
            except Exception:
                pass
            return

        try:
            data = json.loads(line.decode().strip())
        except Exception:
            continue

        t = data.get("type")

        if t == "ok":
            await bot.send_message(entry["chat_id"], f"✅ Бот #{data['i']} зашёл на сервер.")

        elif t == "captcha_prompt":
            await bot.send_message(
                entry["chat_id"],
                f"⚠️ Бот #{data['i']} — antibot просит ответ:\n`{data.get('text', '')}`",
                parse_mode="Markdown"
            )

        elif t == "captcha_map":
            png = base64.b64decode(data["png_base64"])
            bot_id = data["i"]
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"✍️ Ответить за бота #{bot_id}",
                    callback_data=f"ans_{bot_id}"
                )]
            ])
            file = BufferedInputFile(png, filename=f"captcha_{bot_id}.png")
            await bot.send_photo(
                entry["chat_id"], file,
                caption=f"🧩 Капча для бота #{bot_id}\nРеши и нажми кнопку.",
                reply_markup=kb
            )

        elif t == "fail":
            await bot.send_message(entry["chat_id"], f"❌ Бот #{data['i']}: {data.get('error', '')}")

        elif t == "kick":
            await bot.send_message(entry["chat_id"], f"👢 Бот #{data['i']} кикнут: {data.get('reason', '')}")


@dp.callback_query(F.data.startswith("ans_"))
async def answer_start(callback: types.CallbackQuery, state: FSMContext):
    bot_id = int(callback.data.split("_")[1])
    await state.update_data(bot_id=bot_id)
    await callback.message.answer(f"Введи ответ для бота #{bot_id}:")
    await state.set_state(S.answer)
    await callback.answer()


@dp.message(S.answer)
async def answer_send(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    entry = ACTIVE.get(uid)
    if not entry:
        await message.answer("❌ Тест не запущен.")
        await state.clear()
        return

    data = await state.get_data()
    bot_id = data.get("bot_id")
    answer = message.text.strip()

    payload = json.dumps({"type": "say", "bot_id": bot_id, "text": answer}) + "\n"
    try:
        entry["proc"].stdin.write(payload.encode())
        await entry["proc"].stdin.drain()
        await message.answer(f"✅ Бот #{bot_id} отправил: `{answer}`", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    await state.clear()


@dp.message(F.text == "📊 Статус")
async def status(message: types.Message):
    entry = ACTIVE.get(message.from_user.id)
    if not entry:
        await message.answer("Нет активного теста.")
        return
    await message.answer(f"🎮 {entry['host']}:{entry['port']}\n🤖 Ботов: {entry['count']}")


@dp.message(F.text == "⏹ Стоп")
async def stop(message: types.Message):
    uid = message.from_user.id
    entry = ACTIVE.pop(uid, None)
    if not entry:
        await message.answer("Нечего останавливать.")
        return
    try:
        entry["proc"].terminate()
    except Exception:
        pass
    await message.answer("⏹ Остановлено.")


@dp.message()
async def fallback(message: types.Message):
    pass


async def main():
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
