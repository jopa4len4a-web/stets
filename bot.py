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

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_СЮДА_ТОКЕН")

dp = Dispatcher(storage=MemoryStorage())
ACTIVE = {}  # { user_id: {"proc": ..., "chat_id": ..., "config": ...} }


class S(StatesGroup):
    host = State()
    port = State()
    count = State()
    delay = State()
    nickname = State()
    version = State()
    proxy = State()
    chat_cmds = State()
    skip = State()
    answer = State()
    broadcast = State()


def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚀 Запустить")],
        [KeyboardButton(text="📢 Написать всем")],
        [KeyboardButton(text="📊 Статус"), KeyboardButton(text="⏹ Стоп")],
    ], resize_keyboard=True)


def version_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Auto", callback_data="v_auto"),
         InlineKeyboardButton(text="1.21.4", callback_data="v_1.21.4")],
        [InlineKeyboardButton(text="1.21.1", callback_data="v_1.21.1"),
         InlineKeyboardButton(text="1.20.4", callback_data="v_1.20.4")],
        [InlineKeyboardButton(text="1.20.1", callback_data="v_1.20.1"),
         InlineKeyboardButton(text="1.19.4", callback_data="v_1.19.4")],
        [InlineKeyboardButton(text="1.16.5", callback_data="v_1.16.5"),
         InlineKeyboardButton(text="1.12.2", callback_data="v_1.12.2")],
        [InlineKeyboardButton(text="1.8.9", callback_data="v_1.8.9"),
         InlineKeyboardButton(text="✍️ Ввести свою", callback_data="v_custom")],
    ])


def skip_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Пропуск если нет капчи (30 сек)", callback_data="skip_yes")],
        [InlineKeyboardButton(text="⏸ Ждать капчу всегда", callback_data="skip_no")],
    ])


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Стресс-бот Minecraft с реалистичными ботами.\n\n"
        "🚀 Запустить — настройка и старт.\n"
        "📢 Написать всем — команда от всех ботов в чат.\n"
        "📊 Статус / ⏹ Стоп — управление.\n\n"
        "⚠️ Только СВОЙ сервер.",
        reply_markup=main_kb()
    )


# === ЗАПУСК ===
@dp.message(F.text == "🚀 Запустить")
async def go(message: types.Message, state: FSMContext):
    if message.from_user.id in ACTIVE:
        await message.answer("❌ Уже запущено. Останови сначала.")
        return
    await message.answer("1️⃣ Хост сервера (IP или домен):")
    await state.set_state(S.host)


@dp.message(S.host)
async def st_host(message: types.Message, state: FSMContext):
    await state.update_data(host=message.text.strip())
    await message.answer("2️⃣ Порт (25565 по умолчанию):")
    await state.set_state(S.port)


@dp.message(S.port)
async def st_port(message: types.Message, state: FSMContext):
    try:
        port = int(message.text.strip())
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        await message.answer("Число 1–65535.")
        return
    await state.update_data(port=port)
    await message.answer("3️⃣ Сколько ботов? (1–500)")
    await state.set_state(S.count)


@dp.message(S.count)
async def st_count(message: types.Message, state: FSMContext):
    try:
        cnt = int(message.text.strip())
        if not 1 <= cnt <= 500:
            raise ValueError
    except ValueError:
        await message.answer("Число 1–500.")
        return
    await state.update_data(count=cnt)
    await message.answer("4️⃣ Задержка между входами (мс, 100–10000):")
    await state.set_state(S.delay)


@dp.message(S.delay)
async def st_delay(message: types.Message, state: FSMContext):
    try:
        d = int(message.text.strip())
        if not 100 <= d <= 10000:
            raise ValueError
    except ValueError:
        await message.answer("100–10000.")
        return
    await state.update_data(delay=d)
    await message.answer(
        "5️⃣ Шаблон ника. `{i}` — номер бота.\n"
        "Примеры: `SB_{i}`, `Player_{i}`, `MyBot_{i}`\n"
        "Или `random` — случайные ники.",
        parse_mode="Markdown"
    )
    await state.set_state(S.nickname)


