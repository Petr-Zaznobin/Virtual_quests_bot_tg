import asyncio
import logging
import string

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile

import database
from config import *

# logging
logging.basicConfig(
    # level=logging.INFO,  # Уровень логирования
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Формат сообщения
    handlers=[
        logging.FileHandler("app.log"),  # Запись логов в файл "app.log"
        # logging.StreamHandler()  # Вывод логов на консоль
    ]
)
logger = logging.getLogger(__name__)

# FSM
storage = MemoryStorage()

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# postgresql
database = database.AsyncDatabase(
    db_name=db_name,
    user=user,
    password=password,
    host=host,
    port=port
)

# Создание директории для загрузок. Существует ли директория для загрузок?
os.makedirs('./uploads', exist_ok=True)

# Кол-во квестов на одной странице
QUESTS_PER_PAGE = 5


@router.message(Command("start"))
async def start_command(message: Message):
    try:
        # tg_user_id: int = int(message.from_user.id)
        chat_id: int = int(message.chat.id)
        user_exist = await database.user_exists(chat_id)
        if user_exist:
            await main_menu(chat_id)
        else:
            await message.answer(
                text='Готовы зарегистрироваться?',
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(
                        text="Зарегистрироваться",
                        callback_data="Registration"
                    )]]
                )
            )
    except Exception as e:
        logger.error("Произошла ошибка в \start: %s", e)


# Безопасное удаление последнего сообщения
async def safely_delete_last_message(tg_user_id, chat_id):
    try:
        last_messages = await database.get_last_messages_by_user_id(tg_user_id)
        if last_messages is not None:
            for message in last_messages:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=message)
                    # print(f"[Bot] Сообщение {message} пользователя {tg_user_id} успешно удалено")
                except Exception as e:
                    # print(f"[Bot] Ошибка при удалении сообщения для пользователя {tg_user_id}: {str(e)}")
                    continue
            await  database.clear_last_message_ids_by_user_id(tg_user_id)
            # print(f"[DB] Все сообщения удалениы из базы данных {tg_user_id}")

            await database.set_last_message_by_user_id(tg_user_id, None)
    except Exception as e:
        logger.error("Произошла ошибка в safely_delete_last_message: %s", e)


async def main_menu(tg_user_id: int):
    try:
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Мой профиль', callback_data='my_profile')],
            [InlineKeyboardButton(text='Маркет квестов', callback_data='market')]
            # ,[InlineKeyboardButton(text='Мои квесты', callback_data='my_quests')]
        ])
        await bot.send_message(tg_user_id, "Выберите дальнейшее действие", reply_markup=inline_kb)
    except Exception as e:
        logger.error("Произошла ошибка в main_menu: %s", e)


# ---------------------Registration------------------------
class Registration(StatesGroup):
    UsernameWaiting = State()


