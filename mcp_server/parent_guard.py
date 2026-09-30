"""Stop a CLI-owned MCP server when its supervising worker disappears."""
import os
import sys
import threading
import time


def start_parent_watchdog(parent_pid):
    def watch():
        while True:
            if os.getppid() != parent_pid:
                # No database writes occur in this pure calculation server.
                # os._exit also stops a synchronous calculation still in progress.
                os._exit(1)
            time.sleep(.1)
    thread = threading.Thread(target=watch, name='mcp-parent-watchdog', daemon=True)
    thread.start()


if __name__ == '__main__':
    start_parent_watchdog(int(sys.argv[1]))
    from mcp_server.server import server
    server.run('stdio')
