import sys
import traceback


def log_error(context: str) -> None:
    print(f"[ERROR {context}]", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
