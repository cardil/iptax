# Dockerfile for testing fresh install of iptax
# Usage:
#   docker build -t iptax-test . && docker run -it iptax-test
#
# Note: This intentionally does NOT install system dependencies to test
# error handling when they are missing.
#
# PyPI release pending did PR #311. Until then, install from source.

FROM registry.access.redhat.com/ubi10/python-312-minimal:latest

USER 1001

# Install pipx for isolated application install
RUN pip install --user pipx && \
    ~/.local/bin/pipx ensurepath

ENV PATH="/home/default/.local/bin:$PATH"

# Install iptax from git source (PyPI blocked until did PR #311 merges)
# After PyPI release, change to: pipx install iptax
RUN pipx install git+https://github.com/cardil/iptax.git

# Verify installation
RUN iptax --help

# Install browser (Playwright Firefox)
RUN iptax init

# Default command shows version and help
CMD ["iptax", "--help"]
