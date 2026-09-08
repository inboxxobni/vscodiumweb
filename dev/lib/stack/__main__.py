import os
import sys

sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.stdout.reconfigure(line_buffering=True)

from stack.cli import main

try:
    main(sys.argv[1:])
except KeyboardInterrupt:
    sys.exit(130)
except BrokenPipeError:
    try:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except OSError:
        pass
    sys.exit(0)
