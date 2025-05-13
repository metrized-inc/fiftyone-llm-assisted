import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from re import MULTILINE
from re import compile as re_compile
from subprocess import run as run_cmd
from textwrap import dedent


def today():
    return f"{datetime.today():%Y-%m-%d}"


def bold(text):
    return f"\033[1m{text}\033[0m"


def hyperlink(text, link: str):
    return f"\033]8;;{link}\033\\{text}\033]8;;\033\\"


class Bump(Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"

    def __str__(self):
        return self.name


def parse_args():
    parser = ArgumentParser(description="Update the version of the code.")
    parser.add_argument(
        "type",
        type=lambda x: Bump(x.lower()),
        choices=[*Bump],
        help="type of version bump",
    )

    return parser.parse_args()


class GitCommands:
    @staticmethod
    def current_branch():
        response = run_cmd("git branch --show-current".split(), capture_output=True)
        if response.returncode != 0:
            raise RuntimeError("Git command failed")
        return response.stdout.decode("utf-8").strip()

    @staticmethod
    def changes():
        response = run_cmd("git status --porcelain".split(), capture_output=True)
        if response.returncode != 0:
            raise RuntimeError("Git command failed")
        lines = response.stdout.decode("utf-8").strip().splitlines()
        changes = [l for l in lines if not l.startswith("??")]  # noqa: E741
        return changes

    @staticmethod
    def check_assumptions():
        if len(GitCommands.changes()) > 0:
            raise RuntimeError("Must stash or commit the changed files")
        if GitCommands.current_branch() == "main":
            msg = "This changes should be made off the main branch and merged"
            raise RuntimeError(msg)


git = GitCommands()


class AssumedFolderStructure:
    def __init__(self):
        self.root = Path.cwd().relative_to(Path.cwd())
        self.validate()

    def validate(self):
        try:
            self.init_file
            self.git
            self.changelog
        except FileNotFoundError:
            raise

    @property
    def init_file(self):
        src = self.root / "src"
        filename = "__init__.py"
        try:
            return next(src.glob(f"*/{filename}"))
        except StopIteration:
            raise FileNotFoundError(f"Could not find {filename}")

    @property
    def changelog(self):
        filepath = self.root / "CHANGELOG.md"
        if not filepath.exists():
            raise FileNotFoundError(f"Could not find {filepath}")
        return filepath

    @property
    def git(self):
        filepath = self.root / ".git"
        if not filepath.exists() or not filepath.is_dir():
            raise FileNotFoundError(f"Missing {filepath.name} directory")
        return filepath


@dataclass(frozen=True)
class Version:
    PATTERN = r"(\d+)\.(\d+)\.(\d+)"
    major: int
    minor: int
    patch: int

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}"

    def bump(self, type_: Bump):
        if type_ is Bump.MAJOR:
            return Version(self.major + 1, 0, 0)
        elif type_ is Bump.MINOR:
            return Version(self.major, self.minor + 1, 0)
        else:  # is Bump.PATCH
            return Version(self.major, self.minor, self.patch + 1)

    @classmethod
    def from_text(cls, text: str):
        regex = re_compile(cls.PATTERN)
        if (match := regex.match(text)) is None:
            raise ValueError("Could not parse")
        return cls(*(int(d) for d in match.groups()))


def prompt_user(msg):
    while (answer := input(msg).lower()) not in [*"yn"]:
        print("Input must be a 'Y' or 'n'")

    print("\n", end="")
    return answer == "y"


def main():
    """Runs the release workflow."""

    # Get input on whether a major, minor or patch release
    args = parse_args()

    # Check for files
    try:
        repo = AssumedFolderStructure()
    except FileNotFoundError as e:
        print(f"FileError: {e}")
        sys.exit(1)

    # Check Git is in order
    try:
        git.check_assumptions()
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Grep current version
    with open(repo.init_file) as f:
        regex = re_compile(r"^__version__ += +\"(.+)\"$")
        for line in f:
            if (match := regex.match(line)) is not None:
                break

    if match is None:
        print(f"Cannot parse version from {repo.init_file}")
        sys.exit(1)

    old_version = Version.from_text(match.group(1))
    new_version = old_version.bump(args.type)

    # Grab hyper link
    with open(repo.changelog) as f:
        regex = re_compile(
            r"^\[Unreleased\]: (https://github.com/metrized-inc/[a-zA-Z\-]+/compare/v[\d\.]+?\.{3})HEAD$",
            flags=MULTILINE,
        )
        text = f.read()
        if (match := regex.search(text)) is None:
            print("Error: Couldn't find markdown hyperlink.")
            sys.exit(1)
        link = f"{match.group(1)}{git.current_branch()}"

    # Show user the diff
    show_diff = hyperlink(f"{bold(old_version)} -> {bold(new_version)}", link)
    print(f"Will move from {show_diff}")
    proceed = prompt_user("Do you wish to continue? [Y/n]: ")
    if not proceed:
        sys.exit(0)

    # Update init file
    text = repo.init_file.read_text()
    regex = re_compile(r"^__version__ += +\"(.+)\"$", MULTILINE)
    if regex.search(text) is None:
        print("Error: Could not find __version__")
        sys.exit(1)
    text = regex.sub(rf'__version__ = "{new_version}"', text)

    with open(repo.init_file, "w") as f:
        f.write(text)

    # Update Changelog
    text = repo.changelog.read_text()
    regex = re_compile(r"^#{2}\s+\[Unreleased\]$", MULTILINE)

    if (match := regex.search(text)) is None:
        print("Error: Couldn't find Unreleased header in markdown")
        sys.exit(1)

    delim = match.end()
    release_text = f"\n\n## [{new_version}] - {today()}"
    text = "".join([text[:delim], release_text, text[delim:]])
    regex = re_compile(
        r"(\[Unreleased\]): ((https://github.com/metrized-inc/[a-zA-Z\-]+/compare)/v([\d\.]+?)\.\.\.HEAD)"
    )

    if regex.search(text) is None:
        print("Error: Couldn't find markdown hyperlink.")
        sys.exit(1)

    text = regex.sub(
        rf"\1: \3/v{new_version}...HEAD\n[{new_version}]: \3/v\4...v{new_version}", text
    )

    with open(repo.changelog, "w") as f:
        f.write(text)

    # Print instructions
    print(
        dedent(
            f"""\
            Modified: {repo.changelog} {repo.init_file}

            Run the following commands:
            git add {repo.changelog} {repo.init_file};
            git commit -m "Making v{new_version} release";
            git switch main; git merge {git.current_branch()};
            git tag v{new_version};
            git push origin main; git push origin v{new_version}

            (Note: to revert, run the command -> git restore .)
            Then through steps to create a release on github.
            """
        ).strip()
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
