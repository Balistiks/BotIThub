import os.path

from aiogram import Bot, Dispatcher, types, executor
import config
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import sqlite3
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import pandas

bot = Bot(token=config.TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


db = sqlite3.connect("datebase/datebase.db")
cur = db.cursor()


directorate = []


class AddEvent(StatesGroup):
    name = State()
    number = State()
    addQuestionState = State()
    addAnswersQuestionState = State()


class StateUser(StatesGroup):
    wait = State()
    name = State()
    phoneNumber = State()
    answers = State()
    finishAnswer = State()


@dp.message_handler(commands="start")
async def start(message: types.Message):
    if message.chat.id in directorate:
        directorate_keyboard = types.InlineKeyboardMarkup()
        directorate_keyboard.add(types.InlineKeyboardButton(text="Добавить вопрос", callback_data="addEvent"))
        directorate_keyboard.add(types.InlineKeyboardButton(text="Получить ответы", callback_data="getAnswers"))
        await message.answer("Что будем делать?", reply_markup=directorate_keyboard)
    else:
        await StateUser.name.set()
        await message.answer("Доброго времени суток!\n"
                                "На связи служба заботы IT-колледжа ВВГУ (IThub Владивосток)\n"
                                "Как вас зовут?")


@dp.message_handler(state=StateUser.name)
async def getName(message: types.Message, state: FSMContext):
    await state.update_data(first_name=message.text)
    await StateUser.next()
    await message.answer("Напишите номер телефона")


@dp.message_handler(state=StateUser.phoneNumber)
async def getPhoneNumber(message: types.Message, state: FSMContext):
    await state.update_data(phone_number=message.text)
    data = await state.get_data()
    cur.execute("""
    INSERT INTO Users (TGId, FirstName, PhoneNumber)
    VALUES
    (
        ?,
        ?,
        ?
    )
    """, (message.chat.id, data['first_name'], message.text,))
    db.commit()
    cur.execute("""
    SELECT EventTitle FROM Events
    """)
    events = cur.fetchall()
    event_keyboard = types.InlineKeyboardMarkup()
    for i in events:
        event_keyboard.add(types.InlineKeyboardButton(text=i[0], callback_data=f"event_{i[0]}"))
    await state.finish()
    await message.answer(text="На каком мероприятии вы были?", reply_markup=event_keyboard)


@dp.callback_query_handler()
async def callbackHandler(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup(reply_markup=None)
    if call.data == "addEvent":
        await AddEvent.name.set()
        await call.message.answer(text="Напишите название мероприятия")
    elif call.data[0:5] == "event":
        await state.update_data(event=call.data[6::1])
        await state.update_data(answer=0)
        await getAnswer(message=call.message, state=state, event_title=call.data[6::1])
    elif call.data == "getAnswers":
        if os.path.exists('Excel/Users.xlsx') and os.path.exists('Excel/Answers.xlsx'):
            os.remove('Excel/Users.xlsx')
            os.remove('Excel/Answers.xlsx')

        df1 = pandas.read_sql('SELECT * FROM Answers', db)
        df2 = pandas.read_sql('SELECT * FROM Users', db)

        df1.to_excel('Excel/Answers.xlsx')
        df2.to_excel('Excel/Users.xlsx')

        await call.message.answer_document(open('Excel/Users.xlsx', 'rb'))
        await call.message.answer_document(open('Excel/Answers.xlsx', 'rb'))
        await start(call.message)

    elif call.data.split("_")[1] == "answer":
        data = await state.get_data()
        cur.execute("""
        INSERT INTO Answers (UserId, EventId, "Имя", "Мероприятие", "Вопрос", "Ответ")
        VALUES
        (
            ?,
            (SELECT Id FROM Events WHERE EventTitle=?),
            (SELECT FirstName FROM Users WHERE TGId=?),
            ?,
            ?,
            ?
        )
        """, (call.message.chat.id, data['event'], call.message.chat.id,
              data['event'], data['question'], call.data.split("_")[2]))
        db.commit()
        await getAnswer(call.message, state, data['event'])


async def getAnswer(message, state, event_title):
    cur.execute("""
                SELECT NumberOfQuestions, Id FROM Events WHERE EventTitle=?
                """, (event_title,))
    event = cur.fetchall()
    await state.update_data(number_of_questions=event[0][0])
    data = await state.get_data()
    if data['answer'] == data['number_of_questions']:
        await StateUser.finishAnswer.set()
        await message.answer("Спасибо! Напиши мне, что вам особенно понравилось или не понравилось - "
                             "передам команде")
    else:
        cur.execute("""
            SELECT "Вопрос", "Ответы" FROM EventsQuestions WHERE EventId=? AND Number=?
            """, (event[0][1], data['answer'] + 1,))
        questions_answers = cur.fetchall()
        question = questions_answers[0][0]
        await state.update_data(question=question)
        answers = questions_answers[0][1].split(", ")
        keyboard_answers = types.InlineKeyboardMarkup()
        data = await state.get_data()
        for i in answers:
            keyboard_answers.add(types.InlineKeyboardButton(text=i,
                                                            callback_data=f"{data['answer'] + 1}_answer_{i}"))
        await state.update_data(answer=data['answer'] + 1)
        await message.answer(question, reply_markup=keyboard_answers)


@dp.message_handler(state=StateUser.finishAnswer)
async def getFinishAnswer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.finish()
    cur.execute("""
    INSERT INTO Answers (UserId, EventId, "Имя", "Мероприятие", "Вопрос", "Ответ")
    VALUES
    (
        ?,
        (SELECT Id FROM Events WHERE EventTitle=?),
        (SELECT FirstName FROM Users WHERE TGId=?),
        ?,
        ?,
        ?
    )
    """, (message.chat.id, data['event'], message.chat.id,
          data['event'], "Спасибо! Напиши мне, что вам особенно понравилось или не понравилось - "
                         "передам команде",
          message.text))
    db.commit()
    await message.answer("Спасибо, что нашёл минутку и прошёл опрос!\n"
                         "19 февраля (вс) в 11:00 состоится наш День открытых дверей по адресу: Гоголя 39a\n"
                         "Будем тебя ждать!\n"
                         "Оставайся на связи и следи за нашими соц. сетями:\n"
                         "Telegram - https://t.me/vvsuithub\n"
                         "VK - https://vk.com/vvsuithub\n"
                         "YouTube - https://youtube.com/@vvsuithub\n"
                         "Наш сайт - https://vvsu.ithub.ru/")


@dp.message_handler(state=AddEvent.name)
async def addEventName(message: types.Message, state: FSMContext):
    await state.update_data(nameEvent=message.text)
    await AddEvent.next()
    await message.answer(text="Сколько вопросов будет?")


@dp.message_handler(state=AddEvent.number)
async def addNumberQuestions(message: types.Message, state: FSMContext):
    numberQuestions = int(message.text)
    await state.update_data(number=1)
    await state.update_data(numberQuestions=numberQuestions)
    data = await state.get_data()
    cur.execute("INSERT INTO Events (EventTitle, NumberOfQuestions) VALUES (?, ?)", (data["nameEvent"],
                                                                                     numberQuestions,))
    db.commit()
    await AddEvent.addQuestionState.set()
    await message.answer("Напишите вопрос")


@dp.message_handler(state=AddEvent.addQuestionState)
async def addQuestion(message: types.Message, state: FSMContext):
    await state.update_data(question=message.text)
    await AddEvent.addAnswersQuestionState.set()
    await message.answer("Напишите варианты ответа через запятую и пробел!\n"
                         "Пример: да, нет, может быть")


@dp.message_handler(state=AddEvent.addAnswersQuestionState)
async def addAnswersQuestion(message: types.Message, state: FSMContext):
    data = await state.get_data()
    number_questions = data['numberQuestions']
    number = data['number']
    event_title = data['nameEvent']
    question = data['question']
    cur.execute("""
            INSERT INTO EventsQuestions (EventId, "Вопрос", "Ответы", Number)
            VALUES
            (
                (SELECT Id FROM Events WHERE EventTitle = ?),
                ?,
                ?,
                ?
            )
            """, (event_title, question, message.text, number,))
    db.commit()
    if number == number_questions:
        await message.answer("Мероприятие добавлено")
        await start(message)
    else:
        number += 1
        await state.update_data(number=number)
        await message.answer("Вопрос добавлен")
        await AddEvent.addQuestionState.set()
        await message.answer("Напишите следующий вопрос")

executor.start_polling(dp, skip_updates=True)
