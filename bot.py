from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand
import os
import asyncio
import json
import re
from datetime import datetime, timedelta

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("mention_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

JOBS_FILE = "jobs.json"
jobs = {}
job_counter = 0

def load_jobs():
    global jobs, job_counter
    try:
        with open(JOBS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            jobs = data.get("jobs", {})
            job_counter = data.get("counter", 0)
        print(f"Загружено напоминаний: {sum(len(v) for v in jobs.values())}")
    except FileNotFoundError:
        jobs = {}
        job_counter = 0

def save_jobs():
    with open(JOBS_FILE, 'w', encoding='utf-8') as f:
        json.dump({"jobs": jobs, "counter": job_counter}, f, ensure_ascii=False, indent=2)

# ---------- ОТПРАВКА УПОМИНАНИЙ ----------
async def send_reminder(chat_id, text):
    try:
        users = []
        async for member in app.get_chat_members(chat_id):
            if not member.user.is_bot:
                users.append(member.user)
        if not users:
            await app.send_message(chat_id, "Нет участников для упоминания.")
            return
        mentions = []
        for user in users:
            if user.username:
                mentions.append(f"@{user.username}")
            else:
                mentions.append(f'<a href="tg://user?id={user.id}">{user.first_name}</a>')
        chunk_size = 50
        for i in range(0, len(mentions), chunk_size):
            chunk = mentions[i:i+chunk_size]
            msg = f"🔔 {text}\n\n" + " ".join(chunk)
            await app.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
        print(f"Упомянуто {len(users)} участников в чате {chat_id}")
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        await app.send_message(chat_id, f"Ошибка: {e}")

# ---------- ПЛАНИРОВЩИК ----------
async def scheduler_loop():
    while True:
        now = datetime.utcnow().timestamp()
        for chat_id_str, reminds in list(jobs.items()):
            chat_id = int(chat_id_str)
            for r in reminds[:]:
                if r["next_run"] <= now:
                    await send_reminder(chat_id, r["text"])
                    if r.get("interval") is not None:
                        r["next_run"] += r["interval"]
                    else:
                        reminds.remove(r)
            if not reminds:
                del jobs[chat_id_str]
        save_jobs()
        await asyncio.sleep(30)

# ---------- КОМАНДА /all ----------
@app.on_message(filters.command("set_remind") & filters.group)
async def set_remind(client, message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("❌ Пример: /set_remind 20:00 daily Текст")
            return

        # Разбиваем аргументы на части
        parts = args[1].split()
        if len(parts) < 2:
            await message.reply("❌ Слишком мало аргументов. Нужно: время и текст.")
            return

        # Первая часть — время
        time_str = parts[0]
        # Проверяем формат времени
        if not re.match(r'^\d{1,2}:\d{2}$', time_str):
            await message.reply("❌ Неверный формат времени. Используйте HH:MM (например, 20:00).")
            return

        # Остальные части — интервал (необязательный) и текст
        rest = parts[1:]
        interval_keyword = None
        text_start_index = 0

        # Проверяем, является ли первое слово после времени ключевым словом интервала
        if rest:
            first = rest[0].lower()
            # Проверяем daily, weekly
            if first in ("daily", "weekly"):
                interval_keyword = first
                text_start_index = 1
            # Проверяем формат число + суффикс (2h, 3d, 1w) или просто число (часы)
            elif re.match(r'^(\d+)([hdw])?$', first):
                interval_keyword = first
                text_start_index = 1
            # Если ни одно условие не подошло, значит интервал не указан, текст начинается с первого слова
            else:
                interval_keyword = None
                text_start_index = 0

        # Собираем текст из оставшихся слов
        if text_start_index < len(rest):
            text = " ".join(rest[text_start_index:])
        else:
            text = ""

        if not text:
            await message.reply("❌ Вы не указали текст напоминания.")
            return

        # Парсим время
        remind_time = datetime.strptime(time_str, "%H:%M")
        now = datetime.utcnow()
        scheduled = datetime(now.year, now.month, now.day, remind_time.hour, remind_time.minute)
        if scheduled < now:
            scheduled += timedelta(days=1)

        # Определяем интервал в секундах
        interval = None
        if interval_keyword is None:
            # разовое
            pass
        elif interval_keyword == "daily":
            interval = 86400
        elif interval_keyword == "weekly":
            interval = 604800
        else:
            # Это может быть число или число+суффикс
            match = re.match(r'^(\d+)([hdw])?$', interval_keyword)
            if match:
                val = int(match.group(1))
                unit = match.group(2) if match.group(2) else 'h'  # по умолчанию часы
                if unit == 'h':
                    interval = val * 3600
                elif unit == 'd':
                    interval = val * 86400
                elif unit == 'w':
                    interval = val * 604800
                else:
                    interval = val * 3600  # fallback
            else:
                await message.reply("❌ Неизвестный интервал. Используйте daily, weekly, 2h, 3d, 1w или просто число (часы).")
                return

        global job_counter
        job_counter += 1
        rem_id = job_counter
        new_job = {
            "id": rem_id,
            "text": text,
            "next_run": scheduled.timestamp(),
            "interval": interval
        }
        chat_id = str(message.chat.id)
        if chat_id not in jobs:
            jobs[chat_id] = []
        jobs[chat_id].append(new_job)
        save_jobs()

        # Формируем читаемое описание периода
        if interval is None:
            period = "разовое"
        elif interval == 86400:
            period = "ежедневно"
        elif interval == 604800:
            period = "еженедельно"
        else:
            hours = interval // 3600
            if interval % 86400 == 0:
                days = interval // 86400
                period = f"каждые {days} дн."
            else:
                period = f"каждые {hours} ч."

        await message.reply(
            f"✅ Напоминание ID {rem_id} установлено.\n"
            f"🕐 Первое срабатывание: {scheduled.strftime('%d.%m.%Y %H:%M')} UTC\n"
            f"🔄 Тип: {period}\n"
            f"📝 Текст: {text}"
        )
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

# ---------- КОМАНДА /start ----------
@app.on_message(filters.command("start") & filters.group)
async def start_cmd(client, message):
    await message.reply(
        "👋 Команды:\n"
        "/all – упомянуть всех\n"
        "/set_remind HH:MM [интервал] Текст\n"
        "   интервал (необязательно):\n"
        "   • daily – каждый день\n"
        "   • weekly – каждую неделю\n"
        "   • число (например, 2) – часы (каждые 2 часа)\n"
        "   • число + h (например, 3h) – часы\n"
        "   • число + d (например, 2d) – дни (каждые 2 дня)\n"
        "   • число + w (например, 1w) – недели\n"
        "   Примеры:\n"
        "   /set_remind 20:00 Разовое\n"
        "   /set_remind 20:00 daily Ежедневное\n"
        "   /set_remind 20:00 2d Через день\n"
        "   /set_remind 20:00 3h Каждые 3 часа\n"
        "/list_reminds – список активных\n"
        "/cancel_remind [ID] – отменить все или по ID\n\n"
        "⚠️ Время указывается в UTC (по Гринвичу).\n"
        "Например, для 20:00 по Москве пишите 17:00 UTC."
    )

# ---------- КОМАНДА /list_reminds ----------
@app.on_message(filters.command("list_reminds") & filters.group)
async def list_reminds(client, message):
    chat_id = str(message.chat.id)
    if chat_id not in jobs or not jobs[chat_id]:
        await message.reply("Нет активных напоминаний.")
        return
    text = "📋 Активные напоминания:\n"
    for r in jobs[chat_id]:
        dt = datetime.utcfromtimestamp(r["next_run"]).strftime("%d.%m.%Y %H:%M UTC")
        interval = r.get("interval")
        if interval is None:
            period = "разовое"
        elif interval == 86400:
            period = "ежедневно"
        elif interval == 604800:
            period = "еженедельно"
        else:
            hours = interval // 3600
            if interval % 86400 == 0:
                days = interval // 86400
                period = f"каждые {days} дн."
            else:
                period = f"каждые {hours} ч."
        text += f"ID {r['id']}: {dt} ({period}) – {r['text'][:30]}...\n"
    await message.reply(text)

# ---------- КОМАНДА /cancel_remind ----------
@app.on_message(filters.command("cancel_remind") & filters.group)
async def cancel_remind(client, message):
    chat_id = str(message.chat.id)
    if chat_id not in jobs or not jobs[chat_id]:
        await message.reply("Нет активных напоминаний.")
        return
    args = message.text.split()
    if len(args) == 1:
        jobs[chat_id] = []
        save_jobs()
        await message.reply("❌ Все напоминания в этом чате отменены.")
        return
    try:
        rem_id = int(args[1])
        for r in jobs[chat_id]:
            if r["id"] == rem_id:
                jobs[chat_id].remove(r)
                save_jobs()
                await message.reply(f"❌ Напоминание ID {rem_id} отменено.")
                return
        await message.reply(f"Напоминание с ID {rem_id} не найдено.")
    except ValueError:
        await message.reply("Укажите корректный ID.")

# ---------- КОМАНДА /set_remind (с поддержкой расширенных интервалов) ----------
@app.on_message(filters.command("set_remind") & filters.group)
async def set_remind(client, message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("❌ Пример: /set_remind 20:00 daily Текст")
            return
        arg_str = args[1].strip()

        # Расширенный шаблон: время, затем необязательный интервал, затем текст
        pattern = r'^(\d{1,2}:\d{2})\s+(?:(daily|weekly|(\d+)([hdw])?)\s+)?(.+)$'
        match = re.match(pattern, arg_str, re.IGNORECASE)
        if not match:
            await message.reply(
                "❌ Неверный формат.\n"
                "Правильно:\n"
                "/set_remind 20:00 Текст – разовое\n"
                "/set_remind 20:00 daily Текст – ежедневно\n"
                "/set_remind 20:00 weekly Текст – еженедельно\n"
                "/set_remind 20:00 2 Текст – каждые 2 часа\n"
                "/set_remind 20:00 3h Текст – каждые 3 часа\n"
                "/set_remind 20:00 2d Текст – каждые 2 дня\n"
                "/set_remind 20:00 1w Текст – каждую неделю"
            )
            return

        time_str = match.group(1)
        keyword = match.group(2)                 # daily, weekly, или None
        num = match.group(3)                     # число, если ввели
        unit = match.group(4)                    # h, d, w или None
        text = match.group(5)

        # Парсим время
        remind_time = datetime.strptime(time_str, "%H:%M")
        now = datetime.utcnow()
        scheduled = datetime(now.year, now.month, now.day, remind_time.hour, remind_time.minute)
        if scheduled < now:
            scheduled += timedelta(days=1)

        # Определяем интервал в секундах
        interval = None
        if keyword is None and num is None:
            # разовое
            pass
        elif keyword is not None:
            if keyword.lower() == "daily":
                interval = 86400          # 24 часа
            elif keyword.lower() == "weekly":
                interval = 604800         # 7 дней
            else:
                await message.reply("❌ Неизвестное ключевое слово.")
                return
        else:
            # Есть число и возможно единица
            val = int(num)
            if unit is None or unit.lower() == 'h':
                interval = val * 3600     # часы
            elif unit.lower() == 'd':
                interval = val * 86400    # дни
            elif unit.lower() == 'w':
                interval = val * 604800   # недели
            else:
                await message.reply("❌ Неизвестная единица. Используйте h, d, w или ничего (часы).")
                return
            if interval <= 0:
                await message.reply("❌ Интервал должен быть больше 0.")
                return

        global job_counter
        job_counter += 1
        rem_id = job_counter
        new_job = {
            "id": rem_id,
            "text": text,
            "next_run": scheduled.timestamp(),
            "interval": interval
        }
        chat_id = str(message.chat.id)
        if chat_id not in jobs:
            jobs[chat_id] = []
        jobs[chat_id].append(new_job)
        save_jobs()

        # Формируем читаемое описание периода
        if interval is None:
            period = "разовое"
        elif interval == 86400:
            period = "ежедневно"
        elif interval == 604800:
            period = "еженедельно"
        else:
            hours = interval // 3600
            if interval % 86400 == 0:
                days = interval // 86400
                period = f"каждые {days} дн."
            else:
                period = f"каждые {hours} ч."

        await message.reply(
            f"✅ Напоминание ID {rem_id} установлено.\n"
            f"🕐 Первое срабатывание: {scheduled.strftime('%d.%m.%Y %H:%M')} UTC\n"
            f"🔄 Тип: {period}\n"
            f"📝 Текст: {text}"
        )
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

# ---------- МЕНЮ КОМАНД ----------
async def set_commands():
    commands = [
        BotCommand("all", "Упомянуть всех участников"),
        BotCommand("set_remind", "Установить напоминание (разовое / с интервалом)"),
        BotCommand("list_reminds", "Показать активные напоминания"),
        BotCommand("cancel_remind", "Отменить напоминание"),
        BotCommand("start", "Помощь"),
    ]
    await app.set_bot_commands(commands)
    print("✅ Меню команд установлено.")

# ---------- ЗАПУСК ----------
async def main():
    load_jobs()
    asyncio.create_task(scheduler_loop())
    await app.start()
    await set_commands()
    print("🚀 Бот запущен. Поддерживаются интервалы: daily, weekly, часы (число), дни (число+d), недели (число+w).")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