@router.callback_query(lambda call: call.data == "Registration")
async def registration_button_press(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer(
            text="Пожалуйста, введите Ваше имя: "
        )
        # Устанавливаем пользователю состояние "выбирает username"
        await state.set_state(Registration.UsernameWaiting)
    except Exception as e:
        logger.error("Произошла ошибка в registration_button_press: %s", e)


@router.message(Registration.UsernameWaiting)
async def register_user(message: Message, state: FSMContext):
    try:
        # tg_user_id: int = int(message.from_user.id)
        chat_id: int = int(message.chat.id)
        username = message.text
        await state.update_data(username=username)
        await database.registration(chat_id, username)
        await message.answer("Регистрация завершена!")
        await state.clear()
        await main_menu(chat_id)
    except Exception as e:
        logger.error("Произошла ошибка в register_user: %s", e)


# -------------------------my profile----------------------
@router.callback_query(lambda call: call.data == "my_profile")
async def my_profile_button_press(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        user_data = await database.get_user_data(tg_user_id)
        username = user_data['username']

        # Поставить количество пройденных квестов. За количество пройденных квестов начислять звездщочки (местная доп валюта)

        message_txt = f"Здравствуйте, {username}!\nДобро пожаловать в Ваш профиль!\nТут пока что ничего нет, но, в будущем, мы обязательно добавим что-то новое."
        msg = await bot.send_message(tg_user_id,
                                     text=message_txt,
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                         [InlineKeyboardButton(text="Изменить никнейм",
                                                               callback_data="change_username")],
                                         [InlineKeyboardButton(text="Удалить аккаунт", callback_data="delete_account")],
                                         [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
                                     ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(chat_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в my_profile_button_press: %s", e)


class ChangeName(StatesGroup):
    ChangeNameWaiting = State()


@router.callback_query(lambda call: call.data == "change_username")
async def change_username_button_press(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer(
            text="Пожалуйста, введите новое имя: "
        )
        # Устанавливаем пользователю состояние "выбирает username"
        await state.set_state(ChangeName.ChangeNameWaiting)
    except Exception as e:
        logger.error("Произошла ошибка в change_username_button_press: %s", e)


@router.message(ChangeName.ChangeNameWaiting)
async def change_name(message: Message, state: FSMContext):
    try:
        # tg_user_id: int = int(message.from_user.id)
        chat_id: int = int(message.chat.id)
        new_username = message.text
        await state.update_data(username=new_username)
        await database.change_username(chat_id, new_username)
        user_data = await database.get_user_data(chat_id)
        username = user_data['username']
        message_txt = f"Так выглядит измененный профиль:\n\nЗдравствуйте, {username}!\nДобро пожаловать в Ваш профиль!\nТут пока что ничего нет, но, в будущем, мы обязательно добавим что-то новое."
        await bot.send_message(chat_id,
                               text=message_txt,
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                   [InlineKeyboardButton(text="Изменить никнейм", callback_data="change_username")],
                                   [InlineKeyboardButton(text="Удалить аккаунт", callback_data="delete_account")],
                                   [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
                               ]))
        await state.clear()
    except Exception as e:
        logger.error("Произошла ошибка в change_name: %s", e)


@router.callback_query(lambda call: call.data == "delete_account")
async def delete_account(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)

        await bot.send_message(tg_user_id,
                               text="Вы уверены, что хотите удалить аккаунт?\nВсе Ваши квесты не сохранятся",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                   [InlineKeyboardButton(text="Нет", callback_data="main_menu")],
                                   [InlineKeyboardButton(text="Да", callback_data="apply_delete_account")]
                               ]))
    except Exception as e:
        logger.error("Произошла ошибка в delete_account: %s", e)


@router.callback_query(lambda call: call.data == "apply_delete_account")
async def apply_delete_account(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        await database.delete_account(tg_user_id)
        await bot.send_message(tg_user_id, text="Ваш аккаунт успешно удален!")
        message = callback.message
        await start_command(message)
    except Exception as e:
        logger.error("Произошла ошибка в apply_delete_account: %s", e)


# -------------------------my quests-----------------------


# Добавить звезды за хорошую концовку


@router.callback_query(lambda call: call.data == "my_quests")
async def my_quests_button_press(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        quests_list = await database.get_my_quests(tg_user_id)
        if quests_list:
            for quest_id in quests_list:
                quest_data = await database.get_quest_data_by_id(quest_id)
                id = quest_data['id']
                name = quest_data['name']
                description = quest_data['description']
                is_free = quest_data['is_free']
                like = quest_data['likes']
                dislike = quest_data['dislikes']
                price = "free" if is_free else "$"
                message_txt = f"Название: «{name}»\nОписание: {description}\n{like}❤️   {dislike}🙁\n{price}"
                await bot.send_message(tg_user_id, text=message_txt,
                                       reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                           [InlineKeyboardButton(text="Играть", callback_data=f"play:{id}")]
                                       ]))
            await bot.send_message(tg_user_id, text="В главное меню",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                       [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
                                   ]))
        else:
            await bot.send_message(tg_user_id,
                                   text="У вас нет купленных квестов.\n Хотите посмотреть каталог наших квестов?",
                                   parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                       [InlineKeyboardButton(text="Маркет", callback_data="market")]
                                   ]))
    except Exception as e:
        logger.error("Произошла ошибка в my_quests_button_press: %s", e)


