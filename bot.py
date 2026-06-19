from pyrogram import Client, filters
from pyrogram.enums import ParseMode
import os
import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz  # если не установлен, выполните pip install pytz

# ---------- КОНФИГУРАЦИЯ ----------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Если хотите использовать местное время (например, Москва), раскомментируйте:
# TIMEZONE = pytz.timezone('Europe/Moscow')
# и в коде ниже замените datetime.now() на datetime.now(TIMEZONE)

app = Client("mention_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

JOBS_FILE = "jobs.json"
jobs = {}        # { chat_id: [ {id, text, next_run, interval}, ... ] }
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
        now = datetime.utcnow().timestamp()  # используем UTC
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
@app.on_message(filters.command("all") & filters.group)
async def mention_all(client, message):
    chat_id = message.chat.id
    try:
        users = []
        async for member in app.get_chat_members(chat_id):
            if not member.user.is_bot:
                users.append(member.user)
        if not users:
            await message.reply("Нет участников.")
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
            msg = "📢 Всем привет!\n\n" + " ".join(chunk)
            await app.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.reply(f"Ошибка: {e}")

# ---------- КОМАНДА /start ----------
@app.on_message(filters.command("start") & filters.group)
async def start_cmd(client, message):
    await message.reply(
        "👋 Команды:\n"
        "/all – упомянуть всех\n"
        "/set_remind HH:MM Текст – разовое\n"
        "/set_remind HH:MM daily Текст – ежедневно\n"
        "/set_remind HH:MM weekly Текст – еженедельно\n"
        "/set_remind HH:MM 2 Текст – каждые 2 часа\n"
        "/list_reminds – список\n"
        "/cancel_remind [ID] – отменить все или по ID\n\n"
        "⚠️ Время указывается в UTC (по Гринвичу).\n"
        "Если ваш часовой пояс +3 (Москва), то для 20:00 по Москве пишите 17:00 UTC."
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
        period = "разовое" if interval is None else ("ежедневно" if interval == 86400 else "еженедельно" if interval == 604800 else f"каждые {interval//3600} ч.")
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

# ---------- КОМАНДА /set_remind ----------
@app.on_message(filters.command("set_remind") & filters.group)
async def set_remind(client, message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Пример: /set_remind 20:00 daily Текст")
            return
        arg_str = args[1].strip()
        pattern = r'^(\d{1,2}:\d{2})\s+(?:(daily|weekly|\d+)\s+)?(.+)$'
        match = re.match(pattern, arg_str)
        if not match:
            await message.reply("Неверный формат.\nПример: /set_remind 20:00 daily Текст")
            return
        time_str = match.group(1)
        keyword = match.group(2)
        text = match.group(3)

        # Парсим время (UTC)
        remind_time = datetime.strptime(time_str, "%H:%M")
        now = datetime.utcnow()
        scheduled = datetime(now.year, now.month, now.day, remind_time.hour, remind_time.minute)
        if scheduled < now:
            scheduled += timedelta(days=1)

        interval = None
        if keyword is None:
            pass
        elif keyword.lower() == "daily":
            interval = 86400
        elif keyword.lower() == "weekly":
            interval = 604800
        elif keyword.isdigit():
            hours = int(keyword)
            if hours <= 0:
                await message.reply("Интервал должен быть > 0.")
                return
            interval = hours * 3600
        else:
            await message.reply("Неизвестное ключевое слово (используйте daily, weekly или число часов).")
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

        period = "разовое" if interval is None else ("ежедневно" if interval == 86400 else "еженедельно" if interval == 604800 else f"каждые {interval//3600} ч.")
        await message.reply(
            f"✅ Напоминание ID {rem_id} установлено.\n"
            f"Первое срабатывание: {scheduled.strftime('%d.%m.%Y %H:%M')} UTC\n"
            f"Тип: {period}\n"
            f"Текст: {text}"
        )
    except Exception as e:
        await message.reply(f"Ошибка: {e}")

# ---------- ЗАПУСК ----------
async def main():
    load_jobs()
    asyncio.create_task(scheduler_loop())
    print("🚀 Бот запущен. Планировщик активен.")
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
