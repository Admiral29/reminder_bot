from pyrogram import Client, filters

API_ID = 34973373  # ваш api_id
API_HASH = "59def5ad8aa679cff55d76d647174ee8"
BOT_TOKEN = "8740498225:AAE1flLUqQGC0WdZZvPnjHcjR2R0VbggCgQ"

app = Client("mention_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("all") & filters.group)
async def mention_all(client, message):
    chat_id = message.chat.id
    try:
        # Получаем всех участников (не ботов)
        users = []
        async for member in app.get_chat_members(chat_id):
            if not member.user.is_bot:
                users.append(member.user)
        if not users:
            await message.reply("Нет участников.")
            return
        # Формируем упоминания
        mentions = []
        for user in users:
            if user.username:
                mentions.append(f"@{user.username}")
            else:
                mentions.append(f'<a href="tg://user?id={user.id}">{user.first_name}</a>')
        # Отправляем по частям
        chunk_size = 50
        for i in range(0, len(mentions), chunk_size):
            chunk = mentions[i:i+chunk_size]
            msg = "📢 Всем привет!\n\n" + " ".join(chunk)
            await app.send_message(chat_id, msg, parse_mode="html")
    except Exception as e:
        await message.reply(f"Ошибка: {e}\nПроверьте, что я администратор.")

print("Бот запущен (Pyrogram).")
app.run()
