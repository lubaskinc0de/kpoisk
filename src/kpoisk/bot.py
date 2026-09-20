import asyncio
import logging
import operator
import os
import sys
from dataclasses import dataclass
from os import getenv
from pathlib import Path
from typing import Any

import dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.filters.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import (
    Dialog,
    DialogManager,
    StartMode,
    Window,
    setup_dialogs,
)
from aiogram_dialog.widgets.kbd import (
    ScrollingGroup,
    Select,
    SwitchTo,
)
from aiogram_dialog.widgets.text import Const, Format
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from kpoisk.parser import (
    Base,
    FilmruMovieParser,
    MoviesRepository,
    create_sessionmaker,
)

dotenv.load_dotenv()
TOKEN = getenv("BOT_TOKEN")
dp = Dispatcher(storage=MemoryStorage())
DB_PATH = Path("./db.json")


class MySG(StatesGroup):
    main = State()
    movie = State()


async def get_movie_data(sessionmaker: sessionmaker[Session], **kwargs):
    with sessionmaker() as session:
        movies = MoviesRepository(session).get_all()

    return {
        "movies": movies,
        "count": len(movies),
    }


async def on_movie_selected(
    callback: CallbackQuery,
    widget: Any,
    dialog_manager: DialogManager,
    item_id: str,
):
    dialog_manager.dialog_data["movie_id"] = item_id
    await dialog_manager.switch_to(MySG.movie)


async def get_selected_movie(
    dialog_manager: DialogManager,
    sessionmaker: sessionmaker[Session],
    **kwargs,
):
    movie_id = dialog_manager.dialog_data.get("movie_id")
    if movie_id is None:
        return {
            "title": "Фильм не выбран",
            "year": "—",
            "rating": "—",
            "genre": "—",
            "url": "https://www.film.ru/",
        }

    with sessionmaker() as session:
        movie = MoviesRepository(session).get_by_id(movie_id)

    return {
        "title": movie.title,
        "year": movie.year,
        "rating": movie.rating if movie.rating is not None else "Нет оценки",
        "genre": movie.genre,
        "url": f"https://www.film.ru{movie.url}",
    }


movies_select = Select(
    Format("{item.title} ({item.year})"),
    id="s_movies",
    item_id_getter=operator.attrgetter("id"),
    items="movies",
    on_click=on_movie_selected,
)


movies_kbd = ScrollingGroup(
    movies_select,
    id="movies_pages",
    width=1,
    height=8,
)


main_window = Window(
    Format("<b>Топ 500 лучших фильмов</b>\n\nВсего фильмов: {count}\nВыберите фильм:"),
    movies_kbd,
    state=MySG.main,
    getter=get_movie_data,
)


movie_window = Window(
    Format(
        "<b>{title}</b>\n\n"
        "<b>Год:</b> {year}\n"
        "<b>Рейтинг:</b> {rating}\n"
        "<b>Жанр:</b> {genre}\n\n"
        '<a href="{url}">Открыть на Film.ru</a>'
    ),
    SwitchTo(
        Const("Назад к списку"),
        id="back_to_movies",
        state=MySG.main,
    ),
    state=MySG.movie,
    getter=get_selected_movie,
)


dialog = Dialog(
    main_window,
    movie_window,
)


@dp.message(Command("start"))
async def start(
    message: Message,
    dialog_manager: DialogManager,
):
    await dialog_manager.start(
        MySG.main,
        mode=StartMode.RESET_STACK,
    )


@dataclass
class DbConfig:
    user: str
    password: str
    host: str
    db: str


async def main() -> None:
    config = DbConfig(
        os.getenv("DB_USER", "postgres"),
        os.getenv("DB_PASS", "postgres"),
        os.getenv("DB_HOST", "localhost"),
        os.getenv("DB_NAME", "postgres"),
    )

    # u need to use async sqla in production =)
    engine = create_engine(
        f"postgresql+psycopg://{config.user}:{config.password}@{config.host}:5432/{config.db}",
        echo=False,
    )
    parser = FilmruMovieParser()
    session_maker = create_sessionmaker(engine)
    Base.metadata.create_all(engine)

    with session_maker() as session:
        repo = MoviesRepository(session)
        movies = repo.get_all()
        if not movies:
            movies = parser.get_top()
            repo.save(movies)

    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
        session=(
            AiohttpSession(proxy=os.getenv("PROXY_URL", "http://127.0.0.1:10808"))
            if os.getenv("USE_PROXY") == "true"  # телега блокируется в рф
            else None
        ),
    )

    dp.include_router(dialog)
    dp["sessionmaker"] = session_maker
    setup_dialogs(dp)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
    )

    asyncio.run(main())
