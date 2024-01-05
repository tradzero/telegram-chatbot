import asyncio
from asyncio import Queue
import telegram
from dotenv import load_dotenv
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters,ApplicationHandlerStop
from telegram.helpers import escape_markdown
from openai import OpenAI
import time

load_dotenv()

greeting_message = os.getenv('GREETING_MESSAGE')
system_prompt = os.getenv('SYSTEM_PROMPT')
bot_user_name = os.getenv('BOT_USER_NAME')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=greeting_message)
    
async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    SPECIAL_USERS = os.getenv('SPECIAL_USERS').split(',')
    if str(update.effective_chat.id) not in SPECIAL_USERS:
        await update.effective_message.reply_text("you shall not pass")
        raise ApplicationHandlerStop
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=telegram.constants.ChatAction.TYPING)
    user_message = update.message.text

    ai_response = get_chatgpt_response(user_message)

    is_end = False
    ai_response_text = ''
    time_start=time.time()
    time_duration = 1.5

    queue = Queue()

    consumer = asyncio.create_task(handle_messages(queue, context, update))

    for chunk in ai_response:
        ai_chunk = chunk.choices[0].delta.content
        finish_reason = chunk.choices[0].finish_reason
        if (ai_chunk == None or finish_reason == 'stop'):
            is_end = True
            queue.put_nowait((ai_response_text, is_end))
            break
        ai_response_text += ai_chunk

        if (time.time() - time_start > time_duration):
            time_start = time.time()
            queue.put_nowait((ai_response_text, is_end))
    

async def handle_messages(queue, context, update):
    message_id = update.message.message_id
    last_message_id = message_id
    chat_id = update.effective_chat.id
    message = None

    while True:
        # 从队列获取消息
        ai_response_text, is_end = await queue.get()
        # 发送或编辑消息
        if message_id != last_message_id:
            message = await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=last_message_id,
                text=escape_markdown(ai_response_text, 2),
                parse_mode=telegram.constants.ParseMode.MARKDOWN_V2,
            )
            last_message_id = message.message_id
        else:
            message = await context.bot.send_message(
                chat_id=chat_id, 
                text=escape_markdown(ai_response_text, 2),
                parse_mode=telegram.constants.ParseMode.MARKDOWN_V2,
                reply_to_message_id=message_id,
                allow_sending_without_reply=True
            )
            last_message_id = message.message_id
        if is_end:
            print('trigger break')
            queue.task_done()
            break
        queue.task_done()

def get_chatgpt_response(question):
    openai_key = os.getenv('OPENAI_API_KEY')
    model = os.getenv('OPENAI_CHATBOT_MODEL')
    client = OpenAI(api_key=openai_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": question
            }
        ],
        temperature=0.5,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stream=True
    )
    return response

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)


if __name__ == '__main__':
    telegram_bot_token = os.getenv('TELEGRAM_BOT')
    application = ApplicationBuilder().token(telegram_bot_token).build()

    group_mention_handler = MessageHandler(filters.Mention(bot_user_name), answer)
    start_handler = CommandHandler('start', start)

    application.add_handler(start_handler)
    application.add_handler(group_mention_handler)
    application.run_polling()