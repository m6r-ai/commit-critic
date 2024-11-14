#!/usr/bin/env python3

# Copyright 2024 M6R Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
commit-critic - A command line tool for AI-assisted code reviews.

This module provides the main entry point for the commit-critic application,
which processes source files for AI-based code review using the Metaphor
language format.

The tool accepts input files and generates a properly formatted prompt
that can be used with AI systems to perform code reviews. It supports
various command line arguments for configuration and uses the Metaphor
language format for structuring the review request.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


from m6rclib import (
    MetaphorASTNode,
    MetaphorParser,
    MetaphorParserError,
    format_ast,
    format_errors,
)


@dataclass
class ReviewConfiguration:
    """Configuration settings for the review generator.

    Attributes:
        output_file: Optional file path for output
        guideline_paths: List of paths to search for guidelines
        input_files: List of input files to review
        version: Version string of the application
    """
    output_file: Optional[str]
    guideline_paths: List[str]
    input_files: List[str]
    version: str = "v0.1"


class MetaphorReviewGenerator:
    """Handles the generation of code reviews using Metaphor templates."""

    def __init__(self, config: ReviewConfiguration):
        """Initialize the review generator.

        Args:
            config: Configuration settings for the review
        """
        self.config = config
        self.guidelines: List[str] = []
        self.parser = MetaphorParser()

    def _get_env_guideline_paths(self) -> List[str]:
        """Get guideline paths from environment variable.

        Returns:
            List of paths from COMMIT_CRITIC_GUIDELINE_DIR environment variable
        """
        env_paths = os.getenv("COMMIT_CRITIC_GUIDELINE_DIR", "")
        if not env_paths:
            return []

        return [p.strip() for p in env_paths.split(os.pathsep) if p.strip()]

    def find_guideline_files(self, paths: Optional[List[str]]) -> List[str]:
        """Find all .m6r files in the specified paths.

        Args:
            paths: List of paths to search, or None to use current directory

        Returns:
            List of discovered .m6r files

        Raises:
            SystemExit: If no guideline files are found or on permission errors
        """
        search_paths = []

        # Add environment variable paths
        env_paths = self._get_env_guideline_paths()
        if env_paths:
            search_paths.extend(env_paths)

        # Add command line paths if specified
        if paths:
            search_paths.extend(paths)

        # Use current directory if no paths specified
        if not search_paths:
            search_paths = ['.']

        guidelines = []
        for path in search_paths:
            try:
                path_obj = Path(path)
                if not path_obj.exists():
                    sys.stderr.write(f"Warning: Path does not exist: {path}\n")
                    continue

                if not path_obj.is_dir():
                    sys.stderr.write(f"Warning: Path is not a directory: {path}\n")
                    continue

                guidelines.extend(path_obj.glob('*.m6r'))

            except PermissionError as e:
                sys.stderr.write(f"Error: Permission denied accessing path {path}: {e}\n")
                sys.exit(2)

        if not guidelines:
            sys.stderr.write(
                f"Error: No .m6r files found in search paths: {', '.join(search_paths)}\n"
            )
            sys.exit(2)

        return [str(p) for p in guidelines]

    def validate_files(self, files: List[str]) -> None:
        """Validate that all input files exist and are readable.

        Args:
            files: List of files to validate

        Raises:
            SystemExit: If any file cannot be accessed
        """
        for file in files:
            path = Path(file)
            if not path.is_file():
                sys.stderr.write(f"Error: Cannot open input file: {file}\n")
                sys.exit(3)

            if not os.access(path, os.R_OK):
                sys.stderr.write(f"Error: No read permission for file: {file}\n")
                sys.exit(3)

    def create_metaphor_content(self, guidelines: List[str], files: List[str]) -> str:
        """Create the Metaphor content string.

        Args:
            guidelines: List of guideline files to include
            files: List of files to review

        Returns:
            String containing the complete Metaphor content
        """
        include_lines = '\n'.join(f'    Include: {g}' for g in guidelines)
        embed_lines = '\n'.join(f'    Embed: {f}' for f in files)

        return f"""Role:
    You are an expert software reviewer, highly skilled in reviewing code written by other engineers.  You are
    able to provide insightful and useful feedback on how their software might be improved.
Context: Review guidelines
{include_lines}
Action: Review code
    Please review the software described in the files provided here:
{embed_lines}
    I would like you to summarise how the software works.
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

    def write_output(self, content: str, output_file: Optional[str]) -> None:
        """Write content to the specified output file or stdout.

        Args:
            content: Content to write
            output_file: Optional output file path

        Raises:
            SystemExit: If output file cannot be written
        """
        if output_file:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
            except OSError as e:
                sys.stderr.write(f"Error: Cannot create output file {output_file}: {e}\n")
                sys.exit(4)
            return

        sys.stdout.write(content)

    def validate_and_prepare(self) -> None:
        """Validate input files and prepare guidelines.

        Raises:
            SystemExit: If validation fails
        """
        if not self.config.input_files:
            sys.stderr.write("Error: No input files specified\n")
            sys.exit(1)

        self.validate_files(self.config.input_files)
        self.guidelines = self.find_guideline_files(self.config.guideline_paths)

    def generate_review(self) -> None:
        """Generate the code review.

        Raises:
            SystemExit: If review generation fails
        """
        content = self.create_metaphor_content(self.guidelines, self.config.input_files)
        try:
            ast: MetaphorASTNode = self.parser.parse(
                content,
                "<generated>",
                self.config.guideline_paths or ["."]
            )
            self.write_output(format_ast(ast), self.config.output_file)
        except MetaphorParserError as e:
            sys.stderr.write(format_errors(e.errors))
            sys.exit(2)


def parse_arguments() -> ReviewConfiguration:
    """Parse and validate command line arguments.

    Returns:
        ReviewConfiguration containing the parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Generate AI-assisted code reviews using Metaphor templates'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output file for the generated prompt',
        type=str
    )
    parser.add_argument(
        '-g', '--guideline-dir',
        help='Path to search for Metaphor guideline files',
        action='append',
        type=str,
        dest='guideline_paths'
    )
    parser.add_argument(
        '-v', '--version',
        help='Display version information',
        action='version',
        version='v0.1'
    )
    parser.add_argument(
        'files',
        help='Files to review',
        nargs='*'
    )

    args = parser.parse_args()
    return ReviewConfiguration(
        output_file=args.output,
        guideline_paths=args.guideline_paths,
        input_files=args.files
    )


def main() -> None:
    """Main entry point for the application."""
    config = parse_arguments()
    generator = MetaphorReviewGenerator(config)
    generator.validate_and_prepare()
    generator.generate_review()


if __name__ == '__main__':
    main()
