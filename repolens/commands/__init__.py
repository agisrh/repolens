"""Every `repolens <command>` lives in its own module in this package.

A command module provides three things:
  NAME                        the word typed after `repolens`
  register(subparsers, common) defines the command's arguments; `common` holds --lang/--debug
  run(args) -> int            does the work and returns the exit code

To add a command, create a module with those three and add it to COMMANDS below. The
parser, --help, the interactive menu's "Same as:" line, and shell completion pick it up.
Shared argument helpers are in _common.py.
"""

from repolens.commands import auth, completion, diff, doctor, export, init, scan, update

# In the order `repolens --help` lists them.
COMMANDS = [scan, doctor, init, export, diff, auth, update, completion]
