import io
import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, \
    CallbackQueryHandler, ContextTypes
import sqlite3
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random


# Функция для подключения к базе данных SQLite
def create_connection():
    return sqlite3.connect('PATH')


# Проверки на дурака
def is_valid_username(username: str) -> bool:
    return 3 <= len(username) <= 20 and re.match(r'^[a-zA-Z0-9_]+$', username)


def is_valid_password(password: str) -> bool:
    return (6 <= len(password) <= 20 and
            re.search(r'[A-Z]', password) and  # хотя бы одна заглавная буква
            re.search(r'[0-9]', password) and  # хотя бы одна цифра
            re.search(r'[!@#$%^&*(),.?":{}|<>]', password))  # хотя бы один специальный символ


def is_valid_email(email: str) -> bool:
    return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None


def is_valid_phone(phone: str) -> bool:
    # Регулярное выражение для проверки номера телефона: ровно 11 цифр, опционально с символом '+'
    return re.match(r'^\+?\d{11}$', phone) is not None


# Функция для отправки приветственного письма
def send_welcome_email(to_email: str, username: str) -> None:
    from_email = 'login'  # Замените на ваш email
    from_password = 'password'  # Замените на ваш пароль

    body = (
        "Добро пожаловать в KorZap!\n\n"
        "Ваш надежный помощник в мире автозапчастей для корейских и китайских автомобилей.\n\n"
        "Почему выбирают нас?\n"
        "• Мы на рынке с 2015 года.\n"
        "• Продано более 300 тысяч автозапчастей.\n"
        "• Широкий ассортимент и конкурентоспособные цены.\n\n"
        "В KorZap мы понимаем, как важна для вас каждая деталь:\n"
        "• Только лучшие запчасти от надежных производителей.\n"
        "• Безопасность и комфорт ваших поездок.\n"
        "• Профессиональная помощь в выборе деталей.\n\n"
        "Пусть ваш автомобиль работает без перебоев с KorZap! Мы стремимся к вашему удовлетворению и всегда готовы предложить вам лучшее. "
        "Позвольте нам стать вашим надежным партнером на пути к качественному обслуживанию вашего автомобиля!"
    )
    subject = f"Здравствуйте, {username}!\n\nСпасибо за регистрацию в нашем боте. Мы рады вас видеть!"

    # Создаем сообщение
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Отправка письма
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()  # Устанавливаем защищенное соединение
            server.login(from_email, from_password)  # Логин в email
            server.send_message(msg)  # Отправка письма
            print("Письмо успешно отправлено!")
    except Exception as e:
        print(f"Ошибка при отправке email: {e}")


def generate_confirmation_code():
    return ''.join(random.choices('0123456789', k=6))


def send_confirmation_email(email, code):
    msg = MIMEText(f"Ваш код подтверждения: {code}")
    msg['Subject'] = 'Подтверждение регистрации'
    msg['From'] = 'telmanmessi@gmail.com'
    msg['To'] = email

    # Настройте параметры SMTP-сервера
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login('login', 'password')
    server.send_message(msg)
    server.quit()


# Функция для проверки наличия почты в базе данных
def check_email_in_database(email):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Customer WHERE Email = ?', (email,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


