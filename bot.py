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

# ---------- ПРОВЕРКА АДМИНА ----------
async def is_admin(chat_id, user_id):
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except:
        return False

# ---------- ФИЛЬТР ДЛЯ АДМИНОВ ----------
def admin_filter(_, __, message):
    # Проверка будет выполнена асинхронно в обработчике, тут просто заглушка
    # Можно использовать filters.create, но проще проверять внутри каждой команды
    return True  # проверяем внутри команды

# ---------- ОТПРАВКА УПОМИНАНИЙ (с учётом темы) ----------
async def send_reminder(chat_id, text, thread_id=None):
    try:
        users = []
        async for member in app.get_chat_members(chat_id):
            if not member.user.is_bot:
                users.append(member.user)
        if not users:
            await app.send_message(chat_id, "Нет участников для упоминания.", message_thread_id=thread_id)
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
            await app.send_message(chat_id, msg, parse_mode=ParseMode.HTML, message_thread_id=thread_id)
        print(f"Упомянуто {len(users)} участников в чате {chat_id} (тема {thread_id})")
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        await app.send_message(chat_id, f"Ошибка: {e}", message_thread_id=thread_id)

# ---------- ПЛАНИРОВЩИК ----------
async def scheduler_loop():
    while True:
        now = datetime.utcnow().timestamp()
        for chat_id_str, reminds in list(jobs.items()):
            chat_id = int(chat_id_str)
            for r in reminds[:]:
                if r["next_run"] <= now:
                    thread_id = r.get("thread_id")  # сохраняем тему из задания
                    await send_reminder(chat_id, r["text"], thread_id)
                    if r.get("interval") is not None:
                        r["next_run"] += r["interval"]
                    else:
                        reminds.remove(r)
            if not reminds:
                del jobs[chat_id_str]
        save_jobs()
        await asyncio.sleep(30)

# ---------- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТВЕТА В ТУ ЖЕ ТЕМУ ----------
async def reply_in_thread(message, text, **kwargs):
    """Отправляет ответ в ту же тему, откуда пришёл запрос."""
    thread_id = message.message_thread_id
    await app.send_message(
        message.chat.id,
        text,
        message_thread_id=thread_id,
        **kwargs
    )

