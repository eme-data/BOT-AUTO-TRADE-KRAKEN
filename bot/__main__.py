"""Entry point: python -m bot"""

import asyncio
import sys

from bot.user_bot_manager import UserBotManager


async def main() -> None:
    mgr = UserBotManager()
    try:
        await mgr.start()
    except KeyboardInterrupt:
        pass
    finally:
        await mgr.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
        sys.exit(0)
