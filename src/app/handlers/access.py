async def owner_chats(deps, user_id: int) -> list:
    from app.repositories.chats import ChatRepo

    async with deps.db.session() as session:
        return await ChatRepo(session).list_by_owner(user_id)


async def is_owner(deps, chat_id: int, user_id: int) -> bool:
    from app.repositories.chats import ChatRepo

    async with deps.db.session() as session:
        chat = await ChatRepo(session).get(chat_id)
        return chat is not None and chat.owner_id == user_id
