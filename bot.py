import os
import asyncio
import re
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message

# Читаем переменные окружения
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client(
    "reminder_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

scheduled_tasks = {}

async def send_reminder(chat_id, text, reply_to_message_id=None):
    try:
        users = []
        async for member in app.get_chat_members(chat_id):
            if not member.user.is_bot:
                users.append(member.user)

        if not users:
            await app.send_message(chat_id, "Нет участников для упоминания.")
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
                reply_to_message_id=reply_to_message_id
            )
            await asyncio.sleep(0.5)

        print(f"Упомянуто {len(users)} участников в чате {chat_id}")

    except Exception as e:
        print(f"Ошибка: {e}")
        await app.send_message(chat_id, "Ошибка. Проверьте права бота.")

@app.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    await message.reply(
        "👋 Бот для напоминаний.\n"
        "/remind 20:00 Текст\n"
        "/remind 20:00 25.12.2025 Текст\n"
        "/cancel – отменить все\n"
        "/help – справка"
    )

@app.on_message(filters.command("help"))
async def help_handler(client, message: Message):
    await start_handler(client, message)

@app.on_message(filters.command("cancel"))
async def cancel_handler(client, message: Message):
    chat_id = message.chat.id
    key = str(chat_id)
    if key in scheduled_tasks and scheduled_tasks[key]:
        count = 0
        for task in scheduled_tasks[key]:
            task.cancel()
            count += 1
        scheduled_tasks[key] = []
        await message.reply(f"❌ Отменено {count} напоминаний.")
    else:
        await message.reply("Нет запланированных напоминаний.")

@app.on_message(filters.command("remind"))
async def remind_handler(client, message: Message):
    try:
      

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Пример: /remind 20:00 Текст")
            return

        arg_str = args[1].strip()
        pattern1 = r'^(\d{1,2}:\d{2})\s+(.+)$'
        pattern2 = r'^(\d{1,2}:\d{2})\s+(\d{2}\.\d{2}\.\d{4})\s+(.+)$'
        match1 = re.match(pattern1, arg_str)
        match2 = re.match(pattern2, arg_str)

        if match1:
            time_str, text = match1.group(1), match1.group(2)
            today = datetime.now().strftime('%d.%m.%Y')
            remind_dt = datetime.strptime(f"{today} {time_str}", '%d.%m.%Y %H:%M')
            if remind_dt < datetime.now():
                remind_dt += timedelta(days=1)
        elif match2:
            time_str, date_str, text = match2.group(1), match2.group(2), match2.group(3)
            remind_dt = datetime.strptime(f"{date_str} {time_str}", '%d.%m.%Y %H:%M')
            if remind_dt < datetime.now():
                await message.reply("Дата уже прошла.")
                return
        else:
            await message.reply("Неверный формат.")
            return

        delay = (remind_dt - datetime.now()).total_seconds()
        if delay <= 0:
            await message.reply("Время уже прошло.")
            return

        chat_id = message.chat.id
        reply_to_id = message.reply_to_message.id if message.reply_to_message else None

        async def task():
            await asyncio.sleep(delay)
            await send_reminder(chat_id, text, reply_to_id)

        task_obj = asyncio.create_task(task())
        key = str(chat_id)
        scheduled_tasks.setdefault(key, []).append(task_obj)

        await message.reply(
            f"✅ Напоминание на {remind_dt.strftime('%d.%m.%Y %H:%M')}\nТекст: {text}"
        )

    except Exception as e:
        print(f"Ошибка: {e}")
        await message.reply("Ошибка. Проверьте формат.")

print("Бот запускается...")
app.run()
