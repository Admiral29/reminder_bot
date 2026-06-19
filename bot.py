from pyrogram import Client, filters
import os

# ---------- КОНФИГУРАЦИЯ (читаем из переменных окружения) ----------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("mention_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("all") & filters.group)
async def mention_all(client, message):
    chat_id = message.chat.id
    try:
        users = []
        async for member in app.get_chat_members(chat_id):
            if not member.user.is_bot:
                users.append(member.user)
        if not users:
            await message.reply("Нет участников для упоминания.")
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
            await app.send_message(chat_id, msg, parse_mode="html")
    except Exception as e:
        await message.reply(f"Ошибка: {e}\nПроверьте, что я администратор.")

print("Бот запущен и готов к работе!")
app.run()
