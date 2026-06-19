import os
import asyncio
import json
import re
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message

# ---------- Конфигурация ----------
API_ID = int(os.getenv("API_ID", 34973373))        # замените на свои
API_HASH = os.getenv("API_HASH", "59def5ad8aa679cff55d76d647174ee8")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8740498225:AAHCGDwtSV4eND-jEnBLNdY1NHNcpNNMzyk")
JOBS_FILE = "jobs.json"

app = Client("reminder_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------- Структура данных ----------
# jobs = { chat_id: { "thread_id": thread_id, "reminds": [ { "id": int, "text": str, "next_run": timestamp, "interval": int (секунды) или None для разового } ] } }
jobs = {}
job_counter = 0  # глобальный счётчик ID

def load_jobs():
    global jobs, job_counter
    try:
        with open(JOBS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            jobs = data.get("jobs", {})
            job_counter = data.get("counter", 0)
    except FileNotFoundError:
        jobs = {}
        job_counter = 0

def save_jobs():
    with open(JOBS_FILE, 'w', encoding='utf-8') as f:
        json.dump({"jobs": jobs, "counter": job_counter}, f, ensure_ascii=False, indent=2)

# ---------- Отправка упоминаний ----------
async def send_reminder(chat_id, text, thread_id=None):
    try:
        users = []
        async for member in app.get_chat_members(chat_id):
            if not member.user.is_bot:
                users.append(member.user)

        if not users:
            await app.send_message(chat_id, "Нет участников для упоминания.", reply_to_message_id=thread_id)
            return

        chunks = []
        chunk_size = 30
        for i in range(0, len(users), chunk_size):
            chunk_users = users[i:i+chunk_size]
            mentions = []
            for user in chunk_users:
                mentions.append(f'<a href="tg://user?id={user.id}">{user.first_name}</a>')
            chunks.append(" ".join(mentions))

        for chunk in chunks:
            msg = f"🔔 {text}\n\n" + chunk
            await app.send_message(
                chat_id,
                msg,
                parse_mode='html',
                reply_to_message_id=thread_id
            )
            await asyncio.sleep(0.5)

        print(f"Упомянуто {len(users)} участников в чате {chat_id}")
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        await app.send_message(chat_id, "Ошибка при отправке упоминаний. Проверьте права бота.")

# ---------- Планировщик ----------
async def scheduler_loop():
    while True:
        now = datetime.now().timestamp()
        for chat_id_str, chat_data in list(jobs.items()):
            chat_id = int(chat_id_str)
            thread_id = chat_data.get("thread_id")
            reminds = chat_data.get("reminds", [])
            for remind in reminds[:]:  # копия для изменения
                if remind["next_run"] <= now:
                    # Отправляем
                    await send_reminder(chat_id, remind["text"], thread_id)
                    # Обновляем время следующего запуска
                    if remind.get("interval") is not None:
                        remind["next_run"] += remind["interval"]
                    else:
                        # Разовое – удаляем
                        reminds.remove(remind)
            # если список пуст, можно удалить запись чата
            if not reminds:
                del jobs[chat_id_str]
        save_jobs()
        await asyncio.sleep(30)  # проверяем каждые 30 секунд

# ---------- Команды ----------
@app.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    await message.reply(
        "👋 Бот для периодических напоминаний с упоминанием всех.\n"
        "Команды:\n"
        " /set_remind HH:MM Текст – разовое\n"
        " /set_remind HH:MM daily Текст – ежедневно\n"
        " /set_remind HH:MM weekly Текст – еженедельно\n"
        " /set_remind HH:MM INTERVAL_ЧАСОВ Текст – повторять через часы\n"
        " /list_reminds – список активных\n"
        " /cancel_remind [ID] – отменить все или по ID\n"
        " /help – эта справка\n\n"
        "⚠️ Бот должен быть администратором группы."
    )

@app.on_message(filters.command("help"))
async def help_handler(client, message: Message):
    await start_handler(client, message)

@app.on_message(filters.command("list_reminds"))
async def list_reminds(client, message: Message):
    chat_id = str(message.chat.id)
    if chat_id not in jobs or not jobs[chat_id]["reminds"]:
        await message.reply("Нет активных напоминаний в этом чате.")
        return
    text = "📋 Активные напоминания:\n"
    for r in jobs[chat_id]["reminds"]:
        dt = datetime.fromtimestamp(r["next_run"]).strftime("%d.%m.%Y %H:%M")
        interval = r.get("interval")
        if interval:
            if interval == 86400:
                period = "ежедневно"
            elif interval == 604800:
                period = "еженедельно"
            else:
                hours = interval // 3600
                period = f"каждые {hours} ч."
        else:
            period = "разовое"
        text += f"ID {r['id']}: {dt} ({period}) – {r['text'][:30]}...\n"
    await message.reply(text)

@app.on_message(filters.command("cancel_remind"))
async def cancel_remind(client, message: Message):
    chat_id = str(message.chat.id)
    if chat_id not in jobs:
        await message.reply("Нет активных напоминаний.")
        return

    args = message.text.split()
    if len(args) == 1:
        # отменить все
        jobs[chat_id]["reminds"] = []
        del jobs[chat_id]
        save_jobs()
        await message.reply("❌ Все напоминания в этом чате отменены.")
        return

    # отменить по ID
    try:
        rem_id = int(args[1])
        reminds = jobs[chat_id]["reminds"]
        for r in reminds:
            if r["id"] == rem_id:
                reminds.remove(r)
                if not reminds:
                    del jobs[chat_id]
                save_jobs()
                await message.reply(f"❌ Напоминание ID {rem_id} отменено.")
                return
        await message.reply(f"Напоминание с ID {rem_id} не найдено.")
    except ValueError:
        await message.reply("Укажите корректный ID или ничего для отмены всех.")

@app.on_message(filters.command("set_remind"))
async def set_remind(client, message: Message):
    try:
        chat_id = str(message.chat.id)
        thread_id = message.reply_to_message.id if message.reply_to_message else None
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Пример: /set_remind 20:00 daily Текст")
            return

        parts = args[1].split(maxsplit=2)
        if len(parts) < 2:
            await message.reply("Неверный формат. Нужно: время и текст (и возможно ключевое слово daily/weekly/часы).")
            return

        time_str = parts[0]
        # Проверяем, есть ли ключевое слово во второй части
        rest = parts[1]
        keyword = None
        text = None
        # если после времени идёт ключевое слово (daily, weekly или число)
        # пытаемся разобрать
        words = rest.split()
        if words and words[0].lower() in ("daily", "weekly"):
            keyword = words[0].lower()
            text = " ".join(words[1:]) if len(words) > 1 else ""
        else:
            # возможно, это число часов и текст
            if re.match(r'^\d+$', words[0]):
                keyword = words[0]  # число часов
                text = " ".join(words[1:]) if len(words) > 1 else ""
            else:
                # значит, это просто текст без ключевого слова (разовое)
                text = rest

        if not text:
            await message.reply("Укажите текст напоминания.")
            return

        # парсим время
        try:
            remind_time = datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await message.reply("Неверный формат времени. Используйте HH:MM (например, 20:00).")
            return

        now = datetime.now()
        # дата сегодня, но время может быть уже прошло, тогда на завтра
        scheduled = datetime(now.year, now.month, now.day, remind_time.hour, remind_time.minute)
        if scheduled < now:
            scheduled += timedelta(days=1)

        # определяем интервал
        interval = None
        if keyword is None:
            # разовое
            pass
        elif keyword == "daily":
            interval = 86400  # 24 часа
        elif keyword == "weekly":
            interval = 604800  # 7 дней
        elif keyword.isdigit():
            hours = int(keyword)
            if hours <= 0:
                await message.reply("Интервал должен быть больше 0 часов.")
                return
            interval = hours * 3600
            # первое срабатывание в указанное время
        else:
            await message.reply("Неизвестное ключевое слово. Используйте daily, weekly или число часов.")
            return

        # Создаём напоминание
        global job_counter
        job_counter += 1
        rem_id = job_counter
        new_job = {
            "id": rem_id,
            "text": text,
            "next_run": scheduled.timestamp(),
            "interval": interval
        }

        if chat_id not in jobs:
            jobs[chat_id] = {"thread_id": thread_id, "reminds": []}
        else:
            jobs[chat_id]["thread_id"] = thread_id
        jobs[chat_id]["reminds"].append(new_job)
        save_jobs()

        period = "разовое" if interval is None else f"повторяющееся каждые {interval//3600} ч." if interval < 86400 else "ежедневно" if interval == 86400 else "еженедельно"
        await message.reply(
            f"✅ Напоминание ID {rem_id} установлено.\n"
            f"Первое срабатывание: {scheduled.strftime('%d.%m.%Y %H:%M')}\n"
            f"Тип: {period}\n"
            f"Текст: {text}"
        )
    except Exception as e:
        print(f"Ошибка set_remind: {e}")
        await message.reply("Произошла ошибка. Проверьте формат команды.")

# ---------- Запуск планировщика и бота ----------
async def main():
    load_jobs()
    # запускаем фоновую задачу планировщика
    asyncio.create_task(scheduler_loop())
    print("Бот запущен. Планировщик активен.")
    await app.start()
    await app.idle()

if __name__ == "__main__":
    app.run(main())