# заглушка
@router.callback_query(lambda call: call.data.startswith('play:'))
async def play(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        quest_id = int(callback.data.split(':')[1])
        await main_menu(tg_user_id)
    except Exception as e:
        logger.error("Произошла ошибка в play: %s", e)


# --------------------------market--------------------------
@router.callback_query(lambda call: call.data == "market")
async def market(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        quests_list = await database.get_all_quest()
        if quests_list:
            for quest_data in quests_list:
                id = quest_data['id']
                name = quest_data['name']
                description = quest_data['description']
                is_free = quest_data['is_free']
                like = quest_data['likes']
                dislike = quest_data['dislikes']
                price = "free" if is_free else "$"

                # text_play_buy = "Играть" if is_free else "Купить" Закинуть в если выбрал квест

                message_txt = f"Название: «{name}»  \nОписание: {description}\n{like}❤️   {dislike}🙁\n{price}"
                msg = await bot.send_message(tg_user_id, text=message_txt,
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                 [InlineKeyboardButton(text="Выбрать", callback_data=f"buy:{id}")]
                                             ]))
                await safely_delete_last_message(tg_user_id, chat_id)
                await database.set_last_message_by_user_id(chat_id, msg.message_id)
            msg2 = await bot.send_message(tg_user_id, text="В главное меню",
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                              [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
                                          ]))
            await database.set_last_message_by_user_id(chat_id, msg2.message_id)
        else:
            msg = await bot.send_message(tg_user_id,
                                         text="В настоящее время тут пусто. \n **Coming soon**",
                                         parse_mode="Markdown",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                             [InlineKeyboardButton(text="Вернуться в меню", callback_data="main_menu")]
                                         ]))
            await safely_delete_last_message(tg_user_id, chat_id)
            await database.set_last_message_by_user_id(chat_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в market: %s", e)


# --------------------------quest_clases--------------------
class TimeLoop(StatesGroup):
    Start = State()
    Legend = State()
    Code = State()
    GetKey = State()
    Question1 = State()
    Question2 = State()
    Question3 = State()
    Unsuccessful = State()


# ----------------------------playing-----------------------
@router.callback_query(lambda callback: callback.data.startswith('buy:'))
async def StartQuest(callback: CallbackQuery):
    try:
        quest_id = int(callback.data.split(':')[1])
        tg_user_id: int = int(callback.from_user.id)

        if quest_id == 2:  # time_loop
            await quest(callback.message)

        else:
            await callback.message.answer("Ошибка запуска квеста")
    except Exception as e:
        logger.error("Произошла ошибка в StartQuest: %s", e)


# --------------------------quests--------------------------

# TIME LOOP

async def quest(message: Message):
    try:
        chat_id: int = int(message.chat.id)
        legend1 = ("Вы - молодой журналист, который получает странное письмо от своего пропавшего дяди "
                   "известного археолога.")
        legend2 = ("В письме дядя утверждает, что нашел способ путешествовать во времени, "
                   "но что-то пошло не так, и он застрял в прошлом.")
        legend3 = ("Вы должны разгадать тайну исчезновения дяди, "
                   "используя письма, найденные в его кабинете, и свои детективные способности.")
        # Удаление предыдущих сообщений
        await safely_delete_last_message(chat_id, chat_id)

        # Отправка и сохранение первого сообщения
        sent_message = await message.answer(legend1)
        await database.set_last_message_by_user_id(chat_id, sent_message.message_id)

        # Отправка и сохранение второго сообщения
        sent_message = await message.answer(legend2)
        await database.set_last_message_by_user_id(chat_id, sent_message.message_id)

        # Отправка третьего сообщения с клавиатурой и сохранение его ID
        sent_message = await message.answer(
            text=legend3,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Играть", callback_data="startTimeLoop")],
                [InlineKeyboardButton(text="Другие квесты", callback_data="market")]
            ]))
        await database.set_last_message_by_user_id(chat_id, sent_message.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в quest: %s", e)


@router.callback_query(lambda call: call.data == "startTimeLoop")
async def StartTimeLoop(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        await database.init_artefacts_time_loop(tg_user_id)
        txt = "Вы видете письмо на столе"
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть письмо", callback_data="open_letter")],
            [InlineKeyboardButton(text="Искать другие улики", callback_data="other_clues_1")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(int(callback.from_user.id), msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в StartTimeLoop: %s", e)


@router.callback_query(lambda call: call.data == "open_letter")
async def open_letter(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        photo_path = "uploads/First_letter.JPG"
        photo = FSInputFile(photo_path)
        msg = await bot.send_photo(chat_id=chat_id, photo=photo, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Искать другие улики", callback_data="other_clues_1")]
        ]))
        # print(msg.message_id)
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в open_letter: %s", e)


@router.callback_query(lambda call: call.data == "other_clues_1")
async def Other_clues_1(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        txt = ("Среди бумаг дяди вы находите стопку записок, оставленных им во время его путешествия в прошлое. "
               "В них он описывает свои впечатления, людей, с которыми встретился, и события, которые наблюдал. "
               "Хотите прочитать записку?")
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="read_notes")],
            [InlineKeyboardButton(text="Нет", callback_data="other_clues_2")],
            [InlineKeyboardButton(text="Вернуться к письму", callback_data="startTimeLoop")]
        ]))
        # print(msg.chat.id)
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в Other_clues_1: %s", e)


