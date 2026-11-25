"""Makro Studio: çift tıklayınca konsolsuz açılır."""
import ctypes
import multiprocessing
import os
import sys

if sys.version_info < (3, 11):
    ctypes.windll.user32.MessageBoxW(
        None, "Makro Studio için Python 3.11 veya daha yenisi gerekli.\npython.org adresinden indirebilirsin.",
        "Makro Studio", 0x10)
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.app import main  # noqa: E402

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