# ---------- КОМАНДА /all (только для админов) ----------
@app.on_message(filters.command("all") & filters.group)
async def mention_all(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_admin(chat_id, user_id):
        await reply_in_thread(message, "⛔ Только для администраторов.")
        return
    try:
        users = []
        async for member in app.get_chat_members(chat_id):
            if not member.user.is_bot:
                users.append(member.user)
        if not users:
            await reply_in_thread(message, "Нет участников.")
            return
        mentions = []
        for user in users:
            if user.username:
                mentions.append(f"@{user.username}")
            else:
                mentions.append(f'<a href="tg://user?id={user.id}">{user.first_name}</a>')
        chunk_size = 50
        thread_id = message.message_thread_id
        for i in range(0, len(mentions), chunk_size):
            chunk = mentions[i:i+chunk_size]
            msg = "📢 Всем привет!\n\n" + " ".join(chunk)
            await app.send_message(chat_id, msg, parse_mode=ParseMode.HTML, message_thread_id=thread_id)
    except Exception as e:
        await reply_in_thread(message, f"Ошибка: {e}")

# ---------- КОМАНДА /start ----------
@app.on_message(filters.command("start") & filters.group)
async def start_cmd(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_admin(chat_id, user_id):
        await reply_in_thread(message, "⛔ Только для администраторов.")
        return
    await reply_in_thread(
        message,
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
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_admin(chat_id, user_id):
        await reply_in_thread(message, "⛔ Только для администраторов.")
        return
    chat_id_str = str(chat_id)
    if chat_id_str not in jobs or not jobs[chat_id_str]:
        await reply_in_thread(message, "Нет активных напоминаний.")
        return
    text = "📋 Активные напоминания:\n"
    for r in jobs[chat_id_str]:
        dt = datetime.utcfromtimestamp(r["next_run"]).strftime("%d.%m.%Y %H:%M UTC")
        interval = r.get("interval")
        period = "разовое" if interval is None else ("ежедневно" if interval == 86400 else "еженедельно" if interval == 604800 else f"каждые {interval//3600} ч.")
        text += f"ID {r['id']}: {dt} ({period}) – {r['text'][:30]}...\n"
    await reply_in_thread(message, text)

# ---------- КОМАНДА /cancel_remind ----------
@app.on_message(filters.command("cancel_remind") & filters.group)
async def cancel_remind(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_admin(chat_id, user_id):
        await reply_in_thread(message, "⛔ Только для администраторов.")
        return
    chat_id_str = str(chat_id)
    if chat_id_str not in jobs or not jobs[chat_id_str]:
        await reply_in_thread(message, "Нет активных напоминаний.")
        return
    args = message.text.split()
    if len(args) == 1:
        jobs[chat_id_str] = []
        save_jobs()
        await reply_in_thread(message, "❌ Все напоминания в этом чате отменены.")
        return
    try:
        rem_id = int(args[1])
        for r in jobs[chat_id_str]:
            if r["id"] == rem_id:
                jobs[chat_id_str].remove(r)
                save_jobs()
                await reply_in_thread(message, f"❌ Напоминание ID {rem_id} отменено.")
                return
        await reply_in_thread(message, f"Напоминание с ID {rem_id} не найдено.")
    except ValueError:
        await reply_in_thread(message, "Укажите корректный ID.")

# ---------- КОМАНДА /set_remind ----------
@app.on_message(filters.command("set_remind") & filters.group)
async def set_remind(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_admin(chat_id, user_id):
        await reply_in_thread(message, "⛔ Только для администраторов.")
        return
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await reply_in_thread(message, "Пример: /set_remind 20:00 daily Текст")
            return
        arg_str = args[1].strip()
        pattern = r'^(\d{1,2}:\d{2})\s+(?:(daily|weekly|\d+)\s+)?(.+)$'
        match = re.match(pattern, arg_str)
        if not match:
            await reply_in_thread(message, "Неверный формат.\nПример: /set_remind 20:00 daily Текст")
            return
        time_str = match.group(1)
        keyword = match.group(2)
        text = match.group(3)

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
                await reply_in_thread(message, "Интервал должен быть > 0.")
                return
            interval = hours * 3600
        else:
            await reply_in_thread(message, "Неизвестное ключевое слово (используйте daily, weekly или число часов).")
            return

        global job_counter
        job_counter += 1
        rem_id = job_counter
        thread_id = message.message_thread_id  # сохраняем тему
        new_job = {
            "id": rem_id,
            "text": text,
            "next_run": scheduled.timestamp(),
            "interval": interval,
            "thread_id": thread_id  # запоминаем, чтобы потом отправлять в ту же тему
        }
        chat_id_str = str(chat_id)
        if chat_id_str not in jobs:
            jobs[chat_id_str] = []
        jobs[chat_id_str].append(new_job)
        save_jobs()

        period = "разовое" if interval is None else ("ежедневно" if interval == 86400 else "еженедельно" if interval == 604800 else f"каждые {interval//3600} ч.")
        await reply_in_thread(
            message,
            f"✅ Напоминание ID {rem_id} установлено.\n"
            f"Первое срабатывание: {scheduled.strftime('%d.%m.%Y %H:%M')} UTC\n"
            f"Тип: {period}\n"
            f"Текст: {text}"
        )
    except Exception as e:
        await reply_in_thread(message, f"Ошибка: {e}")

# ---------- МЕНЮ КОМАНД ----------
async def set_commands():
    commands = [
        BotCommand("all", "Упомянуть всех участников"),
        BotCommand("set_remind", "Установить напоминание"),
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
    print("🚀 Бот запущен. Команды только для админов. Ответы в ту же тему.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
