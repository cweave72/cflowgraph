import sys
import click

from typing import Iterable, List
from pathlib import Path

from rich.console import Console

from . import setuplogging, timedfunc, shell_cmd, pf
from .parser import CflowParser

# Use the root logger for the application level.
import logging
logger = logging.getLogger()

paths_always_exclude = (
    'site-packages',
)

console = Console()


@timedfunc
def get_file_list(root: str,
                  excluded_paths: Iterable[str] = None,
                  no_builtin_excludes: bool = False) -> List[Path]:
    """Searches for .c and .h files starting at root.
    """
    # Combine passed user excluded paths with always excluded.
    if no_builtin_excludes:
        excludes = excluded_paths
    else:
        excludes = excluded_paths + paths_always_exclude

    root = Path(root).expanduser()
    logger.debug(f"Getting files from {root}")

    paths = []
    status_msg = "[magenta]Searching paths for files:[/magenta]"
    i = 0
    with console.status(status_msg) as status:
        for p in root.rglob('*.[ch]'):
            for ex in excludes:
                if ex in str(p.parent):
                    #logger.debug(f"Skipping {p}")
                    break
            else:
                paths.append(str(p))
                #logger.debug(f"p={p}")
                if i % 5 == 0:
                    partial_path = ''.join(p.parts[-4:])
                    status.update(
                        f"{status_msg} [blue]({len(paths)})[/blue]: "
                        f"[yellow].../{partial_path}[/yellow]"
                    )

            i += 1

    return paths


@timedfunc
def cflow(paths, **extraopts):
    """Runs cflow command and returns results as a list of strings.
    """
    # Check if cflow is installed.
    stdout, stderr = shell_cmd('cflow --help')
    if stdout is None:
        sys.exit(1)

    cmd = ['cflow']

    required_opts = {
        'print-level': True,
    }
    opts = {**extraopts, **required_opts}

    for opt, value in opts.items():
        if value and not isinstance(value, bool):
            cmd.append(f"--{opt.replace('_', '-')}={value}")
        elif value and isinstance(value, bool):
            cmd.append(f"--{opt.replace('_', '-')}")

    logger.info(f"cli: '{' '.join(cmd)}'")

    logger.debug(f"Appending {len(paths)} paths to cli command")
    for path in paths:
        cmd.append(path.strip())

    logger.debug("Running cflow")
    stdout, stderr = shell_cmd(cmd)
    return stdout, stderr


def get_params(**kwargs):
    """Converts kwargs to an on-the-fly class to allow easier dotted
    access to parameters.
    """

    class Params:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    return Params(**kwargs)


@click.group("cli",
             context_settings=dict(help_option_names=['-h', '--help']),
             invoke_without_command=True)
@click.option('--rootpath', default='.', help="Root path to search for files")
@click.option('--excludepath', multiple=True, help="Excluded path (can be repeated).")
@click.option('--nobuiltin-excludes', is_flag=True, help="Don't use any built-in exclude paths.")
@click.option('--usefile', help="Path to file containing paths ('.' for last written c.files)")
@click.option('--loglevel', default='info', help="Logging level [debug, info, warning, error]")
@click.option('--debug', is_flag=True, help="Shortcut for --loglevel=debug")
@click.pass_context
def cli(ctx, **kwargs):
    """C function call graph generator (using Gnu cflow).
    """
    params = get_params(**kwargs)

    # Force loglevel to debug if shortcut --debug is used.
    if params.debug:
        params.loglevel = 'debug'

    setuplogging(logger, params.loglevel)
    logger.debug(f"Launching cflowgraph. (cli params: {pf(params.__dict__)})")

    ctx.obj = {}
    ctx.obj['cli_params'] = params

    if params.usefile:
        if params.usefile == '.':
            params.usefile = 'c.files'

        if not Path(params.usefile).exists():
            logger.error(f"File {params.usefile} does not exist. "
                         f"Provide --rootpath option.")
            sys.exit(1)
        else:
            # Read file and load the paths list.
            with open(params.usefile) as fp:
                paths = fp.readlines()
                logger.info(f"Read {len(paths)} paths from {params.usefile}")
    else:
        paths = get_file_list(params.rootpath, params.excludepath,
                              params.nobuiltin_excludes)
        logger.info(f"Writing paths to c.files (found {len(paths)} files)")
        with open('c.files', 'w') as f:
            f.write('\n'.join(paths))

    ctx.obj['paths'] = paths


def is_not_none(arg):
    """Returns True if arg is not None.
    """
    return True if arg is not None else False


def is_true(arg):
    return arg


@cli.command()
@click.option('--main', help="Function target to graph.")
@click.option('--depth', help="Call graph depth.")
@click.option('--reverse', is_flag=True, help="Generate reverse graph.")
@click.option('--format', default='raw', help="Format of output: [raw, tree, dot, png, ...] (default is raw).")
@click.option('--pager', is_flag=True, help="Use pager for output.")
@click.option('--stderr', is_flag=True, help="Print cflow stderr output.")
@click.option('--show-signatures', is_flag=True, help="Shows function signatures.")
@click.option('--debug', is_flag=True, help="Shortcut for --loglevel=debug")
@click.pass_context
def run(ctx, **kwargs):
    """Generates the call graph for a function.
    """

    #cli_params = ctx.obj['cli_params']
    params = get_params(**kwargs)

    if params.debug:
        logger.setLevel(logging.DEBUG)
        for h in logger.handlers:
            h.setLevel(logging.DEBUG)

    logger.debug(f"cmd: caller local_params={pf(params.__dict__)}")

    copts = {}
    # Dict to define options from the command to pass through to the cflow
    # wrapper. Each option specifies a callable which will return either True
    # or False to determine whether the option should be passed along.
    cflow_opts_check = {
        # arg: func to call to decide if option should be added.
        'main': is_not_none,
        'depth': is_not_none,
        'reverse': is_true,
    }
    for opt, checker in cflow_opts_check.items():
        if checker(kwargs[opt]):
            copts[opt] = kwargs[opt]

    paths = ctx.obj['paths']
    stdout, stderr = cflow(paths, **copts)

    if len(stdout) < 2:
        logger.info("No results from cflow.")
        return

    if params.format == "raw":
        lines = '\n'.join(stdout)
        if params.pager:
            with console.pager(styles=True):
                console.print(lines)
        else:
            console.print(lines)

    if params.stderr:
        console.print("[sea_green1]cflow: stderr[/sea_green1]")
        for line in stderr:
            console.print(line)

    if params.format == "tree":
        cfp = CflowParser(stdout, main=f"{params.main}()")
        cfp.rich_tree(params.show_signatures, pager=params.pager)


def entrypoint():
    try:
        cli(prog_name="cflowgraph")
    except Exception as e:
        logger.exception(f"Exiting: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    entrypoint()
