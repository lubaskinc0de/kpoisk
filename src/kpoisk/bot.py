import asyncio
import logging
import operator
import os
import sys
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

from kpoisk.parser import FilmruMovieParser, Movie, MoviesTopRepository

dotenv.load_dotenv()
TOKEN = getenv("BOT_TOKEN")
dp = Dispatcher(storage=MemoryStorage())
DB_PATH = Path("./db.json")


class MySG(StatesGroup):
    main = State()
    movie = State()


def load_movies() -> list[Movie]:
    parser = FilmruMovieParser()
    repo = MoviesTopRepository(DB_PATH)

    movies = repo.get_all()

    if not movies:
        movies = parser.get_top()
        repo.save(movies)

    return movies


async def get_movie_data(**kwargs):
    movies = load_movies()
    return {
        "movies": list(enumerate(movies)),
        "count": len(movies),
    }


async def on_movie_selected(
    callback: CallbackQuery,
    widget: Any,
    dialog_manager: DialogManager,
    item_id: str,
):
    movie_index = int(item_id)
    dialog_manager.dialog_data["movie_index"] = movie_index
    await dialog_manager.switch_to(MySG.movie)


async def get_selected_movie(
    dialog_manager: DialogManager,
    **kwargs,
):
    movie_index = dialog_manager.dialog_data.get("movie_index")
    if movie_index is None:
        return {
            "title": "Фильм не выбран",
            "year": "—",
            "rating": "—",
            "genre": "—",
            "url": "https://www.film.ru/",
        }

    movies = load_movies()
    if movie_index >= len(movies):
        return {
            "title": "Фильм не найден",
            "year": "—",
            "rating": "—",
            "genre": "—",
            "url": "https://www.film.ru/",
        }

    movie = movies[movie_index]
    return {
        "title": movie.title,
        "year": movie.year,
        "rating": movie.rating if movie.rating is not None else "Нет оценки",
        "genre": movie.genre,
        "url": movie.url,
    }


movies_select = Select(
    Format("{item[1].title} ({item[1].year})"),
    id="s_movies",
    item_id_getter=operator.itemgetter(0),
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
    Format(
        "<b>Топ 500 лучших фильмов</b>\n\nВсего фильмов: {count}\nВыберите фильм:"
    ),
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


async def main() -> None:
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
        session=(
            AiohttpSession(proxy="http://127.0.0.1:10808")
            if os.getenv("USE_PROXY") == "true"  # телега блокируется в рф
            else None
        ),
    )

    dp.include_router(dialog)
    setup_dialogs(dp)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
    )

    asyncio.run(main())