# Функция для обновления пароля в базе данных
def update_password_in_database(email, new_password):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE User SET Password = ? WHERE Login = (SELECT Login FROM Customer WHERE Email = ?)',
                   (new_password, email))
    conn.commit()
    conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    # Проверка на наличие данных о пользователе
    if 'role' in context.user_data:
        user_data = context.user_data
        if user_data.get('role') == 'customer':
            await show_customer_dashboard(update, context, user_data.get('username'))
    else:
        # Если данных нет (пользователь не авторизован), показываем стартовое меню
        keyboard = [
            [InlineKeyboardButton("Вход", callback_data='sign_in')],
            [InlineKeyboardButton("Регистрация", callback_data='reg_in')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "👋 Добро пожаловать! Пожалуйста, выберите один из вариантов ниже для продолжения:",
            reply_markup=reply_markup
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Сохраняем последнюю выбранную команду для последующих действий
    if query.data == "sign_in":
        context.user_data['last_action'] = "sign_in"
        await prompt_sign_in(update, context)
    elif query.data == "reg_in":
        context.user_data['last_action'] = "reg_in"
        await prompt_registration(update, context)
    elif query.data == "reset_password":
        context.user_data['last_action'] = "reset_password"
        await query.message.edit_text("📝 Пожалуйста, введите вашу почту для отправки кода подтверждения:")
    elif query.data == "products":
        await show_categories(update, context)  # Отображаем список товаров
    elif query.data.startswith("category_"):
        await show_products(update, context)
    # Проверяем, если это запрос на товар
    elif query.data.startswith("product_"):
        print(query.data)
        product_id = int(query.data.split("_")[1])
        await show_product_details(update, context, product_id)
    # Логика добавления в корзину
    elif query.data.startswith("add_to_cart_"):
        product_id = int(query.data.split("_")[3])
        await add_to_cart(update, context, product_id)
    elif query.data.startswith("confirm_payment_"):
        await confirm_payment(update, context)
    elif query.data == "order_history":
        await history_order(update, context)

    # Условная логика возврата
    elif query.data == "profile":
        await show_customer_dashboard(update, context, context.user_data.get("username", "Пользователь"))
    elif query.data == "logout":
        await handle_logout(update, context)
    elif query.data == "cart":
        await show_cart(update, context)  # Показ корзины
    elif query.data == "checkout":
        await checkout(update, context)  # Оформление заказа
    elif query.data == "products":
        await show_categories(update, context)
    elif query.data.startswith("car_"):
        await show_products(update, context)


# Функция запроса на регистрацию
async def prompt_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    registration_message = (
        "📝 *Регистрация нового пользователя*\n\n"
        "Пожалуйста, введите ваши данные в следующем формате:\n"
        "`имя_пользователя пароль имя телефон почта`\n\n"
        "_Пример: johndoe 123456 Иванов +79991234567 ivanov@example.com_"
    )
    await update.callback_query.message.edit_text(registration_message, parse_mode='Markdown')


# Функция запроса на вход
async def prompt_sign_in(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Обработка callback_query
    await update.callback_query.answer()  # Подтверждение нажатия кнопки

    # Определите клавиатуру с кнопкой для сброса
    reset_keyboard = [
        [InlineKeyboardButton("Забыли пароль?", callback_data='reset_password')]
    ]
    reply_markup_reset = InlineKeyboardMarkup(reset_keyboard)

    sign_in_message = (
        "🔑 *Вход в систему*\n\n"
        "Введите ваше имя пользователя и пароль в формате:\n"
        "`имя_пользователя пароль`\n\n"
        "_Пример: johndoe 123456_"
    )

    await update.callback_query.message.edit_text(sign_in_message, reply_markup=reply_markup_reset,
                                                  parse_mode='Markdown')


# Обработчик сообщений, который выполняет регистрацию или авторизацию
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Определите клавиатуру с кнопками
    keyboard = [
        [InlineKeyboardButton("Вход", callback_data='sign_in')],
        [InlineKeyboardButton("Регистрация", callback_data='reg_in')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = update.message.text
    parts = text.split()

    conn = create_connection()
    cursor = conn.cursor()

    try:
        user_data = context.user_data.get('last_action', None)

        if user_data == "sign_in":
            if len(parts) != 2:
                await update.message.reply_text(
                    "⚠️ *Ошибка формата ввода*\n\n"
                    "Пожалуйста, используйте следующий формат для ввода:\n"
                    "`имя_пользователя пароль`\n\n"
                    "Попробуйте еще раз."
                    , parse_mode='Markdown')
                return

            username, password = parts
            cursor.execute('SELECT * FROM User WHERE Login = ?', (username,))
            user = cursor.fetchone()

            if user:
                if user[2] == password:
                    role = user[3]  # Получаем роль из базы данных
                    context.user_data['role'] = role  # Сохраняем роль пользователя
                    context.user_data['username'] = username  # Сохраняем имя пользователя
                    await update.message.reply_text(
                        "✅ *Успешный вход!*\n\n"
                        , parse_mode='Markdown')
                    if role == 'customer':
                        await show_customer_dashboard(update, context, username)
                    else:
                        await update.message.reply_text("Неизвестная роль пользователя.")

                else:
                    await update.message.reply_text(
                        "❌ *Неправильный пароль*\n\n"
                        "Пожалуйста, попробуйте снова или сбросьте пароль, если забыли.",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
            else:
                await update.message.reply_text(
                    "❌ *Пользователь не найден*\n\n"
                    "Мы не смогли найти учетную запись с таким именем. "
                    "Пожалуйста, зарегистрируйтесь или попробуйте снова.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown')

        elif user_data == "reg_in":
            if len(parts) != 5:
                await update.message.reply_text(
                    "⚠️ *Ошибка формата ввода*\n\n"
                    "Пожалуйста, используйте следующий формат для ввода:\n"
                    "`имя_пользователя пароль имя телефон почта`\n\n"
                    "Попробуйте еще раз."
                    , parse_mode='Markdown')
                return

            username, password, name, phone, email = parts

            if not is_valid_username(username):
                await update.message.reply_text(
                    "⚠️ *Ошибка ввода логина*\n\n"
                    "Логин должен содержать от 3 до 20 символов и может включать только буквы, цифры и символы подчеркивания."
                    , parse_mode='Markdown')
                return

            if not is_valid_password(password):
                await update.message.reply_text(
                    "⚠️ *Ошибка ввода пароля*\n\n"
                    "Пароль должен содержать от 6 до 20 символов, включая хотя бы одну заглавную букву, одну цифру и один специальный символ."
                    , parse_mode='Markdown')
                return

            if not is_valid_email(email):
                await update.message.reply_text(
                    "⚠️ *Ошибка ввода почты*\n\n"
                    "Пожалуйста, введите корректный адрес электронной почты."
                    , parse_mode='Markdown')
                return

            if not is_valid_phone(phone):
                await update.message.reply_text(
                    "⚠️ *Ошибка ввода телефона*\n\n"
                    "Пожалуйста, введите корректный номер телефона в формате +79991234567."
                    , parse_mode='Markdown')
                return

            cursor.execute('SELECT * FROM Customer WHERE Phone = ? OR Email = ?', (phone, email))
            existing_user = cursor.fetchone()
            if existing_user:
                error_message = "⚠️ *Ошибка регистрации*\n\n"
                if existing_user[3] == phone:
                    error_message += "Номер телефона уже зарегистрирован.\n"
                if existing_user[4] == email:
                    error_message += "Электронная почта уже зарегистрирована.\n"
                await update.message.reply_text(error_message, parse_mode='Markdown')
                return

            # Генерация и отправка кода подтверждения
            confirmation_code = generate_confirmation_code()
            send_confirmation_email(email, confirmation_code)

            # Сохраняем данные и код в user_data
            context.user_data['pending_registration'] = {
                'username': username,
                'password': password,
                'name': name,
                'phone': phone,
                'email': email,
                'confirmation_code': confirmation_code
            }
            await update.message.reply_text(
                "📧 *Проверка почты*\n\n"
                "Код подтверждения был отправлен на вашу почту. "
                "Пожалуйста, введите его для завершения регистрации.",
                parse_mode='Markdown'
            )
            context.user_data['last_action'] = 'confirm_email'

        elif user_data == "confirm_email":
            # Проверка кода подтверждения
            confirmation_code = text.strip()
            pending_registration = context.user_data.get('pending_registration', {})

            if confirmation_code == pending_registration.get('confirmation_code'):
                user_id = update.message.from_user.id
                cursor.execute('INSERT INTO User (ID_user, Login, Password, Role) VALUES (?, ?, ?, ?)',
                               (user_id, pending_registration['username'], pending_registration['password'],
                                'customer'))
                conn.commit()

                cursor.execute('INSERT INTO Customer (Login, Name, Phone, Email) VALUES (?, ?, ?, ?)',
                               (pending_registration['username'], pending_registration['name'],
                                pending_registration['phone'],
                                pending_registration['email']))
                conn.commit()

                await update.message.reply_text(
                    "🎉 *Регистрация прошла успешно!*\n\n"
                    "Теперь вы зарегистрированы в системе как *{}*. Добро пожаловать! Пожалуйста, войдите в аккаунт снова.".format(
                        pending_registration['username']),
                    parse_mode='Markdown'
                )
                send_welcome_email(pending_registration['email'], pending_registration['username'])

                # Очистка данных
                context.user_data.pop('pending_registration', None)
                context.user_data['last_action'] = None
            else:
                await update.message.reply_text(
                    "❌ *Неверный код подтверждения*\n\n"
                    "Пожалуйста, проверьте вашу почту и попробуйте снова.",
                    parse_mode='Markdown'
                )
        elif context.user_data.get('last_action') == "reset_password":
            # Запрос почты для сброса пароля
            await update.message.reply_text(
                "📝 Пожалуйста, введите вашу почту для отправки кода подтверждения:"
            )
            context.user_data['last_action'] = 'WAITING_FOR_EMAIL'  # Сохраняем состояние в context.user_data

        elif context.user_data.get('last_action') == "WAITING_FOR_EMAIL":
            user_email = update.message.text.strip()

            # Проверяем, есть ли почта в базе данных
            if check_email_in_database(user_email):  # Функция проверки почты
                # Генерируем и отправляем код подтверждения
                confirmation_code = generate_confirmation_code()  # Функция генерации кода
                send_confirmation_email(user_email, confirmation_code)  # Функция отправки кода

                # Сохраняем код и email в контексте для дальнейшей проверки
                context.user_data['confirmation_code'] = confirmation_code
                context.user_data['user_email'] = user_email  # Сохраняем email пользователя

                await update.message.reply_text(
                    "✅ Код подтверждения отправлен на вашу почту. Пожалуйста, введите его:"
                )
                context.user_data['last_action'] = 'WAITING_FOR_CONFIRMATION_CODE'  # Обновляем состояние
            else:
                await update.message.reply_text(
                    "❌ Почта не найдена в базе данных. Пожалуйста, проверьте и попробуйте снова."
                )

        elif context.user_data.get('last_action') == "WAITING_FOR_CONFIRMATION_CODE":
            user_input_code = update.message.text.strip()
            expected_code = context.user_data.get('confirmation_code')

            if user_input_code == expected_code:
                context.user_data['last_action'] = 'WAITING_FOR_NEW_PASSWORD'  # Обновляем состояние
                await update.message.reply_text("✅ Код подтверждения верный. Пожалуйста, введите новый пароль:")
            else:
                await update.message.reply_text("❌ Неверный код подтверждения. Пожалуйста, попробуйте снова.")

        elif context.user_data.get('last_action') == "WAITING_FOR_NEW_PASSWORD":
            new_password = update.message.text.strip()

            if not is_valid_password(new_password):
                await update.message.reply_text(
                    "⚠️ *Ошибка ввода пароля*\n\n"
                    "Пароль должен содержать от 6 до 20 символов, включая хотя бы одну заглавную букву, одну цифру и один специальный символ.",
                    parse_mode='Markdown'
                )
                return

            await update.message.reply_text(
                "🔒 Пожалуйста, введите новый пароль еще раз:"
            )
            context.user_data['new_password'] = new_password  # Сохраняем новый пароль
            context.user_data['last_action'] = 'WAITING_FOR_CONFIRM_PASSWORD'  # Обновляем состояние

        elif context.user_data.get('last_action') == "WAITING_FOR_CONFIRM_PASSWORD":
            confirm_password = update.message.text.strip()
            new_password = context.user_data.get('new_password')
            user_email = context.user_data.get('user_email')

            if new_password == confirm_password:
                # Обновляем пароль в базе данных
                update_password_in_database(user_email, new_password)  # Функция обновления пароля

                await update.message.reply_text(
                    "✅ Пароль успешно обновлен!"
                )
                context.user_data.clear()  # Полная очистка всех временных данных
            else:
                await update.message.reply_text(
                    "❌ Пароли не совпадают. Пожалуйста, попробуйте снова."
                )
    except Exception as e:
        print(f"Ошибка: {e}")
        await update.message.reply_text(
            "❌ *Произошла ошибка. Пожалуйста, попробуйте позже.*",
            parse_mode='Markdown'
        )
    finally:
        conn.close()


async def show_customer_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str) -> None:
    """Показывает главное меню для пользователя."""
    keyboard = [
        [InlineKeyboardButton("Товары", callback_data='products')],
        [InlineKeyboardButton("История заказов", callback_data='order_history')],
        [InlineKeyboardButton("Корзина", callback_data='cart')],
        [InlineKeyboardButton("Выход", callback_data='logout')]  # Кнопка выхода
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        query = update.callback_query
        await query.answer()  # Ответ на callback-запрос, чтобы убрать "часики"
        await query.message.edit_text(
            f"Добро пожаловать, {username}!\nВы находитесь в личном кабинете покупателя.",
            reply_markup=reply_markup
        )
    elif update.message:
        # Если функция вызвана через сообщение
        await update.message.reply_text(
            f"Добро пожаловать, {username}!\nВы находитесь в личном кабинете покупателя.",
            reply_markup=reply_markup
        )


async def handle_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Функция для выхода из учетной записи."""
    context.user_data.clear()  # Очистка всех данных пользователя
    keyboard = [
        [InlineKeyboardButton("Вход", callback_data='sign_in')],
        [InlineKeyboardButton("Регистрация", callback_data='reg_in')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.edit_text(
        "👋 Вы успешно вышли из системы.\n\n"
        "Для продолжения выберите одну из доступных команд из меню ниже:",
        reply_markup=reply_markup
    )


# Функция для показа категорий
async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Получаем категории из БД
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ID_category, Name FROM Category")
    categories = cursor.fetchall()
    conn.close()

    if not categories:
        await query.message.edit_text("❌ Нет доступных категорий.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Назад", callback_data="profile")]]
            ))
        return

    # Формируем кнопки для категорий
    keyboard = [[InlineKeyboardButton(cat[1], callback_data=f"category_{cat[0]}")] for cat in categories]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="profile")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("📦 *Категории товаров*\n\nВыберите категорию:", reply_markup=reply_markup)


# Функция для показа товаров
async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Получаем ID выбранного автомобиля
    car_id = query.data.split("_")[1]

    # Получаем товары из БД
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ID_product, Name, Description, Cost, Status 
        FROM Product 
        WHERE ID_car = ?
    """, (car_id,))
    products = cursor.fetchall()
    conn.close()

    if not products:
        await query.message.edit_text("❌ Нет доступных товаров.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Назад", callback_data=f"products")]]
            ))
        return

    # Формируем кнопки для товаров
    keyboard = [[InlineKeyboardButton(f"{prod[0]} - {prod[2]}₽ ({prod[3]})", callback_data=f"product_{prod[0]}")]
                for prod in products]
    keyboard.append([InlineKeyboardButton("Назад", callback_data=f"products")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("🛠 *Товары*\n\nВыберите товар:", reply_markup=reply_markup)


async def show_product_details(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int) -> None:
    """Отображает подробную информацию о товаре, включая количество на складе и возможность добавить в корзину."""
    # Получаем подробную информацию о товаре и количество на складе из базы данных
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Name, Description, Cost, Status, IFNULL(Count_product, 0) 
        FROM Product
        WHERE ID_product = ?
    """, (product_id,))
    product = cursor.fetchone()
    conn.close()

    if not product:
        await update.callback_query.message.edit_text("❌ Товар не найден.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="products")]]))
        return

    name, description, cost, status, stock = product

    # Формируем сообщение с полной информацией о товаре
    product_info = f"🛠 *Товар:* {name}\n\n"
    product_info += f"📄 *Описание:* {description}\n"
    product_info += f"💰 *Цена:* {cost}₽\n"
    product_info += f"📦 *Статус:* {status}\n"
    product_info += f"📊 *Наличие на складе:* {stock} шт."

    # Формируем кнопки для добавления в корзину и возврата
    keyboard = [
        [InlineKeyboardButton("Добавить в корзину", callback_data=f"add_to_cart_{product_id}")],
        [InlineKeyboardButton("Назад", callback_data="products")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем сообщение с подробной информацией о товаре
    await update.callback_query.message.edit_text(product_info, reply_markup=reply_markup)


async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int) -> None:
    """Добавляет товар в корзину пользователя с проверкой на наличие на складе."""
    query = update.callback_query
    await query.answer()

    # Получаем информацию о товаре и его наличии на складе
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Name, Cost, IFNULL(Count_product, 0) 
        FROM Product
        WHERE ID_product = ?
    """, (product_id,))
    product = cursor.fetchone()
    conn.close()

    if not product:
        await query.message.edit_text("❌ Товар не найден.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("Назад", callback_data="products")]]))
        return

    name, cost, stock = product

    # Проверка, есть ли товар на складе
    if stock <= 0:
        await query.message.edit_text(
            f"❌ Товар '{name}' временно отсутствует на складе.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="products")]])
        )
        return

    # Добавляем товар в корзину пользователя
    if 'cart' not in context.user_data:
        context.user_data['cart'] = []

    context.user_data['cart'].append({'product_id': product_id, 'name': name, 'cost': cost})

    # Подтверждение добавления в корзину
    await query.message.edit_text(
        f"🛒 Товар '{name}' добавлен в вашу корзину!\n\n"
        "Вы можете продолжить покупки или перейти к корзине.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Перейти в корзину", callback_data="cart")],
            [InlineKeyboardButton("Назад", callback_data="products")]
        ])
    )


