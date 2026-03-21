import sys

from printpulse.app import run


def main():
    try:
        run(sys.argv[1:])
    except KeyboardInterrupt:
        print("\n[ABORT] User cancelled.")
        sys.exit(130)


if __name__ == "__main__":
    main()
