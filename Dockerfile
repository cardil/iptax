# Dockerfile for testing fresh install of iptax
# Usage:
#   docker build -t iptax-test . && docker run -it iptax-test
#
# PyPI release pending did PR #311. Until then, install from source.

FROM registry.access.redhat.com/ubi10/python-312-minimal:latest

# Install required system dependencies:
# - git: for pip git+https:// installs
# - krb5-devel, gcc, python3-devel: for gssapi build
#   (required by did -> requests-gssapi)
# - pango, cairo, gdk-pixbuf2, fontconfig: for WeasyPrint PDF generation
USER root
RUN microdnf install -y \
        git krb5-devel gcc python3-devel \
        pango cairo gdk-pixbuf2 fontconfig \
    && microdnf clean all
USER 1001

# Install pipx for isolated application install
RUN pip install pipx && \
    pipx ensurepath

ENV PATH="/opt/app-root/src/.local/bin:$PATH"

# Install iptax from git source (PyPI blocked until did PR #311 merges)
# After PyPI release, change to: pipx install iptax
RUN pipx install git+https://github.com/cardil/iptax.git

# Verify installation
RUN iptax --help

# Install browser (Playwright Firefox)
RUN iptax init

# Default command shows version and help
CMD ["iptax", "--help"]
