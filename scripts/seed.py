import asyncio
from decimal import Decimal
from uuid import UUID

from app.config import Settings
from app.infrastructure.database.database import Database
from app.infrastructure.database.models import User


DEMO_USERS = (
    UUID("11111111-1111-1111-1111-111111111111"),
    UUID("22222222-2222-2222-2222-222222222222"),
)


async def seed() -> None:
    settings = Settings()
    db = Database(settings.database_url)

    try:
        async with db.session_factory() as session:
            async with session.begin():
                for user_id in DEMO_USERS:
                    user = await session.get(User, user_id)

                    if user is None:
                        session.add(
                            User(
                                id=user_id,
                                ai_balance=Decimal("1000.00"),
                            )
                        )
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(seed())