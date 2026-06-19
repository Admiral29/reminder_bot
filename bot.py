from pyrogram import Client, filters
from pyrogram.enums import ParseMode
import os
import asyncio
import json
import re
from datetime import datetime, timedelta

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("mention_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------- ОТЛАДКА: все команды ----------
@app.on_message(filters.command("all") & filters.group)
async def mention_all(client, message):
    await message.reply("✅ Команда /all получена! Обрабатываю...")
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

# ---------- КОМАНДА /start (помощь) ----------
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
        "/cancel_remind [ID] – отменить все или по ID"
    )

# ---------- КОМАНДА /set_remind ----------
@app.on_message(filters.command("set_remind") & filters.group)
async def set_remind(client, message):
    await message.reply("✅ Команда /set_remind получена! Разбираю...")
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Пример: /set_remind 20:00 daily Текст")
            return
        arg_str = args[1].strip()
        pattern = r'^(\d{1,2}:\d{2})\s+(?:(daily|weekly|\d+)\s+)?(.+)$'
        match = re.match(pattern, arg_str)
        if not match:
            await message.reply("Неверный формат. Нужно: /set_remind 20:00 daily Текст")
            return
        time_str, keyword, text = match.group(1), match.group(2), match.group(3)
        remind_time = datetime.strptime(time_str, "%H:%M")
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
                await message.reply("Интервал должен быть > 0.")
                return
            interval = hours * 3600
        else:
            await message.reply("Неизвестное ключевое слово.")
            return
        # Сохраняем задание (пока просто в памяти, но вы можете добавить сохранение)
        await message.reply(
            f"✅ Напоминание установлено на {scheduled.strftime('%d.%m.%Y %H:%M')}\n"
            f"Тип: {'разовое' if interval is None else 'ежедневно' if interval == 86400 else 'еженедельно' if interval == 604800 else f'каждые {interval//3600} ч.'}\n"
            f"Текст: {text}"
        )
    except Exception as e:
        await message.reply(f"Ошибка: {e}")

# ---------- КОМАНДА /list_reminds (заглушка) ----------
@app.on_message(filters.command("list_reminds") & filters.group)
async def list_reminds(client, message):
    await message.reply("✅ Команда /list_reminds получена! Список пока пуст (задания не сохраняются в этой версии).")

# ---------- КОМАНДА /cancel_remind (заглушка) ----------
@app.on_message(filters.command("cancel_remind") & filters.group)
async def cancel_remind(client, message):
    await message.reply("✅ Команда /cancel_remind получена! Отмена пока не реализована.")

print("🚀 Бот запущен (отладочная версия).")
app.run()
