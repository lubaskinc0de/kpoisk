import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from adaptix import Retort
from bs4 import BeautifulSoup

logger = logging.getLogger()
retort = Retort()


@dataclass(frozen=True)
class Movie:
    title: str
    year: int
    rating: float | None
    genre: str
    url: str


class FilmruMovieParser:
    def __init__(self) -> None:
        self._base_url = "https://www.film.ru/compilation/500-luchshih-filmov"
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def get_top(self) -> list[Movie]:
        return self._parse_top_page()

    def _parse_top_page(self, page: int = 0) -> list[Movie]:
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

        movies: list[Movie] = []
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
                Movie(
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


class MoviesTopRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _read(self, key: str | None) -> dict[str, Any] | None:
        try:
            with self._db_path.open("r", encoding="utf-8") as fd:
                content = json.load(fd)
        except (FileNotFoundError, json.JSONDecodeError):
            content = {}

        if key is not None:
            return content.get(key)
        return content

    def _write(self, key: str, value: Any, tp: Any) -> None:
        content = self._read(None)
        value_dumped = retort.dump(value, tp)
        with self._db_path.open("w", encoding="utf-8") as fd:
            content[key] = value_dumped
            json.dump(content, fd, ensure_ascii=False, indent=4)

    def save(self, movies: list[Movie]) -> None:
        self._write("movies_top", movies, list[Movie])

    def get_all(self) -> list[Movie]:
        data = self._read("movies_top")
        if data is None:
            return []
        return retort.load(data, list[Movie])
