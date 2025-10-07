import asyncio
import os
import sys
from typing import Optional

from app.agent import root_agent
from app.runner_config import run_with_memory


async def _amain(user_message: str, user_id: Optional[str] = None, session_id: Optional[str] = None):
    uid = user_id or os.environ.get("MMVN_USER_ID", "user")
    sid = session_id or os.environ.get("MMVN_SESSION_ID", "session")
    resp = await run_with_memory(root_agent, uid, sid, user_message, app_name="mmvn_app")
    print(resp or "")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.run_agent_with_hooks "
              "\"<user message>\" [<user_id>] [<session_id>]")
        sys.exit(1)
    msg = sys.argv[1]
    uid = sys.argv[2] if len(sys.argv) >= 3 else None
    sid = sys.argv[3] if len(sys.argv) >= 4 else None
    asyncio.run(_amain(msg, uid, sid))


if __name__ == "__main__":
    main()


