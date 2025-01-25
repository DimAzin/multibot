import telebot
from PIL import Image, ImageOps
import io
from telebot import types
import os

# Получение токена
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN is not set in environment variables.")

bot = telebot.TeleBot(TOKEN)
bot.remove_webhook()
user_states = {}  # Хранение данных пользователя

DEFAULT_ASCII_CHARS = '@%#*+=-:. '

# Функция для создания негатива изображения
def invert_colors(image):
    """
    Инвертирует цвета изображения, создавая эффект негатива.
    """
    if image.mode == 'RGBA':
        r, g, b, a = image.split()
        rgb_image = Image.merge("RGB", (r, g, b))
        inverted_image = ImageOps.invert(rgb_image)
        r, g, b = inverted_image.split()
        return Image.merge("RGBA", (r, g, b, a))
    elif image.mode == 'RGB':
        return ImageOps.invert(image)
    else:
        raise ValueError("Unsupported image mode for inversion")

def pixelate_image(image, pixel_size):
    """
    Уменьшает разрешение изображения, а затем увеличивает обратно для эффекта пикселизации.
    """
    image = image.resize(
        (image.size[0] // pixel_size, image.size[1] // pixel_size),
        Image.NEAREST  # Используем ближайшего соседа для увеличения
    )
    image = image.resize(
        (image.size[0] * pixel_size, image.size[1] * pixel_size),
        Image.NEAREST
    )
    return image

def resize_image(image, new_width=100):
    width, height = image.size
    ratio = height / width
    new_height = int(new_width * ratio)
    return image.resize((new_width, new_height))

def image_to_ascii(image_stream, ascii_chars, new_width=40):
    image = Image.open(image_stream).convert('L')
    width, height = image.size
    aspect_ratio = height / float(width)
    new_height = int(aspect_ratio * new_width * 0.55)
    img_resized = image.resize((new_width, new_height))

    pixels = img_resized.getdata()
    characters = "".join(
        ascii_chars[pixel * len(ascii_chars) // 256] for pixel in pixels
    )

    img_width = img_resized.width
    max_characters = 4000 - (new_width + 1)
    max_rows = max_characters // (new_width + 1)

    ascii_art = ""
    for i in range(0, min(max_rows * img_width, len(characters)), img_width):
        ascii_art += characters[i:i + img_width] + "\n"

    return ascii_art

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Send me an image, and I'll provide options for you!")


#Обработчик для инверсии цветов
@bot.callback_query_handler(func=lambda call: call.data == "invert_colors")
def invert_colors_and_send(call):
    try:
        bot.answer_callback_query(call.id, "Inverting colors of your image...")
        chat_id = call.message.chat.id
        photo_id = user_states[chat_id]['photo']
        file_info = bot.get_file(photo_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Работаем с изображением
        image_stream = io.BytesIO(downloaded_file)
        image = Image.open(image_stream)
        inverted_image = invert_colors(image)

        # Сохраняем результат в поток и отправляем пользователю
        output_stream = io.BytesIO()
        inverted_image.save(output_stream, format="JPEG")
        output_stream.seek(0)
        bot.send_photo(chat_id, output_stream)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Error during color inversion: {e}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        bot.reply_to(message, "I got your photo! Please choose what you'd like to do with it.",
                     reply_markup=get_options_keyboard())
        file_id = message.photo[-1].file_id
        user_states[message.chat.id] = {'photo': file_id}
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def get_options_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    pixelate_btn = types.InlineKeyboardButton("Pixelate", callback_data="pixelate")
    ascii_btn = types.InlineKeyboardButton("ASCII Art", callback_data="ascii")
    invert_btn = types.InlineKeyboardButton("Invert Colors", callback_data="invert_colors")  # Новая кнопка
    keyboard.add(pixelate_btn, ascii_btn, invert_btn)
    return keyboard

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    try:
        if call.data == "pixelate":
            bot.answer_callback_query(call.id, "Pixelating your image...")
            pixelate_and_send(call.message.chat.id)
        elif call.data == "ascii":
            bot.answer_callback_query(call.id, "Please send the characters you want to use for the ASCII art.")
            user_states[call.message.chat.id]['awaiting_chars'] = True
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Error: {e}")

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('awaiting_chars', False))
def handle_custom_chars(message):
    try:
        custom_chars = message.text.strip()
        if not custom_chars:
            bot.reply_to(message, "You provided an empty set of characters. Using default set.")
            custom_chars = DEFAULT_ASCII_CHARS

        user_states[message.chat.id]['ascii_chars'] = custom_chars
        bot.reply_to(message, "Characters received. Converting your image to ASCII art...")
        ascii_and_send(message.chat.id)
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}")

def pixelate_and_send(chat_id):
    try:
        photo_id = user_states[chat_id]['photo']
        file_info = bot.get_file(photo_id)
        downloaded_file = bot.download_file(file_info.file_path)

        image_stream = io.BytesIO(downloaded_file)
        image = Image.open(image_stream)
        pixelated = pixelate_image(image, 20)

        output_stream = io.BytesIO()
        pixelated.save(output_stream, format="JPEG")
        output_stream.seek(0)
        bot.send_photo(chat_id, output_stream)
    except Exception as e:
        bot.send_message(chat_id, f"Error during pixelation: {e}")

def ascii_and_send(chat_id):
    try:
        photo_id = user_states[chat_id]['photo']
        ascii_chars = user_states[chat_id].get('ascii_chars', DEFAULT_ASCII_CHARS)

        file_info = bot.get_file(photo_id)
        downloaded_file = bot.download_file(file_info.file_path)

        image_stream = io.BytesIO(downloaded_file)
        ascii_art = image_to_ascii(image_stream, ascii_chars)

        ascii_art = ascii_art.replace("`", "'")  # Заменяем конфликтные символы
        bot.send_message(chat_id, f"```\n{ascii_art}\n```", parse_mode="MarkdownV2")

        # Убираем статус ожидания набора символов
        user_states[chat_id].pop('awaiting_chars', None)
    except Exception as e:
        bot.send_message(chat_id, f"Error during ASCII conversion: {e}")

bot.polling(none_stop=True)
