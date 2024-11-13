#!/usr/bin/env python3

"""
code-review2 - A command line tool for AI-assisted code reviews.

This module provides the main entry point for the code-review2 application,
which processes source files for AI-based code review using the Metaphor
language format.

The tool accepts input files and generates a properly formatted prompt
that can be used with AI systems to perform code reviews. It supports
various command line arguments for configuration and uses the Metaphor
language format for structuring the review request.
"""

import argparse
import glob
import os
import sys
from pathlib import Path
from typing import List, TextIO, Optional, Set

from m6rclib import (
    MetaphorParser,
    MetaphorParserError,
    MetaphorASTNode,
    MetaphorASTNodeType
)


def recurse_ast(node: MetaphorASTNode, depth: int, out: TextIO) -> None:
    """
    Recursively traverse the MetaphorAST and output formatted sections.

    Args:
        node (MetaphorASTNode): The current MetaphorAST node being processed
        depth (int): The current tree depth
        out (TextIO): The output stream to write to
    """
    if node.node_type != MetaphorASTNodeType.ROOT:
        indent = " " * ((depth - 1) * 4)
        if node.node_type == MetaphorASTNodeType.TEXT:
            out.write(f"{indent}{node.value}\n")
            return

        # Map node types to keywords
        node_type_map = {
            MetaphorASTNodeType.ACTION: "Action:",
            MetaphorASTNodeType.CONTEXT: "Context:",
            MetaphorASTNodeType.ROLE: "Role:"
        }
        keyword = node_type_map.get(node.node_type, "")

        if keyword:
            out.write(f"{indent}{keyword}")
            if node.value:
                out.write(f" {node.value}")
            out.write("\n")

    for child in node.children:
        recurse_ast(child, depth + 1, out)


def find_guideline_files(paths: List[str]) -> Set[str]:
    """
    Find all .m6r files in the given paths.

    Args:
        paths (List[str]): List of paths to search

    Returns:
        Set[str]: Set of found .m6r files
    """
    guideline_files = set()

    for path in paths:
        if not os.path.exists(path):
            continue

        # Search for .m6r files in the directory
        pattern = os.path.join(path, "*.m6r")
        guideline_files.update(glob.glob(pattern))

    return guideline_files


def create_prompt(files: List[str], search_paths: List[str], output_stream: TextIO) -> int:
    """
    Create the Metaphor prompt structure that will be sent to the AI for review.

    Args:
        files (List[str]): List of files to be reviewed
        search_paths (List[str]): List of paths to search for included files
        output_stream (TextIO): Where to write the output

    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    # First check if we can find any guideline files
    search_paths = search_paths if search_paths else [os.getcwd()]
    guideline_files = find_guideline_files(search_paths)

    if not guideline_files:
        print("Error: No .m6r guideline files found in the search path", file=sys.stderr)
        return 2

    # Create the root metaphor structure
    metaphor_root = """Role:
    You are an expert software reviewer, highly skilled in reviewing code written by other engineers.  You are
    able to provide insightful and useful feedback on how their software might be improved.
Context: Review guidelines"""

    # Add the Include directives for each guideline file found
    for guideline in guideline_files:
        metaphor_root += f"\n    Include: {guideline}"

    metaphor_root += """\nAction: Review code
    Please review the software described in the files provided here:
"""

    # Add the embedded files with correct indentation
    for file in files:
        metaphor_root += f"    Embed: {file}\n"

    metaphor_root += """    I would like you to summarise how the software works.
    I would also like you to review each file individually and comment on how it might be improved, based on the
    guidelines I have provided.  When you do this, you should tell me the name of the file you believe may want to
    be modified, the modification you believe should happen, and which of the guidelines the change would align with.
    If any change you envisage might conflict with a guideline then please highlight this and the guideline that might
    be impacted.
    The review guidelines include generic guidance that should be applied to all file types, and guidance that should
    only be applied to a specific language type.  In some cases the specific guidance may not be relevant to the files
    you are asked to review, and if that's the case you need not mention it.  If, however, there is no specific
    guideline file for the language in which a file is written then please note that the file has not been reviewed
    against a detailed guideline.
    Where useful, I would like you to write new software to show me how any modifications should look."""

    # Parse the metaphor content
    try:
        metaphor_parser = MetaphorParser()
        syntax_tree = metaphor_parser.parse(metaphor_root, "<root>", search_paths)
    except MetaphorParserError as e:
        for error in e.errors:
            caret = " " * (error.column - 1)
            error_message = (
                f"{error.message}: line {error.line}, column {error.column}, "
                f"file {error.filename}\n{caret}|\n{caret}v\n{error.input_text}"
            )
            print(f"----------------\n{error_message}", file=sys.stderr)
        print("----------------\n", file=sys.stderr)
        return 2

    recurse_ast(syntax_tree, 0, output_stream)
    return 0


def process_files(args: argparse.Namespace) -> int:
    """
    Process input files and generate the review prompt.

    Args:
        args (argparse.Namespace): Parsed command line arguments

    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    # Verify all input files exist
    for file in args.files:
        if not Path(file).is_file():
            print(f"Error: Input file '{file}' does not exist", file=sys.stderr)
            return 3

    # Handle output file
    output_stream: Optional[TextIO] = None
    try:
        output_stream = (
            open(args.output, 'w', encoding='utf-8')
            if args.output
            else sys.stdout
        )
        result = create_prompt(args.files, args.guideline_path, output_stream)

        # Only close if we opened a file
        if args.output:
            output_stream.close()

        return result

    except OSError as e:
        print(f"Error: Could not open output file {args.output}: {e}", file=sys.stderr)
        return 4


def main() -> int:
    """
    Main entry point for the code-review2 application.

    Parses command line arguments and orchestrates the review prompt generation process.

    Returns:
        int: Exit code (0 for success, non-zero for error)
        - 0: Success
        - 1: Command line usage error
        - 2: Data format error (e.g. invalid Metaphor syntax)
        - 3: Cannot open input file
        - 4: Cannot create output file
    """
    parser = argparse.ArgumentParser(
        description='Generate an AI prompt for code review from input files'
    )
    parser.add_argument(
        '-v', '--version',
        action='version',
        version='%(prog)s v0.1'
    )
    parser.add_argument(
        '-o', '--output',
        help='output file (defaults to stdout)',
        type=str
    )
    parser.add_argument(
        '-g', '--guideline-path',
        action='append',
        help='add a directory to search for .m6r files (defaults to current directory)',
        type=str
    )
    parser.add_argument(
        'files',
        nargs='+',
        help='input files to process'
    )

    try:
        args = parser.parse_args()
        return process_files(args)
    except argparse.ArgumentError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