async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает корзину пользователя."""
    query = update.callback_query
    await query.answer()

    # Получаем данные из корзины пользователя
    cart = context.user_data.get('cart', [])

    if not cart:
        await query.message.edit_text("🛒 Ваша корзина пуста.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Формируем список товаров в корзине
    cart_info = "🛒 Ваша корзина:\n\n"
    total_cost = 0
    for item in cart:
        cart_info += f"• {item['name']} - {item['cost']}₽\n"
        total_cost += item['cost']

    cart_info += f"\n🛍️ *Общая сумма:* {total_cost}₽"

    # Формируем кнопки для оформления заказа или возврата
    keyboard = [
        [InlineKeyboardButton("Оформить заказ", callback_data="checkout")],
        [InlineKeyboardButton("Назад", callback_data="profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(cart_info, reply_markup=reply_markup)


async def create_order_and_generate_qr(cart, user_id):
    # 1. Создаём заказ в базе данных
    conn = create_connection()
    cursor = conn.cursor()

    # Вставляем заказ в таблицу "Order"
    cursor.execute("INSERT INTO 'Order' (ID_customer, Status) VALUES (?, ?)", (user_id, 'pending'))
    order_id = cursor.lastrowid

    total_cost = 0

    # 2. Добавляем товары из корзины в таблицу Products_on_order
    for item in cart:
        cursor.execute("""
            INSERT INTO Products_on_order (ID_order, ID_product, Amount, Cost)
            VALUES (?, ?, ?, ?)
        """, (
        order_id, item['product_id'], 1, item['cost']))  # Количество товара = 1, если нужно больше - добавьте логику

        total_cost += item['cost']

    conn.commit()

    # Генерация QR-кода для оплаты через СБП
    payment_link = f'https://payment_system.com/pay?order_id={order_id}&amount={total_cost}'  # Это пример ссылки
    qr = qrcode.make(payment_link)

    # Сохраняем изображение QR в байтовом потоке для отправки в Telegram
    img_byte_arr = io.BytesIO()
    qr.save(img_byte_arr)
    img_byte_arr.seek(0)

    # Закрываем соединение с БД
    conn.close()

    return img_byte_arr, order_id


async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Оформляет заказ и очищает корзину."""
    query = update.callback_query
    await query.answer()

    # Получаем данные корзины
    cart = context.user_data.get('cart', [])

    if not cart:
        await query.message.edit_text("❌ Ваша корзина пуста, добавьте товары в корзину перед оформлением.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Получаем имя пользователя из context
    username = context.user_data.get('username')
    # Получаем customer_id по username
    customer_id = await get_customer_id_by_username(username)
    if not customer_id:
        await query.message.edit_text("❌ Не удалось найти клиента с таким именем пользователя.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Создаем заказ и генерируем QR
    img_byte_arr, order_id = await create_order_and_generate_qr(cart, customer_id)

    # Отправляем QR-код пользователю
    await query.message.edit_text(
        "🛒 Ваш заказ оформлен. Для оплаты отсканируйте QR-код ниже.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Подтвердить оплату", callback_data=f"confirm_payment_{order_id}")]])
    )
    sent_photo_message = await query.message.reply_photo(photo=img_byte_arr)

    # Сохраняем ID сообщения с фото, чтобы удалить его позже
    context.user_data['qr_message_id'] = sent_photo_message.message_id
    context.user_data['qr_chat_id'] = sent_photo_message.chat_id


