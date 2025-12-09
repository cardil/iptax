# Dockerfile for testing fresh install of iptax from TestPyPI
# Usage:
#   First publish to TestPyPI: make PYPI_REPO=testpypi publish
#   Then build and run: docker build -t iptax-test . && docker run -it iptax-test
#
# Note: This intentionally does NOT install system dependencies to test
# error handling when they are missing.

FROM registry.access.redhat.com/ubi10/python-312-minimal:latest

USER 1001

# Install pipx for isolated application install
RUN pip install --user pipx && \
    ~/.local/bin/pipx ensurepath

ENV PATH="/home/default/.local/bin:$PATH"

# Install iptax from TestPyPI (with fallback to PyPI for dependencies)
# Note: TestPyPI may not have all dependencies, so we use --extra-index-url
ARG PYPI_INDEX=https://test.pypi.org/simple/
RUN pipx install --index-url "${PYPI_INDEX}" \
    --pip-args="--extra-index-url https://pypi.org/simple/" \
    iptax

# Verify installation
RUN iptax --help

# Install browser (Playwright Firefox)
RUN iptax init

# Default command shows version and help
CMD ["iptax", "--help"]
