from __future__ import annotations
import sys
import re

from typing import Optional, List, Any
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme
from rich.tree import Tree

from graphviz import Digraph

from . import pf

import logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Regex for parsing line output from cflow.
cflow_re = re.compile(r"""
    {\s+(\d+)}                      # group 1 -> depth level
    \s+(\w+?\(\))                   # group 2 -> function name
    (?:
    \s<(.*\))\sat\s (.*):(\d+)>:    # (opt) group 3,4,5 signature, path, line no
    )?
    """, flags=re.DOTALL | re.VERBOSE)

# Rich theme for showing results as a tree graph.
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

    def iterate(self, parent : Branch = None):
        """Recursive generator for iterating through branch items.
        """
        prev_item = parent
        for item in self.items:
            if isinstance(item, Node):
                yield parent, item
            elif isinstance(item, Branch):
                yield from item.iterate(prev_item)

            prev_item = item


@dataclass
class NodeTree:
    root: str
    branch: Optional[Branch] = None
    static: Optional[bool] = False

    def add(self, branch: Branch) -> None:
        self.branch = branch

    def iterate(self):
        """Generator for looping through the entire node tree.
        """
        yield from self.branch.iterate()


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

    def __init__(self,
                 raw_results: List[str],
                 main: str = None,
                 verbose : bool = False) -> None:
        self.nodes = []
        self.verbose = verbose
        self.console = Console(theme=node_theme)
        self.nodetree = None

        if len(raw_results) == 0:
            logger.info("No results to process.")
            return

        # Parse results from cflow into a list of Nodes.
        for entry in raw_results:
            m = cflow_re.match(entry)
            if m:
                items = m.groups()
                node = Node(*items)
                self.nodes.append(node)

        # Build node tree object.
        # Sometimes a function will not be in the cflow output at level 0 (not
        # sure why this occurs). To still attempt to provide a result, we
        # search the tree at increasing levels until the desired function is
        # found at that level - or - it is not found at all.
        for level in range(0, 9):
            logger.debug(f"Searching cflow output for main={main} at level {level}")
            level_found = self.build_node_tree(main, target_level=level)
            if level_found is None:
                logger.error(f"Did not find function {main} in cflow output.")
                sys.exit(1)
            elif level_found < 0:
                sys.exit(1)
            elif level_found == level:
                logger.debug("Successfully created node tree.")
                if self.verbose:
                    logger.debug(f"nodetree = {pf(self.nodetree)}")
                break

    def build_node_tree(self, main : str = None, target_level : int = 0) -> None:
        """Builds a recursive node list representing the call graph.
        """
        index = 0
        stop_index = len(self.nodes)
        lowest_level_found = None

        if main:
            # Ideally, cflow will have found the function specified as the
            # 'main' function and this will be the first entry in the
            # self.nodes list (and will have a level of 0). However, if the
            # desired 'main' function is declared as 'static' in the C codebase
            # being searched, cflow will not isolate this in its output but
            # instead will generate a call graph for every function it finds
            # (i.e. as if every function was the 'main' function). The desired
            # 'main' function will still be in the list, but it will not be the
            # first entry - and it may not be marked as level 0. The following
            # code searches through the self.nodes list to find the 'main'
            # function at the target_level specified. Once found, it will then
            # try to mark the end of the call graph list so that it can be
            # extraced and displayed.
            for index, node in enumerate(self.nodes):
                if self.verbose:
                    logger.debug(f"(searching for main) index={index} "
                                 f"level={node.level} node={node.name}")

                if node.name == main:
                    if lowest_level_found:
                        lowest_level_found = min(lowest_level_found, node.level)
                    else:
                        lowest_level_found = node.level

                    if node.level == target_level:
                        logger.debug(f"Found main={main} at index={index} "
                                     f"(level={node.level})")
                        break
            else:
                logger.debug(f"Function {main} not found at level "
                             f"{target_level}.")
                return lowest_level_found

            # If the main function wasn't found at the head of the list, it was
            # likely a static function and we must find where the graph ends.
            # The following code attempts to find the end of the call graph by
            # finding the next function with level 0.
            if index > 0:
                # Extract call graph from this point. All nodes after that
                # have level > 0 if part of the 'main' functions call graph.
                # We know we've found the end when the current node in the
                # iteration has a level of 0.
                m = index+1
                while m < len(self.nodes):
                    if self.verbose:
                        logger.debug(f"(searching for end) index={m} "
                                     f"(level={self.nodes[m].level}) "
                                     f"node={self.nodes[m].name}")

                    if self.nodes[m].level > target_level:
                        m += 1
                    else:
                        logger.debug(f"Found end of graph at index {m-1}")
                        stop_index = m
                        break
                else:
                    logger.error(f"Could not find end of graph for function {main}")
                    return -1

        nodes = self.nodes[index:stop_index]

        # If the starting index in the node list is not 0, then the function
        # was declared as static (see explaination above).
        if index == 0:
            funcion_is_static = False
        else:
            funcion_is_static = True

        self.nodetree = NodeTree(root=main, static=funcion_is_static)
        root_branch = Branch()
        self.nodetree.add(root_branch)
        iternodes = iter(nodes)
        try:
            self.recurse_nodes(next(iternodes),
                               iternodes,
                               root_branch,
                               target_level)
        except StopIteration:
            # Return the passed target level to indicate success at that level.
            return target_level

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
        static_txt = "(static)" if self.nodetree.static else ""
        root_panel = Panel.fit(f"{static_txt} [root]{self.nodetree.root}[/root]")
        root = tree.add(root_panel, guide_style='red')
        self.add_tree_branches(parent=root,
                               items=self.nodetree.branch.items,
                               show_signatures=show_signatures)
        if pager:
            with self.console.pager(styles=True):
                self.console.print(tree)
        else:
            self.console.print(tree)

    def add_tree_branches(self, parent, items, show_signatures) -> None:
        """Recursively creates branches of a rich tree.
        """
        child = None
        for item in items:
            if isinstance(item, Node):
                child = parent.add(item.print(show_signatures, path_parts=5))
            elif isinstance(item, Branch):
                if child is None:
                    child = parent
                self.add_tree_branches(parent=child,
                                       items=item.items,
                                       show_signatures=show_signatures)

    def dot_graph(self, **opts):
        opts.setdefault('name', 'call_graph')
        opts.setdefault('comment', f'call graph for {self.nodetree.root}')
        opts.setdefault('filename', 'cflowgraph')
        opts.setdefault('engine', 'dot')
        opts.setdefault('format', 'svg')
        opts.setdefault('directory', '.')
        opts.setdefault('graph_attr', {'rankdir': 'LR'})
        opts.setdefault('node_attr', {'shape': 'rect',
                                      'margin': '0.05',
                                      'height': '.3',
                                      'style': 'filled',
                                      'fontname': 'Courier New',
                                      'fontsize': '8',
                                      'fillcolor': '#ccccff',
                                      })
        opts.setdefault('edge_attr', {'arrowsize': '0.5'})

        graph = Digraph(**opts)
        graph.attr(rankdir='LR')
        edges = []
        for parent, node in self.nodetree.iterate():
            if parent is None:
                graph.node(node.name)
            else:
                logger.debug(f"Adding edge: {parent.name} -> {node.name}")
                edges.append((f"{parent.name}", f"{node.name}"))

        unique_edges = set(edges)
        dups = len(edges) - len(unique_edges)
        logger.debug(f"Filtered {dups} duplicate edges.")

        for parent, node in unique_edges:
            graph.edge(parent, node)

        graph.view()
