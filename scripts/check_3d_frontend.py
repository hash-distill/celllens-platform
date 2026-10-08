"""Compatibility entry point for the current data-driven functional network checks.

Organelle structure visualization was removed on 2026-10-08. This command now
requires --run-id and delegates to the response-workbench browser suite.
"""

from check_response_frontend import main

if __name__ == "__main__":
    main()
