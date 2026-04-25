from __future__ import annotations

from .train_one_model import main


if __name__ == "__main__":
    import sys

    # Default to BiLSTM if user runs this file directly.
    if "--kind" not in sys.argv:
        sys.argv = [sys.argv[0], "--kind", "bilstm", *sys.argv[1:]]
    raise SystemExit(main())

