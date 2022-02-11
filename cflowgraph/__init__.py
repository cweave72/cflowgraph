import shlex
import subprocess
from subprocess import Popen
from time import time

from typing import Union, List, Tuple

from rich.logging import RichHandler
from rich.pretty import pretty_repr as pf

import logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


loglevels = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR
}


def setuplogging(logger: logging.Logger,
                 level: str = 'info',
                 logfile: str = None):

    logger.setLevel(logging.DEBUG)

    if logfile:
        fh = logging.FileHandler(logfile, mode='w')
        fmt = logging.Formatter(
            fmt="[%(levelname)6s] %(name)s: %(message)s")

        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)

    ch = RichHandler(rich_tracebacks=True, show_time=False)
    #ch.setFormatter(logging.Formatter(fmt="[%(name)s] %(message)s"))
    ch.setFormatter(logging.Formatter(fmt="%(message)s"))
    ch.setLevel(loglevels[level])
    logger.addHandler(ch)


def timedfunc(func):
    def wrapped(*args, **kwargs):
        t1 = time()
        result = func(*args, **kwargs)
        t2 = time()
        logger.debug(f"Func {func.__name__} executed in {(t2-t1):.5f} sec")
        return result
    return wrapped


def shell_cmd(cmd: Union[str, List[str]]) -> Tuple[List[str], List[str]]:
    """Executes a shell command.
    Returns a tuple (stdout, stderr) as a list of lines.
    """

    if isinstance(cmd, str):
        cmd = shlex.split(cmd)

    try:
        proc = Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        logger.error(f"Error running command {cmd[0]}. It may not be installed.")
        return None, None

    try:
        s_out, s_err = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        s_out, s_err = proc.communicate()

    # Convert from bytes to str.
    s_out = s_out.decode()
    s_err = s_err.decode()

    stdout = [line for line in s_out.split('\n')]
    stderr = [line for line in s_err.split('\n')]

    return stdout, stderr
