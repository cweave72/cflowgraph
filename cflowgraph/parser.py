from __future__ import annotations
import re

from typing import Optional, List, Any
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme
from rich.tree import Tree

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

    def __init__(self, raw_results: List[str]):
        self.nodes = []
        self.console = Console(theme=node_theme)

        for entry in raw_results:
            m = cflow_re.match(entry)
            if m:
                items = m.groups()
                node = Node(*items)
                self.nodes.append(node)

        # Build node tree object.
        self.build_node_tree()

    def build_node_tree(self):
        """Builds a recursive node list representing the call graph.
        """
        # Root node is always the first node in the list (level = 0).
        self.nodetree = NodeTree(root=self.nodes[0])
        root_branch = Branch()
        self.nodetree.add(root_branch)
        nodes = iter(self.nodes[1:])
        try:
            self.recurse_nodes(next(nodes), nodes, root_branch, 1)
        except StopIteration:
            pass
        #self.console.print(self.nodetree)

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

    def add_tree_branches(self, parent, items, show_signatures) -> None:
        """Recursively builds the tree.
        """
        for item in items:
            if isinstance(item, Node):
                child = parent.add(item.print(show_signatures, path_parts=5))
            elif isinstance(item, Branch):
                self.add_tree_branches(child, item.items, show_signatures)

    def rich_tree(self, show_signatures: bool = False) -> None:
        """Renders a tree view of the call graph using rich.tree.
        """
        # Parent node is always the first node in the list (level = 0).
        tree = Tree("Call Graph", hide_root=True)
        root = tree.add(Panel.fit(f"[root]{self.nodetree.root.name}[/root]"), guide_style='red')
        self.add_tree_branches(root, self.nodetree.branch.items, show_signatures)
        self.console.print(tree)