@dp.message(S.nickname)
async def st_nick(message: types.Message, state: FSMContext):
    await state.update_data(nickname=message.text.strip())
    await message.answer("6️⃣ Версия клиента:", reply_markup=version_kb())
    await state.set_state(S.version)


@dp.callback_query(F.data.startswith("v_"))
async def st_version(callback: types.CallbackQuery, state: FSMContext):
    v = callback.data.split("_", 1)[1]
    if v == "custom":
        await callback.message.edit_text("✍️ Введи версию вручную (например `1.20.1`):", parse_mode="Markdown")
        await state.update_data(await_custom_version=True)
        await callback.answer()
        return
    await state.update_data(version=v, await_custom_version=False)
    await callback.message.edit_text(f"✅ Версия: {v}")
    await ask_proxy(callback.message, state)
    await callback.answer()


@dp.message(S.version)
async def st_custom_version(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("await_custom_version"):
        return
    await state.update_data(version=message.text.strip(), await_custom_version=False)
    await message.answer(f"✅ Версия: {message.text.strip()}")
    await ask_proxy(message, state)


async def ask_proxy(msg, state):
    await msg.answer(
        "7️⃣ Прокси (опционально).\n\n"
        "Список построчно: `ip:port` или `ip:port:user:pass`\n"
        "Или `нет`."
    )
    await state.set_state(S.proxy)


@dp.message(S.proxy)
async def st_proxy(message: types.Message, state: FSMContext):
    text = message.text.strip()
    proxies = [] if text.lower() in ("нет", "no", "-") else [l.strip() for l in text.splitlines() if l.strip()]
    await state.update_data(proxies=proxies)
    await message.answer(
        "8️⃣ Команды для автоматического ввода после входа.\n\n"
        "Пример: `/reg пароль пароль` затем `/login пароль`\n"
        "Каждая команда — с новой строки, отправляются с паузой 1.5 сек.\n\n"
        "Отправь `-`, если не нужно."
    )
    await state.set_state(S.chat_cmds)


@dp.message(S.chat_cmds)
async def st_cmds(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "-":
        cmds = []
    else:
        cmds = [l.strip() for l in text.splitlines() if l.strip()]
    await state.update_data(chat_cmds=cmds)
    await message.answer(
        f"✅ Команд: {len(cmds)}\n\n9️⃣ Пропускать капчу, если её нет 30 секунд?",
        reply_markup=skip_kb()
    )
    await state.set_state(S.skip)


@dp.callback_query(F.data.startswith("skip_"))
async def st_skip(callback: types.CallbackQuery, state: FSMContext):
    val = callback.data.endswith("yes")
    await state.update_data(skip_if_none=val)

    data = await state.get_data()
    config = {
        "host": data["host"],
        "port": data["port"],
        "count": data["count"],
        "delay": data["delay"],
        "nickname": data["nickname"],
        "version": data["version"],
        "proxies": data["proxies"],
        "chat_cmds": data["chat_cmds"],
        "skip_if_none": val,
    }

    proc = await asyncio.create_subprocess_exec(
        "node", "stress.js",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
    )
    proc.stdin.write((json.dumps({"type": "config", **config}) + "\n").encode())
    await proc.stdin.drain()

    ACTIVE[callback.from_user.id] = {
        "proc": proc,
        "chat_id": callback.message.chat.id,
        "config": config,
    }
    asyncio.create_task(reader_task(callback.from_user.id))

    await callback.message.edit_text(
        f"🚀 Тест запущен.\n\n"
        f"🎮 {config['host']}:{config['port']}\n"
        f"🤖 Ботов: {config['count']}\n"
        f"⏱ Задержка: {config['delay']} мс\n"
        f"🏷 Ники: {config['nickname']}\n"
        f"📦 Версия: {config['version']}\n"
        f"🌐 Прокси: {len(config['proxies'])}\n"
        f"💬 Команд: {len(config['chat_cmds'])}"
    )
    await callback.answer("Запущено")
    await state.clear()


# === РАССЫЛКА ОТ ВСЕХ БОТОВ ===
@dp.message(F.text == "📢 Написать всем")
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ACTIVE:
        await message.answer("❌ Нет активного теста.")
        return
    await message.answer(
        "✍️ Отправь команду/текст, который напишут ВСЕ боты:\n\n"
        "Например: `/reg qwerty qwerty` или `привет всем`"
    )
    await state.set_state(S.broadcast)


@dp.message(S.broadcast)
async def broadcast_send(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    entry = ACTIVE.get(uid)
    if not entry:
        await message.answer("❌ Тест не запущен.")
        await state.clear()
        return

    text = message.text.strip()
    payload = json.dumps({"type": "broadcast", "text": text}) + "\n"
    try:
        entry["proc"].stdin.write(payload.encode())
        await entry["proc"].stdin.drain()
        await message.answer(f"📢 Отправлено всем ботам: `{text}`", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    await state.clear()


# === ЧТЕНИЕ ЛОГОВ NODE.JS ===
async def reader_task(uid):
    entry = ACTIVE.get(uid)
    if not entry:
        return
    proc = entry["proc"]
    bot = Bot(token=BOT_TOKEN)

    async def read_stdout():
        while uid in ACTIVE:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
            except asyncio.TimeoutError:
                continue
            if not line:
                return
            try:
                data = json.loads(line.decode().strip())
            except Exception:
                continue
            await handle_event(bot, entry, data)

    async def read_stderr():
        while uid in ACTIVE:
            try:
                line = await asyncio.wait_for(proc.stderr.readline(), timeout=5)
            except asyncio.TimeoutError:
                continue
            if not line:
                return
            text = line.decode().strip()
            if text:
                try:
                    await bot.send_message(entry["chat_id"], f"⚠️ Node.js: `{text[:500]}`", parse_mode="Markdown")
                except Exception:
                    pass

    try:
        await asyncio.gather(read_stdout(), read_stderr())
    finally:
        ACTIVE.pop(uid, None)
        try:
            await bot.send_message(entry["chat_id"], "⏹ Процесс завершён.")
        except Exception:
            pass


async def handle_event(bot, entry, data):
    t = data.get("type")

    if t == "ok":
        await bot.send_message(entry["chat_id"], f"✅ #{data['i']} ({data.get('username')}) зашёл.")

    elif t == "captcha_prompt":
        await bot.send_message(
            entry["chat_id"],
            f"⚠️ #{data['i']} — antibot:\n`{data.get('text', '')}`",
            parse_mode="Markdown"
        )

    elif t == "captcha_map":
        png = base64.b64decode(data["png_base64"])
        bot_id = data["i"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✍️ Ответить за #{bot_id}", callback_data=f"ans_{bot_id}")]
        ])
        file = BufferedInputFile(png, filename=f"captcha_{bot_id}.png")
        await bot.send_photo(entry["chat_id"], file, caption=f"🧩 Капча для #{bot_id}", reply_markup=kb)

    elif t == "no_captcha":
        await bot.send_message(entry["chat_id"], f"✅ #{data['i']} прошёл без капчи.")

    elif t == "fail":
        await bot.send_message(entry["chat_id"], f"❌ #{data['i']}: {data.get('error', '')}")

    elif t == "kick":
        await bot.send_message(entry["chat_id"], f"👢 #{data['i']} кикнут: {data.get('reason', '')}")


@dp.callback_query(F.data.startswith("ans_"))
async def answer_start(callback: types.CallbackQuery, state: FSMContext):
    bot_id = int(callback.data.split("_")[1])
    await state.update_data(bot_id=bot_id)
    await callback.message.answer(f"✍️ Введи ответ для #{bot_id}:")
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
        await message.answer(f"✅ #{bot_id} отправил: `{answer}`", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ {e}")
    await state.clear()


@dp.message(F.text == "📊 Статус")
async def status(message: types.Message):
    entry = ACTIVE.get(message.from_user.id)
    if not entry:
        await message.answer("Нет активного теста.")
        return
    c = entry["config"]
    await message.answer(
        f"🎮 {c['host']}:{c['port']}\n"
        f"🤖 Ботов: {c['count']}\n"
        f"📦 Версия: {c['version']}\n"
        f"🌐 Прокси: {len(c['proxies'])}"
    )


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
