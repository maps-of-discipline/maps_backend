from .db_seed import seed_command
from .db_unseed import unseed_command
from .import_aup import import_aup_command
from .fgos_import import import_fgos_command
from .parse_profstandard import parse_ps_command

def register_cli_commands(app):
    """Registers all custom CLI commands with the Flask application."""
    app.cli.add_command(seed_command)
    app.cli.add_command(unseed_command)
    app.cli.add_command(import_aup_command)
    app.cli.add_command(import_fgos_command)
    app.cli.add_command(parse_ps_command)