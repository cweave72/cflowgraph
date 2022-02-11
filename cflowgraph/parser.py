from __future__ import annotations
import re

from typing import Optional, List, Any
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme
from rich.tree import Tree

from . import pf

import logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

cflow_re = re.compile(r"""
    {\s+(\d+)}                      # group 1 -> depth level
    \s+(\w+?\(\))                   # group 2 -> function name
    (?:
    \s<(.*\))\sat\s (.*):(\d+)>:    # (opt) group 3,4,5 signature, path, line no
    )?
    """, flags=re.DOTALL | re.VERBOSE)

node_theme = Theme({
    "root": "yellow",
    "level": "cyan",
    "name": "sky_blue1",
    "path": "magenta",
    "line": "sea_green1",
    "signature": "dark_khaki",
})


@dataclass
class Branch:
    items: Optional[List[Any]] = field(default_factory=lambda: [])

    def add(self, item: Any) -> None:
        self.items.append(item)


@dataclass
class NodeTree:
    root: Node
    branch: Optional[Branch] = None

    def add(self, branch: Branch) -> None:
        self.branch = branch


@dataclass
class Node:
    level: int
    name: str
    signature: Optional[str] = None
    path: Optional[Path] = None
    line: Optional[int] = None

    def __post_init__(self):
        if self.level:
            self.level = int(self.level)
        if self.line:
            self.line = int(self.line)
        if self.path:
            self.path = Path(self.path)

    def get_level(self) -> str:
        return f"[level]{self.level}[/level]"

    def get_name(self) -> str:
        return f"[name]{self.name}[/name]"

    def get_path(self, parts=None) -> str:
        if self.path is None:
            return ""
        if parts:
            parts = -parts
            return f"[path].../{'/'.join(self.path.parts[parts:])}[/path]"
        else:
            return f"[path]{self.path}[/path]"

    def get_signature(self) -> str:
        if self.signature:
            return f"[signature]{self.signature}[/signature]"
        else:
            return ""

    def get_line(self) -> str:
        if self.line is None:
            return ""
        return f"([line]{self.line}[/line])"

    def print(self, show_signature: bool = False, path_parts: int = 4) -> str:
        if show_signature:
            return (f"[{self.get_level()}]: "
                    f"{self.get_name()}  "
                    f"{self.get_signature()} "
                    f"{self.get_path(parts=path_parts)} "
                    f"{self.get_line()}")
        else:
            return (f"[{self.get_level()}]: "
                    f"{self.get_name()}  "
                    f"{self.get_path(parts=path_parts)} "
                    f"{self.get_line()}")


class CflowParser:
    """Object for handling cflow output and visualizing results.
    """

    def __init__(self, raw_results: List[str], main: str = None) -> None:
        self.nodes = []
        self.console = Console(theme=node_theme)
        self.nodetree = None

        if len(raw_results) == 0:
            logger.info("No results to process.")
            return

        for entry in raw_results:
            m = cflow_re.match(entry)
            if m:
                items = m.groups()
                node = Node(*items)
                self.nodes.append(node)

        # Build node tree object.
        self.build_node_tree(main)

    def build_node_tree(self, main : str = None) -> None:
        """Builds a recursive node list representing the call graph.
        """
        # The following is a work-around for a short-coming with cflow. It
        # doesn't seem to detect functions as the 'main' function if the
        # function is declared as static. It will default by dumping call
        # graphs for every function (there will be multiple entries with
        # level=0). The desired 'main' function will still be in the list, but
        # it will not be the first entry, so we need to find it. This will tell
        # us where to start in the list to build the node tree.
        if main:
            for k, node in enumerate(self.nodes):
                if node.name == main and node.level == 0:
                    logger.debug(f"Found main={main} at index={k}")
                    break
            else:
                logger.error(f"Could not find main function {main}")
                return

            # Extract call graph from this point (all nodes after that
            # have level > 0)
            m = k+1
            while True:
                if self.nodes[m].level > 0:
                    m += 1
                else:
                    logger.debug(f"Found end of graph at {m}: {self.nodes[m]}")
                    stop = m
                    break
        else:
            k = 0
            stop = len(self.nodes)

        nodes = self.nodes[k:stop]
        #logger.debug(f"nodes={pf(nodes)}")

        # Root node is always the first node in the list (level = 0).
        self.nodetree = NodeTree(root=nodes[0])
        root_branch = Branch()
        self.nodetree.add(root_branch)
        iternodes = iter(nodes)
        try:
            self.recurse_nodes(next(iternodes), iternodes, root_branch, 0)
        except StopIteration:
            pass

    def recurse_nodes(self, node, nodes, parent_branch, parent_level):
        while True:
            if node.level == parent_level:
                parent_branch.add(node)
            elif node.level > parent_level:
                # Recursive call for next level of tree.
                child = Branch()
                parent_branch.add(child)
                node = self.recurse_nodes(node, nodes, child, node.level)
                # Returning from recursive call, do not advance iterator.
                continue
            else:
                # Pop recursive call.
                return node

            node = next(nodes)

    def rich_tree(self,
                  show_signatures: bool = False,
                  pager: bool = False) -> None:
        """Renders a tree view of the call graph using rich.tree.
        """
        if self.nodetree is None:
            logger.error("No data to process.")
            return

        # Parent node is always the first node in the list (level = 0).
        tree = Tree("Call Graph", hide_root=True)
        root = tree.add(Panel.fit(f"[root]{self.nodetree.root.name}[/root]"), guide_style='red')
        self.add_tree_branches(root, self.nodetree.branch.items, show_signatures)
        if pager:
            with self.console.pager(styles=True):
                self.console.print(tree)
        else:
            self.console.print(tree)

    def add_tree_branches(self, parent, items, show_signatures) -> None:
        """Recursively builds the tree.
        """
        for item in items:
            if isinstance(item, Node):
                child = parent.add(item.print(show_signatures, path_parts=5))
            elif isinstance(item, Branch):
                self.add_tree_branches(child, item.items, show_signatures)
