import logging
from dataclasses import dataclass

import requests
from adaptix import Retort
from adaptix.conversion import get_converter
from bs4 import BeautifulSoup
from sqlalchemy import VARCHAR, Engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

logger = logging.getLogger()
retort = Retort()


class Base(DeclarativeBase): ...


@dataclass(frozen=True)
class MovieDTO:
    id: int
    title: str
    year: int
    rating: float | None
    genre: str
    url: str


class MovieModel(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(VARCHAR(50))
    year: Mapped[int] = mapped_column()
    rating: Mapped[float | None] = mapped_column()
    genre: Mapped[str] = mapped_column(VARCHAR(50))
    url: Mapped[str] = mapped_column()


movie_model_to_dto = get_converter(MovieModel, MovieDTO)
movie_dto_to_model = get_converter(MovieDTO, MovieModel)


class FilmruMovieParser:
    def __init__(self) -> None:
        self._base_url = "https://www.film.ru/compilation/500-luchshih-filmov"
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def get_top(self) -> list[MovieDTO]:
        return self._parse_top_page()

    def _parse_top_page(self, page: int = 0) -> list[MovieDTO]:
        resp = requests.get(f"{self._base_url}/page/{page}/nojs", headers=self._headers)

        if resp.status_code == 404:
            return []

        if resp.status_code != 200:
            logger.warning("parser_req_failed, status_code = %d", resp.status_code)
            raise ValueError(f"Parser request failed with status = {resp.status_code}")

        dom = BeautifulSoup(resp.text)
        containers = dom.findAll("div", attrs={"class": "redesign_afisha_movie"})
        if not containers:
            return []

        movies: list[MovieDTO] = []
        logger.info("parser_current_page = %d", page)
        for movie_container in containers:
            title_raw = movie_container.find(
                "div", attrs={"class": "redesign_afisha_movie_main_title"}
            )
            title = title_raw.text.strip()
            url = title_raw.find("a")["href"].strip()
            year = int(
                next(
                    el
                    for el in list(
                        movie_container.find(
                            "div",
                            attrs={"class": "redesign_afisha_movie_main_subtitle"},
                        ).stripped_strings
                    )
                    if el.isdigit()
                )
            )
            genre = (
                movie_container.find(
                    "div", attrs={"class": "redesign_afisha_movie_main_info"}
                )
                .text.strip()
                .split("/")[0]
                .strip()
            )
            rating_raw = (
                movie_container.find(
                    "div", attrs={"title": "Средняя оценка пользователей film.ru"}
                )
                .find("span")
                .text.strip()
            )
            movies.append(
                MovieDTO(
                    id=None,
                    title=title,
                    year=year,
                    rating=float(rating_raw)
                    if "." in rating_raw or rating_raw.isdigit()
                    else None,
                    genre=genre,
                    url=url,
                )
            )
        return movies + self._parse_top_page(page=page + 1)


class MoviesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, movies: list[MovieDTO]) -> None:
        models = [movie_dto_to_model(movie) for movie in movies]
        self._session.add_all(models)
        self._session.commit()

    def get_all(self) -> list[MovieDTO]:
        q = self._session.execute(
            select(MovieModel).order_by(MovieModel.id)
        )
        return [movie_model_to_dto(movie) for movie in q.scalars().all()]

    def get_by_id(self, movie_id: int) -> MovieDTO:
        return movie_model_to_dto(self._session.get(MovieModel, movie_id))


def create_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine)
