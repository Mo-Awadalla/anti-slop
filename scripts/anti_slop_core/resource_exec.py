"""Linux-only exec boundary, invoked inside Bubblewrap before project code.

This is a stand-alone stdlib script to avoid preexec_fn in a threaded parent.
RLIMIT_NPROC is per real UID, not a container-wide guarantee; the external
Docker launcher supplies hard aggregate cgroup memory and process bounds.
"""

import os
import resource
import sys


def main():
    if sys.platform != "linux":
        raise SystemExit("resource launch requires Linux")
    address_space, file_size, processes, open_files, cpu_seconds = map(int, sys.argv[1:6])
    for kind, value in ((resource.RLIMIT_AS, address_space),
                        (resource.RLIMIT_FSIZE, file_size),
                        (resource.RLIMIT_NPROC, processes),
                        (resource.RLIMIT_NOFILE, open_files),
                        (resource.RLIMIT_CPU, cpu_seconds),
                        (resource.RLIMIT_CORE, 0)):
        _, hard = resource.getrlimit(kind)
        maximum = value if hard == resource.RLIM_INFINITY else min(value, hard)
        resource.setrlimit(kind, (maximum, maximum))
    command = sys.argv[6:]
    if not command:
        raise SystemExit("resource launch needs a command")
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
