"""Local launcher. The token is ephemeral and never stored on disk."""
from __future__ import annotations

import argparse
import os
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description="Piko local-first Windows agent")
    parser.add_argument("command", choices=["serve"], help="Start local control API")
    parser.add_argument("--model", default=os.environ.get("PIKO_REASONING_MODEL", ""),
                        help="Installed Ollama reasoning model (can be configured in Piko)")
    parser.add_argument("--vision-model", help="Installed Ollama vision model (optional)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose an unprivileged TCP port")
    from piko.api import create_app
    from piko.windows import DesktopUnavailable
    try:
        token = os.environ.get("PIKO_CONTROL_TOKEN") or secrets.token_urlsafe(36)
        if len(token) < 24:
            parser.error("Invalid PIKO_CONTROL_TOKEN: at least 24 characters required")
        app = create_app(token=token, reasoning_model=args.model,
                         vision_model=args.vision_model)
    except DesktopUnavailable as exc:
        parser.error(str(exc))
    print("Piko is listening on the local loopback interface only.", flush=True)
    if not os.environ.get("PIKO_CONTROL_TOKEN"):
        print("Paste this one-time token into the Piko desktop app:", flush=True)
        print(token, flush=True)
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
