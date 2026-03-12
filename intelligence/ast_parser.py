"""
intelligence/ast_parser.py

Static code parser using Tree-sitter for AST extraction.
Extracts classes, functions, methods, and imports from source files.
Falls back gracefully when tree-sitter is unavailable.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from utils.logger import logger

# Try to import tree-sitter; fall back to regex-based parsing if unavailable
_TREE_SITTER_AVAILABLE = False
try:
    from tree_sitter_languages import get_language, get_parser
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    logger.warning("ASTParser", "tree-sitter-languages not installed; using regex fallback")


# Tree-sitter language name mapping
_TS_LANG_MAP = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "go": "go",
    "java": "java",
}


@dataclass
class ParsedSymbol:
    """A symbol extracted from source code."""
    name: str
    kind: str        # "class", "function", "method"
    line: int        # 1-based line number
    end_line: int = 0
    parent: Optional[str] = None  # Enclosing class name for methods


@dataclass
class ParsedImport:
    """An import statement extracted from source code."""
    module: str          # The module or file being imported
    names: List[str] = field(default_factory=list)  # Specific names imported
    line: int = 0


@dataclass
class ParsedFile:
    """Full parse result for one file."""
    path: str
    language: str
    classes: List[ParsedSymbol] = field(default_factory=list)
    functions: List[ParsedSymbol] = field(default_factory=list)
    imports: List[ParsedImport] = field(default_factory=list)

    @property
    def all_symbols(self) -> List[ParsedSymbol]:
        return self.classes + self.functions


class ASTParser:
    """
    Parses source files to extract symbols and imports.
    
    Uses Tree-sitter when available, falls back to regex-based extraction.
    """

    def __init__(self):
        self._parsers: Dict[str, object] = {}

    @property
    def tree_sitter_available(self) -> bool:
        return _TREE_SITTER_AVAILABLE

    def parse_file(self, file_path: str, language: str, source: Optional[str] = None) -> ParsedFile:
        """
        Parse a source file and extract symbols.

        Args:
            file_path: Relative path of the file.
            language: Language identifier (python, javascript, etc.).
            source: Optional source code string. Will read from file if not provided.

        Returns:
            ParsedFile with extracted symbols and imports.
        """
        if source is None:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    source = f.read()
            except (OSError, IOError) as e:
                logger.warning("ASTParser", f"Cannot read {file_path}: {e}")
                return ParsedFile(path=file_path, language=language)

        if _TREE_SITTER_AVAILABLE and language in _TS_LANG_MAP:
            return self._parse_with_tree_sitter(file_path, language, source)
        else:
            return self._parse_with_regex(file_path, language, source)

    # ── Tree-sitter parsing ──────────────────────────────────────────────

    def _get_parser(self, language: str):
        """Get or create a tree-sitter parser for the given language."""
        if language not in self._parsers:
            ts_lang = _TS_LANG_MAP[language]
            parser = get_parser(ts_lang)
            self._parsers[language] = parser
        return self._parsers[language]

    def _parse_with_tree_sitter(self, file_path: str, language: str, source: str) -> ParsedFile:
        """Parse using tree-sitter AST."""
        result = ParsedFile(path=file_path, language=language)

        try:
            parser = self._get_parser(language)
            tree = parser.parse(source.encode("utf-8"))
            root = tree.root_node

            if language == "python":
                self._extract_python(root, result)
            elif language in ("javascript", "typescript"):
                self._extract_js_ts(root, result)
            elif language == "go":
                self._extract_go(root, result)
            elif language == "java":
                self._extract_java(root, result)

        except Exception as e:
            logger.warning("ASTParser", f"Tree-sitter parse failed for {file_path}: {e}, falling back to regex")
            return self._parse_with_regex(file_path, language, source)

        return result

    def _extract_python(self, root, result: ParsedFile):
        """Extract Python symbols from AST."""
        for node in self._walk(root):
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    cls_name = name_node.text.decode("utf-8")
                    result.classes.append(ParsedSymbol(
                        name=cls_name, kind="class",
                        line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                    ))
                    # Extract methods inside classes
                    for child in self._walk(node):
                        if child.type == "function_definition" and child.parent and child.parent.type in ("block",):
                            method_name = child.child_by_field_name("name")
                            if method_name:
                                result.functions.append(ParsedSymbol(
                                    name=method_name.text.decode("utf-8"),
                                    kind="method",
                                    line=child.start_point[0] + 1,
                                    end_line=child.end_point[0] + 1,
                                    parent=cls_name,
                                ))

            elif node.type == "function_definition":
                # Top-level functions only (not nested in class)
                if node.parent and node.parent.type == "module":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        result.functions.append(ParsedSymbol(
                            name=name_node.text.decode("utf-8"),
                            kind="function",
                            line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        ))

            elif node.type == "import_statement":
                text = node.text.decode("utf-8")
                match = re.match(r"import\s+([\w.]+)", text)
                if match:
                    result.imports.append(ParsedImport(
                        module=match.group(1),
                        line=node.start_point[0] + 1,
                    ))

            elif node.type == "import_from_statement":
                text = node.text.decode("utf-8")
                match = re.match(r"from\s+([\w.]+)\s+import\s+(.+)", text)
                if match:
                    module = match.group(1)
                    names = [n.strip() for n in match.group(2).split(",")]
                    result.imports.append(ParsedImport(
                        module=module,
                        names=names,
                        line=node.start_point[0] + 1,
                    ))

    def _extract_js_ts(self, root, result: ParsedFile):
        """Extract JavaScript/TypeScript symbols from AST."""
        for node in self._walk(root):
            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    cls_name = name_node.text.decode("utf-8")
                    result.classes.append(ParsedSymbol(
                        name=cls_name, kind="class",
                        line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                    ))
                    # Extract methods
                    body = node.child_by_field_name("body")
                    if body:
                        for child in self._walk(body):
                            if child.type == "method_definition":
                                mname = child.child_by_field_name("name")
                                if mname:
                                    result.functions.append(ParsedSymbol(
                                        name=mname.text.decode("utf-8"),
                                        kind="method",
                                        line=child.start_point[0] + 1,
                                        end_line=child.end_point[0] + 1,
                                        parent=cls_name,
                                    ))

            elif node.type in ("function_declaration", "function"):
                name_node = node.child_by_field_name("name")
                if name_node and node.parent and node.parent.type == "program":
                    result.functions.append(ParsedSymbol(
                        name=name_node.text.decode("utf-8"),
                        kind="function",
                        line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                    ))

            elif node.type in ("lexical_declaration", "variable_declaration"):
                # Arrow functions / const exports
                if node.parent and node.parent.type == "program":
                    text = node.text.decode("utf-8")
                    # Match const/let/var Name = ... => or function
                    match = re.match(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|=>)", text)
                    if match:
                        result.functions.append(ParsedSymbol(
                            name=match.group(1),
                            kind="function",
                            line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        ))

            elif node.type == "import_statement":
                text = node.text.decode("utf-8")
                # import X from 'module'
                match = re.search(r"""from\s+['"](.+?)['"]""", text)
                if match:
                    module = match.group(1)
                    names = []
                    name_match = re.search(r"import\s+\{([^}]+)\}", text)
                    if name_match:
                        names = [n.strip() for n in name_match.group(1).split(",")]
                    else:
                        default_match = re.match(r"import\s+(\w+)", text)
                        if default_match:
                            names = [default_match.group(1)]
                    result.imports.append(ParsedImport(
                        module=module, names=names,
                        line=node.start_point[0] + 1,
                    ))

    def _extract_go(self, root, result: ParsedFile):
        """Extract Go symbols from AST."""
        for node in self._walk(root):
            if node.type == "type_declaration":
                for child in node.children:
                    if child.type == "type_spec":
                        name_node = child.child_by_field_name("name")
                        type_node = child.child_by_field_name("type")
                        if name_node and type_node and type_node.type == "struct_type":
                            result.classes.append(ParsedSymbol(
                                name=name_node.text.decode("utf-8"),
                                kind="class",
                                line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                            ))

            elif node.type in ("function_declaration", "method_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    kind = "method" if node.type == "method_declaration" else "function"
                    parent = None
                    if node.type == "method_declaration":
                        params = node.child_by_field_name("parameters")
                        if params and params.named_child_count > 0:
                            recv = params.named_children[0]
                            type_node = recv.child_by_field_name("type")
                            if type_node:
                                parent = type_node.text.decode("utf-8").lstrip("*")

                    result.functions.append(ParsedSymbol(
                        name=name_node.text.decode("utf-8"),
                        kind=kind,
                        line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        parent=parent,
                    ))

            elif node.type == "import_declaration":
                for child in self._walk(node):
                    if child.type == "import_spec" or child.type == "interpreted_string_literal":
                        text = child.text.decode("utf-8").strip('"')
                        if "/" in text:
                            result.imports.append(ParsedImport(
                                module=text,
                                line=child.start_point[0] + 1,
                            ))

    def _extract_java(self, root, result: ParsedFile):
        """Extract Java symbols from AST."""
        for node in self._walk(root):
            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    cls_name = name_node.text.decode("utf-8")
                    result.classes.append(ParsedSymbol(
                        name=cls_name, kind="class",
                        line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                    ))
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            if child.type == "method_declaration":
                                mname = child.child_by_field_name("name")
                                if mname:
                                    result.functions.append(ParsedSymbol(
                                        name=mname.text.decode("utf-8"),
                                        kind="method",
                                        line=child.start_point[0] + 1,
                                        end_line=child.end_point[0] + 1,
                                        parent=cls_name,
                                    ))

            elif node.type == "import_declaration":
                text = node.text.decode("utf-8")
                match = re.match(r"import\s+([\w.]+);", text)
                if match:
                    result.imports.append(ParsedImport(
                        module=match.group(1),
                        line=node.start_point[0] + 1,
                    ))

    def _walk(self, node):
        """Depth-first walk of AST nodes."""
        cursor = node.walk()
        visited = False

        while True:
            if not visited:
                yield cursor.node
                if cursor.goto_first_child():
                    continue
            if cursor.goto_next_sibling():
                visited = False
                continue
            if not cursor.goto_parent():
                break
            visited = True

    # ── Regex fallback parsing ───────────────────────────────────────────

    def _parse_with_regex(self, file_path: str, language: str, source: str) -> ParsedFile:
        """Regex-based fallback when tree-sitter is unavailable."""
        result = ParsedFile(path=file_path, language=language)

        if language == "python":
            self._regex_python(source, result)
        elif language in ("javascript", "typescript"):
            self._regex_js_ts(source, result)
        elif language == "go":
            self._regex_go(source, result)
        elif language == "java":
            self._regex_java(source, result)

        return result

    def _regex_python(self, source: str, result: ParsedFile):
        lines = source.split("\n")
        current_class = None

        for i, line in enumerate(lines, 1):
            # Class definition
            match = re.match(r"^class\s+(\w+)", line)
            if match:
                current_class = match.group(1)
                result.classes.append(ParsedSymbol(name=current_class, kind="class", line=i))
                continue

            # Method (indented def inside class)
            match = re.match(r"^    def\s+(\w+)", line)
            if match and current_class:
                result.functions.append(ParsedSymbol(
                    name=match.group(1), kind="method", line=i, parent=current_class
                ))
                continue

            # Top-level function
            match = re.match(r"^def\s+(\w+)", line)
            if match:
                current_class = None
                result.functions.append(ParsedSymbol(name=match.group(1), kind="function", line=i))
                continue

            # Reset class context on non-indented non-empty line
            if line and not line.startswith(" ") and not line.startswith("#"):
                if not line.startswith("class ") and not line.startswith("def "):
                    current_class = None

            # Imports
            match = re.match(r"^from\s+([\w.]+)\s+import\s+(.+)", line)
            if match:
                names = [n.strip() for n in match.group(2).split(",")]
                result.imports.append(ParsedImport(module=match.group(1), names=names, line=i))
                continue

            match = re.match(r"^import\s+([\w.]+)", line)
            if match:
                result.imports.append(ParsedImport(module=match.group(1), line=i))

    def _regex_js_ts(self, source: str, result: ParsedFile):
        lines = source.split("\n")
        current_class = None

        for i, line in enumerate(lines, 1):
            match = re.match(r"(?:export\s+)?class\s+(\w+)", line.strip())
            if match:
                current_class = match.group(1)
                result.classes.append(ParsedSymbol(name=current_class, kind="class", line=i))
                continue

            match = re.match(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", line.strip())
            if match:
                result.functions.append(ParsedSymbol(name=match.group(1), kind="function", line=i))
                continue

            match = re.match(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|=>)", line.strip())
            if match:
                result.functions.append(ParsedSymbol(name=match.group(1), kind="function", line=i))
                continue

            match = re.search(r"""from\s+['"](.+?)['"]""", line)
            if match and ("import" in line):
                module = match.group(1)
                names = []
                name_match = re.search(r"import\s+\{([^}]+)\}", line)
                if name_match:
                    names = [n.strip() for n in name_match.group(1).split(",")]
                result.imports.append(ParsedImport(module=module, names=names, line=i))

    def _regex_go(self, source: str, result: ParsedFile):
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            match = re.match(r"type\s+(\w+)\s+struct\s*\{", line.strip())
            if match:
                result.classes.append(ParsedSymbol(name=match.group(1), kind="class", line=i))
                continue

            match = re.match(r"func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\(", line.strip())
            if match:
                receiver_type = match.group(2)
                func_name = match.group(3)
                if receiver_type:
                    result.functions.append(ParsedSymbol(
                        name=func_name, kind="method", line=i, parent=receiver_type
                    ))
                else:
                    result.functions.append(ParsedSymbol(name=func_name, kind="function", line=i))

    def _regex_java(self, source: str, result: ParsedFile):
        lines = source.split("\n")
        current_class = None
        for i, line in enumerate(lines, 1):
            match = re.match(r".*\bclass\s+(\w+)", line.strip())
            if match:
                current_class = match.group(1)
                result.classes.append(ParsedSymbol(name=current_class, kind="class", line=i))
                continue

            match = re.match(
                r"\s*(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(",
                line
            )
            if match and current_class:
                name = match.group(1)
                if name != current_class:  # Skip constructors
                    result.functions.append(ParsedSymbol(
                        name=name, kind="method", line=i, parent=current_class
                    ))

            match = re.match(r"import\s+([\w.]+);", line.strip())
            if match:
                result.imports.append(ParsedImport(module=match.group(1), line=i))