async def get_customer_id_by_username(username: str) -> int:
    """Извлекает customer_id по username из базы данных."""

    # Создаем соединение с базой данных
    conn = create_connection()
    cursor = conn.cursor()

    # SQL-запрос для поиска customer_id по username
    cursor.execute("SELECT ID_customer FROM Customer WHERE Login = ?", (username,))

    # Получаем результат
    result = cursor.fetchone()

    # Закрываем соединение с базой данных
    conn.close()

    if result:
        # Возвращаем ID клиента
        return result[0]
    else:
        # Если клиента с таким username нет
        return None


async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подтверждает оплату и добавляет запись в таблицу платежей."""
    query = update.callback_query
    await query.answer()

    # Получаем имя пользователя из context
    username = context.user_data.get('username')
    if not username:
        await query.message.edit_text("❌ Имя пользователя не найдено. Попробуйте снова.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Получаем customer_id по username
    customer_id = await get_customer_id_by_username(username)
    if not customer_id:
        await query.message.edit_text("❌ Не удалось найти клиента с таким именем пользователя.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Продолжаем с обработкой платежа
    cart = context.user_data.get('cart', [])
    if not cart:
        await query.message.edit_text("❌ Ваш заказ пуст, не удалось подтвердить оплату.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Получаем сумму заказа
    total_cost = sum(item['cost'] for item in cart)

    # Примерный способ оплаты
    way_of_payment = "СБП (QR-код)"

    # Получаем имя пользователя из context
    username = context.user_data.get('username')
    if not username:
        await query.message.edit_text("❌ Имя пользователя не найдено. Попробуйте снова.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Получаем customer_id по username
    customer_id = await get_customer_id_by_username(username)
    if not customer_id:
        await query.message.edit_text("❌ Не удалось найти клиента с таким именем пользователя.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Создаем соединение с базой данных
    conn = create_connection()
    cursor = conn.cursor()

    # Получаем последний заказ для клиента
    cursor.execute("""
        SELECT ID_order FROM "Order"
        WHERE ID_customer = ?
        ORDER BY ID_order DESC
        LIMIT 1
    """, (customer_id,))

    result = cursor.fetchone()

    if result:
        id_order = result[0]  # Получаем ID_order
        # Вставляем запись в таблицу Payment с реальным ID_order
        cursor.execute("""
            INSERT INTO Payment (ID_order, Summ_payment, Way_of_payment)
            VALUES (?, ?, ?)
        """, (id_order, total_cost, way_of_payment))

        conn.commit()  # Не забудьте зафиксировать изменения
    else:
        print("Не найдено ни одного заказа для данного клиента.")

    # Закрываем соединение
    conn.close()

    # Отправляем письмо с подтверждением заказа
    await send_order_confirmation_email(customer_id, total_cost, way_of_payment)

    context.user_data['cart'] = []

    # Уведомляем пользователя
    await query.message.edit_text(
        "✅ Оплата подтверждена! Ваш заказ в обработке.\n\nОжидайте письмо о заказе.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="profile")]])
    )

    # Удаляем сообщение с QR-кодом
    qr_message_id = context.user_data.get('qr_message_id')
    qr_chat_id = context.user_data.get('qr_chat_id')

    if qr_message_id and qr_chat_id:
        try:
            # Удаляем сообщение с QR-кодом
            await context.bot.delete_message(chat_id=qr_chat_id, message_id=qr_message_id)
        except Exception as e:
            print(f"Ошибка при удалении сообщения: {e}")

    # Очистка данных пользователя
    context.user_data.pop('qr_message_id', None)
    context.user_data.pop('qr_chat_id', None)


async def send_order_confirmation_email(customer_id, total_cost, way_of_payment):
    """Отправляет красивое и персонализированное подтверждение заказа на email клиента."""

    # Получаем email клиента
    conn = create_connection()
    cursor = conn.cursor()

    # Получаем email клиента
    cursor.execute("SELECT Email FROM Customer WHERE ID_customer = ?", (customer_id,))
    customer_email = cursor.fetchone()[0]

    # Получаем номер заказа
    cursor.execute("SELECT ID_order FROM 'Order' WHERE ID_customer = ? ORDER BY ID_order DESC", (customer_id,))
    order_number = cursor.fetchone()[0]

    # Получаем товары в заказе
    cursor.execute("""
        SELECT p.Name, po.Amount, po.Cost
        FROM Products_on_order po
        INNER JOIN Product p ON po.ID_product = p.ID_product
        WHERE po.ID_order = ?
    """, (order_number,))

    products = cursor.fetchall()
    conn.close()

    # Составляем текст для товаров
    products_text = "🛒 Товары в заказе:\n"
    for product in products:
        name, amount, cost = product
        products_text += f"  - {name} (Количество: {amount}, Цена: {cost}₽)\n"

    # Составляем письмо
    subject = f"Ваш заказ №{order_number} подтвержден! 🎉"
    body = f"""
    Здравствуйте!

    Мы рады сообщить, что ваш заказ №{order_number} был успешно оформлен. Вот его детали:

    📦 Общая сумма: {total_cost}₽
    💳 Способ оплаты: {way_of_payment}

    {products_text}

    Пункт самовывоза товара: г. Москва, ул. Южнопортовая, д. 38, с. 1.

    При получении понадобится документ подтверждающий личность.

    Мы ценим ваш выбор и благодарим за доверие. Наши специалисты уже начинают обрабатывать ваш заказ, и вы сможете его получить, ждите письмо о готовности товара!. Если у вас возникнут вопросы, не стесняйтесь обращаться к нам.

    Благодарим за покупку и надеемся на ваше дальнейшее сотрудничество!

    С уважением,
    Ваша команда KorZap!
    """

    # Создаем MIME сообщение
    msg = MIMEMultipart()
    msg['From'] = "telmanmessi@gmail.com"
    msg['To'] = customer_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    # Отправляем письмо через SMTP сервер
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login("login", "password")
        server.sendmail("telmanmessi@gmail.com", customer_email, msg.as_string())


async def history_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает историю заказов пользователя."""
    query = update.callback_query
    await query.answer()

    # Получаем имя пользователя из context
    username = context.user_data.get('username')
    if not username:
        await query.message.edit_text("❌ Имя пользователя не найдено. Попробуйте снова.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Получаем customer_id по username
    customer_id = await get_customer_id_by_username(username)
    if not customer_id:
        await query.message.edit_text("❌ Не удалось найти клиента с таким именем пользователя.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Получаем информацию о заказах пользователя
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("""
            SELECT o.ID_order, o.Date_of_order, o.Status, p.Summ_payment, p.Way_of_payment
            FROM "Order" o
            INNER JOIN Payment p ON o.ID_order = p.ID_order
            WHERE o.ID_customer = ?
        """, (customer_id,))

    orders = cursor.fetchall()

    if not orders:
        await query.message.edit_text("❌ У вас нет заказов.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("Назад", callback_data="profile")]]))
        return

    # Формирование текста для отображения истории заказов
    history_text = "📜 История ваших заказов:\n\n"

    for order in orders:
        id_order, date_order, status, summ, way = order

        # Получаем товары для текущего заказа
        cursor.execute("""
                SELECT p.ID_product, p.Name, po.Amount, po.Cost
                FROM Products_on_order po
                INNER JOIN Product p ON po.ID_product = p.ID_product
                WHERE po.ID_order = ?
                ORDER BY po.ID_order DESC
            """, (id_order,))

        products = cursor.fetchall()

        # Формируем текст для товаров
        products_text = "🛒 Товары в заказе:\n"
        for product in products:
            id_product, name, amount, cost = product
            products_text += (f"  - {name} (Количество: {amount}, Цена: {cost}₽)\n")

        history_text += (f"🔹 Номер Заказа: {id_order}\n"
                         f"📅 Дата заказа: {date_order}\n"
                         f"✅ Статус: {status}\n"
                         f"💰 Сумма: {summ}₽\n"
                         f"💳 Способ оплаты: {way}\n"
                         f"{products_text}\n")

    conn.close()

    await query.message.edit_text(history_text,
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("Назад", callback_data="profile")]]))



def main():
    token = 'TOKEN'
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()


if __name__ == '__main__':
    main()

