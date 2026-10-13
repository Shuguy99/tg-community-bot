from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Stopword


class StopwordRepo:
    def __init__(self, session):
        self.session = session

    async def list_words(self, chat_id: int) -> list[str]:
        result = await self.session.execute(select(Stopword.word).where(Stopword.chat_id == chat_id))
        return list(result.scalars())

    async def add(self, chat_id: int, word: str) -> None:
        stmt = (
            insert(Stopword)
            .values(chat_id=chat_id, word=word.strip().lower())
            .on_conflict_do_nothing(index_elements=[Stopword.chat_id, Stopword.word])
        )
        await self.session.execute(stmt)

    async def remove(self, chat_id: int, word: str) -> None:
        await self.session.execute(
            delete(Stopword).where(Stopword.chat_id == chat_id, Stopword.word == word.strip().lower())
        )
