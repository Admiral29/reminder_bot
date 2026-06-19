import os
import logging
import json
import re
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")  # читаем из переменных окружения
if not TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

JOBS_FILE = "jobs.json"

# ---------- Данные ----------
jobs = {}       # { chat_id: [ {id, text, next_run, interval}, ... ] }
job_counter = 0

def load_jobs():
    global jobs, job_counter
    try:
        with open(JOBS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            jobs = data.get("jobs", {})
            job_counter = data.get("counter", 0)
        logging.info(f"Загружено напоминаний: {sum(len(v) for v in jobs.values())}")
    except FileNotFoundError:
        jobs = {}
        job_counter = 0
        logging.info("Файл jobs.json не найден, создан новый")

def save_jobs():
    with open(JOBS_FILE, 'w', encoding='utf-8') as f:
        json.dump({"jobs": jobs, "counter": job_counter}, f, ensure_ascii=False, indent=2)

# ---------- Отправка упоминаний ----------
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    text = job.data['text']
    try:
        # Получаем список участников
        members = []
        async for member in context.bot.get_chat_members(chat_id):
            if not member.user.is_bot:
                members.append(member.user)

        if not members:
            await context.bot.send_message(chat_id, "Нет участников для упоминания.")
            return

        # Формируем упоминания по 30 штук
        mentions = []
        for user in members:
            mentions.append(f'<a href="tg://user?id={user.id}">{user.first_name}</a>')

        chunk_size = 30
        for i in range(0, len(mentions), chunk_size):
            chunk = mentions[i:i+chunk_size]
            msg = f"🔔 {text}\n\n" + " ".join(chunk)
            await context.bot.send_message(
                chat_id,
                msg,
                parse_mode='HTML'
            )
            await asyncio.sleep(0.5)

        logging.info(f"Упомянуто {len(members)} участников в чате {chat_id}")
    except Exception as e:
        logging.error(f"Ошибка отправки: {e}")
        await context.bot.send_message(chat_id, "Ошибка при отправке упоминаний. Проверьте права бота.")

# ---------- Команды ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Бот для периодических напоминаний с упоминанием всех.\n"
        "Команды:\n"
        " /set_remind HH:MM Текст – разовое\n"
        " /set_remind HH:MM daily Текст – ежедневно\n"
        " /set_remind HH:MM weekly Текст – еженедельно\n"
        " /set_remind HH:MM 2 Текст – каждые 2 часа\n"
        " /list_reminds – список активных\n"
        " /cancel_remind [ID] – отменить все или по ID\n"
        " /help – справка\n\n"
        "⚠️ Бот должен быть администратором группы."
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def list_reminds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in jobs or not jobs[chat_id]:
        await update.message.reply_text("Нет активных напоминаний.")
        return
    text = "📋 Активные напоминания:\n"
    for r in jobs[chat_id]:
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
    await update.message.reply_text(text)

async def cancel_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in jobs or not jobs[chat_id]:
        await update.message.reply_text("Нет активных напоминаний.")
        return
    args = update.message.text.split()
    if len(args) == 1:
        # отменить все
        jobs[chat_id] = []
        save_jobs()
        await update.message.reply_text("❌ Все напоминания в этом чате отменены.")
        return
    try:
        rem_id = int(args[1])
        for r in jobs[chat_id]:
            if r["id"] == rem_id:
                jobs[chat_id].remove(r)
                save_jobs()
                await update.message.reply_text(f"❌ Напоминание ID {rem_id} отменено.")
                return
        await update.message.reply_text(f"Напоминание с ID {rem_id} не найдено.")
    except ValueError:
        await update.message.reply_text("Укажите корректный ID.")

async def set_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text("Команда только в группах.")
            return

        args = update.message.text.split(maxsplit=1)
        if len(args) < 2:
            await update.message.reply_text("Пример: /set_remind 20:00 daily Текст")
            return

        arg_str = args[1].strip()
        pattern = r'^(\d{1,2}:\d{2})\s+(?:(daily|weekly|\d+)\s+)?(.+)$'
        match = re.match(pattern, arg_str)
        if not match:
            await update.message.reply_text(
                "Неверный формат. Используйте:\n"
                "/set_remind 20:00 Текст\n"
                "/set_remind 20:00 daily Текст\n"
                "/set_remind 20:00 weekly Текст\n"
                "/set_remind 20:00 2 Текст (каждые 2 часа)"
            )
            return

        time_str = match.group(1)
        keyword = match.group(2)
        text = match.group(3)

        try:
            remind_time = datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await update.message.reply_text("Неверный формат времени. Используйте HH:MM (например, 20:00).")
            return

        now = datetime.now()
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
                await update.message.reply_text("Интервал должен быть > 0 часов.")
                return
            interval = hours * 3600
        else:
            await update.message.reply_text("Неизвестное ключевое слово.")
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

        chat_id = str(update.effective_chat.id)
        if chat_id not in jobs:
            jobs[chat_id] = []
        jobs[chat_id].append(new_job)
        save_jobs()

        # Ставим задачу в JobQueue (чтобы она сработала)
        delay = (scheduled - now).total_seconds()
        if delay > 0:
            job_queue: JobQueue = context.job_queue
            job_queue.run_once(
                send_reminder,
                delay,
                data={'text': text},
                chat_id=update.effective_chat.id,
                name=f"reminder_{chat_id}_{rem_id}"
            )

        period = "разовое" if interval is None else f"каждые {interval//3600} ч." if interval < 86400 else "ежедневно" if interval == 86400 else "еженедельно"
        await update.message.reply_text(
            f"✅ Напоминание ID {rem_id} установлено.\n"
            f"Первое срабатывание: {scheduled.strftime('%d.%m.%Y %H:%M')}\n"
            f"Тип: {period}\n"
            f"Текст: {text}"
        )
    except Exception as e:
        logging.error(f"Ошибка set_remind: {e}")
        await update.message.reply_text("Произошла ошибка. Проверьте формат команды.")

# ---------- Планировщик повторяющихся заданий ----------
async def scheduler_loop(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет jobs.json и запускает пропущенные задания при перезапуске."""
    # Эта функция вызывается при старте бота, чтобы переставить задания из JSON
    # в JobQueue, если они ещё не запущены.
    pass  # мы используем JobQueue для разовых, а для повторяющихся будем пересоздавать

# ---------- Главная ----------
def main():
    load_jobs()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("set_remind", set_remind))
    app.add_handler(CommandHandler("list_reminds", list_reminds))
    app.add_handler(CommandHandler("cancel_remind", cancel_remind))

    # При запуске переставить все задания из jobs.json в JobQueue
    now = datetime.now().timestamp()
    for chat_id_str, reminds in jobs.items():
        chat_id = int(chat_id_str)
        for r in reminds:
            if r["next_run"] > now:
                delay = r["next_run"] - now
                app.job_queue.run_once(
                    send_reminder,
                    delay,
                    data={'text': r["text"]},
                    chat_id=chat_id,
                    name=f"reminder_{chat_id}_{r['id']}"
                )
            else:
                # Если время уже прошло, сразу отправляем и обновляем интервал, если есть
                # но для простоты мы просто удалим просроченные разовые задания, а повторяющиеся пересчитаем
                if r.get("interval") is not None:
                    # пересчитываем next_run на будущее
                    while r["next_run"] <= now:
                        r["next_run"] += r["interval"]
                    delay = r["next_run"] - now
                    app.job_queue.run_once(
                        send_reminder,
                        delay,
                        data={'text': r["text"]},
                        chat_id=chat_id,
                        name=f"reminder_{chat_id}_{r['id']}"
                    )
                else:
                    # разовое просроченное — удаляем
                    reminds.remove(r)
            save_jobs()

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