@router.callback_query(lambda call: call.data == "read_notes")
async def read_notes(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        photo_path = "uploads/Notes.png"
        photo = FSInputFile(photo_path)
        msg = await bot.send_photo(chat_id=chat_id, photo=photo, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Искать другие улики", callback_data="other_clues_2")],
            [InlineKeyboardButton(text="Вернуться назад", callback_data="other_clues_1")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в read_notes: %s", e)


@router.callback_query(lambda call: call.data == "other_clues_2")
async def other_clues_2(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        txt = ("В ящике стола вы находите дневник Вашего дяди, в котором зашифрован непонятный код.\n "
               "В нем он записывал свои наблюдения, результаты исследований и некоторые тайные записи.")
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Изучить записи", callback_data="code")],
            [InlineKeyboardButton(text="Не трогать дневник", callback_data="other_clues_3")],
            [InlineKeyboardButton(text="Вернуться назад", callback_data="other_clues_1")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в other_clues_2: %s", e)


@router.callback_query(lambda call: call.data == "code")
async def decode(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        photo_path = "uploads/Code.png"
        photo = FSInputFile(photo_path)
        msg = await bot.send_photo(chat_id=chat_id, photo=photo, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Искать другие улики", callback_data="other_clues_3")],
            [InlineKeyboardButton(text="Вернуться назад", callback_data="other_clues_2")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в decode: %s", e)


@router.callback_query(lambda call: call.data == "other_clues_3")
async def other_clues_3(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        txt1 = ('В шкафу Вы находите ящик, запертый на ключ. '
                'Внутри - странный артефакт, похожий на кулон. '
                'В дневнике дяди упоминается, что этот артефакт может служить ключом к путешествию во времени, '
                '"Ключом Времени". \nЧто вы делаете?')
        txt2 = ('В шкафу Вы находите ящик, который уже открыли, а внутри пыль. '
                'Видно, что когда-то тут лежал кулон. Который Вы уже взяли.')
        artefacts = await database.get_artefacts_time_loop(tg_user_id)
        if artefacts['safe']:
            msg = await bot.send_message(chat_id=chat_id, text=txt2, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Искать дальше", callback_data="other_clues_4")],
                [InlineKeyboardButton(text="Вернуться назад", callback_data="other_clues_2")]
            ]))
        else:
            msg = await bot.send_message(chat_id=chat_id, text=txt1, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Попытаться открыть ящик", callback_data="open_box")],
                [InlineKeyboardButton(text="Не трогать ящик", callback_data="other_clues_4")],
                [InlineKeyboardButton(text="Вернуться назад", callback_data="other_clues_2")]
            ]))

        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в other_clues_3: %s", e)


@router.callback_query(lambda call: call.data == "open_box")
async def open_box(callback: CallbackQuery, state: FSMContext):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        txt = "Введите пароль:"
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Вернуться назад", callback_data="other_clues_3")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
        await state.set_state(TimeLoop.Code)
    except Exception as e:
        logger.error("Произошла ошибка в open_box: %s", e)


@router.message(TimeLoop.Code)
async def check_code(message: Message):
    try:
        # tg_user_id: int = int(message.from_user.id)
        chat_id: int = int(message.chat.id)
        if message.text == "6142":
            msg = await bot.send_message(chat_id=chat_id, text="Успешно")
            await database.set_last_message_by_user_id(chat_id, message.message_id)
            await database.set_last_message_by_user_id(chat_id, msg.message_id)
            await database.update_safe_time_loop(chat_id, 1)
            await access_code(message)
        else:
            artefacts = await database.get_artefacts_time_loop(chat_id)
            count_safe_try = artefacts['safe_tip']
            # print(count_safe_try)
            txt = "----НЕВЕРНЫЙ КОД!----\n попробуйте еще раз"
            if count_safe_try >= 3:
                msg = await bot.send_message(chat_id=chat_id, text=txt,
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                 [InlineKeyboardButton(text="Вернуться назад",
                                                                       callback_data="other_clues_3")],
                                                 [InlineKeyboardButton(text="Подсказка", callback_data="safe_tip")]
                                             ]))
            else:
                msg = await bot.send_message(chat_id=chat_id, text=txt,
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                 [InlineKeyboardButton(text="Вернуться назад",
                                                                       callback_data="other_clues_3")]
                                             ]))
                await database.inc_safe_tip_time_loop(chat_id)
            await database.set_last_message_by_user_id(chat_id, message.message_id)
            await database.set_last_message_by_user_id(chat_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в check_code: %s", e)


@router.callback_query(lambda call: call.data == "safe_tip")
async def safe_tip(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        photo_path = "uploads/Tip.png"
        photo = FSInputFile(photo_path)
        msg = await bot.send_photo(chat_id=chat_id, photo=photo, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Вернуться к коду (подсказка исчезнет)", callback_data="open_box")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в safe_tip: %s", e)


async def access_code(message: Message):
    try:
        # tg_user_id: int = int(message.from_user.id)
        chat_id: int = int(message.chat.id)
        await bot.send_message(chat_id=chat_id, text="Вы нашли артефакт")
        await database.update_key_time_loop(chat_id, 1)
        photo_path = "uploads/Key.png"
        photo = FSInputFile(photo_path)
        await safely_delete_last_message(chat_id, chat_id)
        msg = await bot.send_photo(chat_id=chat_id, photo=photo)
        msg2 = await bot.send_message(chat_id=chat_id,
                                      text="Это «Ключ Времени», которые поможет вам воспользоваться временной аномалией",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                          [InlineKeyboardButton(text="Искать другие улики",
                                                                callback_data="other_clues_4")],
                                          [InlineKeyboardButton(text="Вернуться назад",
                                                                callback_data="other_clues_3")]
                                      ]))
        await safely_delete_last_message(chat_id, chat_id)
        await database.set_last_message_by_user_id(chat_id, msg2.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в access_code: %s", e)


@router.callback_query(lambda call: call.data == "other_clues_4")
async def other_clues_4(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        txt = ("За книжным шкафом вы обнаруживаете тайный ход. "
               "В дневнике дяди упоминается, что он использовал этот ход, "
               "чтобы добраться до места проведения своих экспериментов. "
               "\nЧто вы делаете?")
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Войти в тайный ход", callback_data=f"laboratory")],
            [InlineKeyboardButton(text="Назад", callback_data="other_clues_3")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в other_clues_4: %s", e)


@router.callback_query(lambda call: call.data == "laboratory")
async def laboratory(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        txt0 = ("Как только Вы вошли, дверь с грохотом закрылась. "
                "Вы попали в заброшенную пыльную лабораторию дяди. "
                "Тут очень мало света, но Вам удается что-то разглядеть. "
                "Здесь Вы видите несколько приборов, записную книжку с информацией о путешествиях во времени и чертежи. "
                "\nЧто вы делаете?")
        msg0 = await bot.send_message(chat_id=chat_id, text=txt0, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Попытаться открыть дверь', callback_data="open_door")],
            [InlineKeyboardButton(text='Изучить записную книжку', callback_data="devices")],
            [InlineKeyboardButton(text='Посмотреть чертеж', callback_data="drafts")],
            [InlineKeyboardButton(text='Искать другие улики', callback_data="other_clues_5")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg0.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в laboratory: %s", e)


@router.callback_query(lambda call: call.data == "open_door")
async def open_door(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id = callback.message.chat.id
        txt = ("Дверь заклинило. У Вас не получается её открыть, но вы заметили щенка, привязанного к ножке стола "
               "с надписью на ошейнике КОПЕРНИК. Он выглядит уставшим. Однако Вы замечаете его умные глаза и острые когти")
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Взять щенка себе', callback_data="take_puppy")],
            [InlineKeyboardButton(text='Не рисковать', callback_data=f"not_risk")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в open_door: %s", e)


@router.callback_query(lambda call: call.data == "take_puppy")
async def take_puppy(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id = callback.message.chat.id
        txt = "Это оказалась очень умная и добрая собака. Теперь у тебя появился новый пушистый друг"
        await database.update_dog_time_loop(tg_user_id, 1)
        photo_path = "uploads/Kopernik.png"
        photo = FSInputFile(photo_path)
        await bot.send_photo(chat_id=chat_id, photo=photo)
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Вернуться назад', callback_data=f"not_risk")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в take_puppy: %s", e)


@router.callback_query(lambda call: call.data == "not_risk")
async def not_risk(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id = callback.message.chat.id
        txt1 = ("Вы в заброшенной лаборатории дяди. "
                "Тут очень мало света, но Вам удается что-то разглядеть."
                " Здесь Вы видите несколько приборов, записную книжку с информацией о путешествиях во времени и чертежи. "
                "\nЧто Вы делаете?")

        msg1 = await bot.send_message(chat_id=chat_id, text=txt1, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Изучить записную книжку', callback_data="devices")],
            [InlineKeyboardButton(text='Посмотреть чертеж', callback_data="drafts")],
            [InlineKeyboardButton(text='Искать другие улики', callback_data="other_clues_5")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg1.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в not_risk: %s", e)


@router.callback_query(lambda call: call.data == "devices")
async def devices_callback(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = int(callback.message.chat.id)
        photo_path = "uploads/page_1.JPG"
        photo = FSInputFile(photo_path)
        msg = await bot.send_photo(chat_id=chat_id, photo=photo, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Вернуться назад', callback_data="not_risk")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в devices_callback: %s", e)


@router.callback_query(lambda call: call.data == "drafts")
async def drafts(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        photo_path = "uploads/device.JPG"
        photo = FSInputFile(photo_path)
        msg = await bot.send_photo(chat_id=chat_id, photo=photo, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Вернуться назад', callback_data="not_risk")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в drafts: %s", e)


@router.callback_query(lambda call: call.data == "other_clues_5")
async def other_clues_5(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        txt = ("Вы нашли информацию о том, как ваш дядя попал в прошлое, "
               "и кто мог бы ему помочь. В записках дяди упоминается "
               "«Хранитель Времени», который, по его мнению, может помочь ему вернуться."
               " \nВам нужно найти его.")
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Изучить информацию о Хранителе Времени", callback_data="searchTS")],
            [InlineKeyboardButton(text="Искать Хранителя Времени самостоятельно", callback_data="myselfTS")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в other_clues_5: %s", e)


@router.callback_query(lambda call: call.data == "myselfTS")
async def myself(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        txt = ('В записках дяди вы обнаруживаете, что "Ключ Времени" '
               '- это не просто артефакт, а ключ к особой точке во времени, '
               'связанной с Хранителем Времени. Вам нужно найти это место, где использовать его.')
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Использовать информацию из дневника", callback_data="use_diary")],
            [InlineKeyboardButton(text="Искать прибор самостоятельно в другом месте", callback_data="myselfD")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в myself: %s", e)


@router.callback_query(lambda call: call.data == "myselfD")
async def myselfD(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        txt = "Вы нашли прибор, отдалённо напоминающий нужное устройство. Однако он может быть опасен"
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Использовать этот прибор", callback_data="use_device")],
            [InlineKeyboardButton(text="Не рисковать, не использовать прибор", callback_data="not_risk_D")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в myselfD: %s", e)


@router.callback_query(lambda call: call.data == "use_device")
async def use_device(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        txt = "К сожалению это оказался не тот прибор. При его запуске произошел взрыв и Вы погибли\n💀💀💀"
        msg = await bot.send_message(chat_id=chat_id, text=txt)
        await database.clear_artefacts_time_loop(chat_id)
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
        await database.clear_artefacts_time_loop(tg_user_id)
        await unsuccess_final_rate(callback.message, 2)
    except Exception as e:
        logger.error("Произошла ошибка в use_device: %s", e)


@router.callback_query(lambda call: call.data == "not_risk_D")
async def not_risk_D(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        txt = "Прибор Вам немного напомнил бомбу и Вы решили не рисковать"
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Использовать информацию из дневника", callback_data="use_diary")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в not_risk_D: %s", e)


@router.callback_query(lambda call: call.data == "use_diary")
async def use_diary(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        artefacts = await database.get_artefacts_time_loop(tg_user_id)
        txt = "В дневнике Вы нашли это фото.\n Благодаря ему Вы нашли прибор Вашего дяди"
        photo_path = "uploads/Location_device.JPG"
        photo = FSInputFile(photo_path)
        msg = await bot.send_message(chat_id=chat_id, text=txt)
        pht = await bot.send_photo(chat_id=chat_id, photo=photo)
        if artefacts['key']:
            txt2 = ("Вы нашли прибор, где «Ключ Времени» может открыть временную аномалию. "
                    "После того, как вы воспользовались прибором, повернув ключ, "
                    "Вас встречает Хранитель Времени.")
            msg2 = await bot.send_message(chat_id=chat_id, text=txt2,
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                              [InlineKeyboardButton(text="Заговорить с Хранителем времени",
                                                                    callback_data="talkTS")],
                                              [InlineKeyboardButton(text="Попытаться вернуть дядю самостоятельно",
                                                                    callback_data="myselfUncle")]
                                          ]))
            await safely_delete_last_message(tg_user_id, chat_id)
            await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
            await database.set_last_message_by_user_id(tg_user_id, msg2.message_id)
            await database.set_last_message_by_user_id(tg_user_id, pht.message_id)
        else:
            txt2 = ("К сожалению, "
                    "Вы не смогли найти «Ключ Времени». "
                    "Вы не можете запустить прибор. Вы не смогли спасти Вашего дядю.")
            msg2 = await bot.send_message(chat_id=chat_id, text=txt2)
            await database.clear_artefacts_time_loop(chat_id)
            await unsuccess_final_rate(callback.message, 2)
            await safely_delete_last_message(tg_user_id, chat_id)
            await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
            await database.set_last_message_by_user_id(tg_user_id, msg2.message_id)
            await database.set_last_message_by_user_id(tg_user_id, pht.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в use_diary: %s", e)


@router.callback_query(lambda call: call.data == "searchTS")
async def searchTS(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        photo_path = "uploads/page_2.JPG"
        photo = FSInputFile(photo_path)
        txt = ("Вы нашли прибор, где «Ключ Времени» может открыть "
               "временную аномалию. После того, как вы воспользовались прибором, "
               "повернув ключ, Вас встречает Хранитель Времени.")
        msg = await bot.send_message(chat_id=chat_id, text="В дневнике Вы находите следующую запись")
        pht = await bot.send_photo(chat_id=chat_id, photo=photo, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Найти прибор", callback_data="use_diary")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
        await database.set_last_message_by_user_id(tg_user_id, pht.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в searchTS: %s", e)


@router.callback_query(lambda call: call.data == "talkTS")
async def talkTS(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        txt = ("Хранитель:\n Приветствую тебя, я полагаю твое появление здесь связанно с тем, "
               "чтобы воспользоваться «Ключом времени». Я должен убедиться, "
               "что ты достоин моей помощи. Тебе нужно будет ответить на "
               "3 вопроса и у тебя будет 4 попытки на каждый вопрос. "
               "Справишься - я помогу тебе, иначе ты будешь страдать")
        msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Согласиться ответить на вопросы", callback_data="question1")],
            [InlineKeyboardButton(text="Проигнорировать и самостоятельно спасти Дядю", callback_data="myselfUncle")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в talkTS: %s", e)


@router.callback_query(lambda call: call.data == "question1")
async def question1(callback: CallbackQuery, state: FSMContext):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        txt = ("Что течет, но не имеет ни источника, ни устья? "
               "Что можно потратить, но нельзя вернуть? "
               "Что все имеют, но никому не принадлежит?")
        answer = "время"
        msg = await bot.send_message(chat_id=chat_id, text=txt)
        await state.set_state(TimeLoop.Question1)
        await state.update_data(question1=1)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в question1: %s", e)


@router.message(TimeLoop.Question1)
async def question2(message: Message, state: FSMContext):
    try:
        # tg_user_id: int = int(message.from_user.id)
        chat_id: int = message.chat.id
        ans = "время"
        user_ans = message.text.lower().translate(str.maketrans('', '', string.punctuation)).replace(' ', '')
        user_data = await state.get_data()
        tries = user_data.get("question1", 1)

        if user_ans != ans:
            if tries >= 4:
                msg = await bot.send_message(chat_id=chat_id, text=f"Не верно! У Вас не осталось попыток")
                await unsuccessful(message)
                #await state.set_state(TimeLoop.Unsuccessful)
                await state.clear()
            else:
                msg = await bot.send_message(chat_id=chat_id, text=f"Не верно! Осталось {4 - tries} попыток")
                if tries == 3:
                    text = "Вот тебе подсказка:\nВлюбленные этого не наблюдают"
                    msg_tip = await bot.send_message(chat_id=chat_id, text=text)
                    await database.set_last_message_by_user_id(chat_id, msg_tip.message_id)
                await state.update_data(question1=tries + 1)
                await database.inc_first_q_tip_time_loop(chat_id)
        else:
            msg = await bot.send_message(chat_id=chat_id, text="Правильно!")
            txt = "Что есть и было, но никогда не настанет?"
            msg2 = await bot.send_message(chat_id=chat_id, text=txt)
            await state.set_state(TimeLoop.Question2)
            await state.update_data(question2=1)
            await database.set_last_message_by_user_id(chat_id, msg2.message_id)

        await database.set_last_message_by_user_id(chat_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в question2: %s", e)


@router.message(TimeLoop.Question2)
async def question3(message: Message, state: FSMContext):
    try:
        # tg_user_id: int = int(message.from_user.id)
        chat_id: int = message.chat.id
        ans1 = "вчера"
        ans2 = "вчерашнийдень"
        user_ans = message.text.lower().translate(str.maketrans('', '', string.punctuation)).replace(' ', '')
        user_data = await state.get_data()
        tries = user_data.get("question2", 1)

        if user_ans != ans1 and user_ans != ans2:
            if tries >= 4:
                msg = await bot.send_message(chat_id=chat_id, text="Не верно! У Вас не осталось попыток..")
                await unsuccessful(message)
                # await state.set_state(TimeLoop.Unsuccessful)
                await state.clear()
            else:
                msg = await bot.send_message(chat_id=chat_id, text=f"Не верно! Осталось {4 - tries} попыток")
                if tries == 3:
                    text = "Вот тебе подсказка:\nУ каждого человека сегодня, этот момент уже прошел."
                    msg_tip = await bot.send_message(chat_id=chat_id, text=text)
                    await database.set_last_message_by_user_id(chat_id, msg_tip.message_id)
                await state.update_data(question2=tries + 1)
                await database.inc_second_q_tip_time_loop(chat_id)
        else:
            msg = await bot.send_message(chat_id=chat_id, text="Правильно!")
            txt = "Что является ключом, к пониманию всего вокруг, что нас окружает?"
            msg2 = await bot.send_message(chat_id=chat_id, text=txt)
            await state.set_state(TimeLoop.Question3)
            await state.update_data(question3=1)
            await database.set_last_message_by_user_id(chat_id, msg2.message_id)

        await database.set_last_message_by_user_id(chat_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в question3: %s", e)


@router.message(TimeLoop.Question3)
async def last_question(message: Message, state: FSMContext):
    try:
        # tg_user_id: int = int(message.from_user.id)
        chat_id: int = message.chat.id
        ans1 = "сознание"
        ans2 = "осознание"
        user_ans = message.text.lower().translate(str.maketrans('', '', string.punctuation)).replace(' ', '')
        user_data = await state.get_data()
        tries = user_data.get("question3", 1)

        if user_ans != ans1 and user_ans != ans2:
            if tries >= 4:
                msg = await bot.send_message(chat_id=chat_id, text="Не верно! У Вас не осталось попыток")
                await unsuccessful(message)
                # await state.set_state(TimeLoop.Unsuccessful)
                await state.clear()
            else:
                msg = await bot.send_message(chat_id=chat_id, text=f"Не верно! Осталось {4 - tries} попыток")
                if tries == 3:
                    text = "Вот тебе подсказка:\nВнутри каждого из нас, это есть, в основном, это в голове."
                    msg_tip = await bot.send_message(chat_id=chat_id, text=text)
                    await database.set_last_message_by_user_id(chat_id, msg_tip.message_id)
                await state.update_data(question3=tries + 1)
                await database.inc_third_q_tip_time_loop(chat_id)
        else:
            msg = await bot.send_message(chat_id=chat_id, text="Правильно!")
            txt = "Хранитель:\n Ты достоин, воспользоваться временной аномалией, я разрешаю попасть тебе туда, куда тебе нужно"
            msg2 = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Воспользоваться аномалией", callback_data="anomaly")],
                [InlineKeyboardButton(text="Отказаться", callback_data="rejection")]
            ]))
            await state.clear()
            await database.set_last_message_by_user_id(chat_id, msg2.message_id)
        await database.set_last_message_by_user_id(chat_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в last_question: %s", e)


@router.callback_query(lambda call: call.data == "anomaly")
async def anomaly(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        user_data = await database.get_user_data(tg_user_id)
        name = user_data['username']
        txt = (f"Дядя:\nПривет, {name}, я рад, что ты смог разобраться во "
               "всем и спасти своего любимого дядю. Я очень тебе благодарен. "
               "Мне нужно тебе столько всего рассказать и показать, я надеюсь, "
               "что мы будем вместе путешествовать, изучать разные временные промежутки "
               "и погружаться в историю планеты.")
        await database.clear_artefacts_time_loop(chat_id)
        msg = await bot.send_message(chat_id=chat_id, text=txt)
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
        await success_final_rate(callback.message, 2)
    except Exception as e:
        logger.error("Произошла ошибка в anomaly: %s", e)


@router.callback_query(lambda call: call.data == "rejection")
async def rejection(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        txt = ("Вы отказались от возможности спасти Вашего дядю..\n"
               "Хранитель времени пропадает, и Вам больше "
               "не удается включить прибор заново.")
        msg = await bot.send_message(chat_id=chat_id, text=txt)
        await database.clear_artefacts_time_loop(chat_id)
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
        await unsuccess_final_rate(callback.message, 2)
    except Exception as e:
        logger.error("Произошла ошибка в rejection: %s", e)


@router.callback_query(lambda call: call.data == "myselfUncle")
async def myselfUncle(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        txt = ("Вы решили проигнорировать Хранителя Времени, "
               "и просто запустить прибор, к сожалению, прибор не сработал, "
               "без помощи Хранителя, вас засосало в прошлое к вашему дяде, и "
               "теперь вы оба находитесь в потерянном времени.")
        msg = await bot.send_message(chat_id=chat_id, text=txt)
        await database.clear_artefacts_time_loop(chat_id)
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
        await unsuccess_final_rate(callback.message, 2)
    except Exception as e:
        logger.error("Произошла ошибка в myselfUncle: %s", e)


async def unsuccessful(message: Message):
    try:
        # tg_user_id: int = int(message.from_user.id)
        chat_id: int = message.chat.id
        txt = ("Вам не удалось отгадать загадку с третьего раза и Хранитель молча исчез.\n"
               "Прибор больше не включается, Вам не удалось спасти Вашего дядю..")
        msg = await bot.send_message(chat_id=chat_id, text=txt)
        await database.clear_artefacts_time_loop(chat_id)
        await safely_delete_last_message(chat_id, chat_id)
        await database.set_last_message_by_user_id(chat_id, msg.message_id)
        await unsuccess_final_rate(message, 2)
    except Exception as e:
        logger.error("Произошла ошибка в unsuccessful: %s", e)


async def unsuccess_final_rate(message: Message, quest_id):
    try:
        chat_id: int = int(message.chat.id)
        user_data = await database.get_user_data(chat_id)
        name = user_data['username']
        quest_data = await database.get_quest_data_by_id(quest_id)
        quest_name = quest_data['name']
        txt2 = (f"{name}, к сожалению, Вам не удалось пройти квест «{quest_name}» на счастливую концовку\n"
                f"Вы всегда можете попробовать еще раз!\n")
        msg = await bot.send_message(chat_id=chat_id, text=txt2, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Пройти заново", callback_data="again_time_loop")],
            [InlineKeyboardButton(text="Маркет", callback_data="market")],
            [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
        ]))
        await database.set_last_message_by_user_id(chat_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в unsuccess_final_rate: %s", e)


async def success_final_rate(message: Message, quest_id):
    try:
        chat_id: int = int(message.chat.id)
        user_data = await database.get_user_data(chat_id)
        name = user_data['username']
        quest_data = await database.get_quest_data_by_id(quest_id)
        quest_name = quest_data['name']
        timeloop_data = await database.get_artefacts_time_loop(chat_id)
        rate_count = timeloop_data['rate_count']
        if rate_count == 0:
            txt = f"Поздравляю, {name}, Вы прошли квест «{quest_name}»\nОцените пожалуйста квест"
            msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="   ❤️   ", callback_data="final_like:2")],
                [InlineKeyboardButton(text="   🙁   ", callback_data="final_dislike:2")]
            ]))
            await database.inc_rate_count_time_loop(chat_id)
        else:
            if rate_count + 1 == 2:
                txt = f"Поздравляю, {name}, Вы прошли квест «{quest_name}» во {rate_count + 1} раз!"
            else:
                txt = f"Поздравляю, {name}, Вы прошли квест «{quest_name}» в {rate_count + 1} раз!"
            msg = await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
            ]))
            await database.inc_rate_count_time_loop(chat_id)

        await database.set_last_message_by_user_id(chat_id, msg.message_id)

    except Exception as e:
        logger.error("Произошла ошибка в success_final_rate: %s", e)


@router.callback_query(lambda query: query.data.startswith("final_like:"))
async def final_like(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        quest_id = int(callback.data.split(':')[1])
        await database.quest_mark(mark="like", quest_id=quest_id)
        txt = "Спасибо за Вашу оценку.\nЕсли у Вас есть какие-то предложения или Вы нашли недочеты, напишите пожалуйста на профиль в описании бота."
        msg = await bot.send_message(tg_user_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Маркет", callback_data="market")],
            [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в final_like: %s", e)


@router.callback_query(lambda query: query.data.startswith("final_dislike:"))
async def final_dislike(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        chat_id: int = callback.message.chat.id
        quest_id = int(callback.data.split(':')[1])
        await database.quest_mark(mark="dislike", quest_id=quest_id)
        txt = "Спасибо за Вашу оценку!\n Нам жаль, что Вам не понравилось..\nЕсли у Вас есть какие-то предложения или Вы нашли недочеты, напишите пожалуйста на профиль в описании бота."
        msg = await bot.send_message(tg_user_id, text=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Маркет", callback_data="market")],
            [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
        ]))
        await safely_delete_last_message(tg_user_id, chat_id)
        await database.set_last_message_by_user_id(tg_user_id, msg.message_id)
    except Exception as e:
        logger.error("Произошла ошибка в final_dislike: %s", e)


@router.callback_query(lambda call: call.data == "again_time_loop")
async def again_time_loop(callback: CallbackQuery):
    try:
        await quest(callback.message)
    except Exception as e:
        logger.error("Произошла ошибка в again_time_loop: %s", e)


# ----------------------------------------------------------

@router.callback_query(lambda call: call.data == "main_menu")
async def MMenu(callback: CallbackQuery):
    try:
        tg_user_id: int = int(callback.from_user.id)
        await main_menu(tg_user_id)
    except Exception as e:
        logger.error("Произошла ошибка в MMenu: %s", e)


async def on_startup():
    try:
        await database.connect()
    except Exception as e:
        logger.error("Произошла ошибка в on_startup: %s", e)


# Запуск процесса
async def main():
    try:
        dp.startup.register(on_startup)
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error("Произошла ошибка в main: %s", e)


if __name__ == '__main__':  # выполняется, если код вызван непосредственно
    try:
        asyncio.run(main())
        # print("[Bot Running] Бот включён")
    except Exception as e:
        logger.error("Произошла ошибка в __name__: %s", e)
