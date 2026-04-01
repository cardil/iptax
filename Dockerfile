# Dockerfile for testing fresh install of iptax
# Usage:
#   docker build -t iptax-test . && docker run -it iptax-test
#
# Install iptax from PyPI (did PR #311 merged, released as did 0.23.1)

FROM registry.access.redhat.com/ubi10/python-312-minimal:latest

# Install required system dependencies:
# - krb5-devel, gcc, python3-devel: for gssapi build
#   (required by did -> requests-gssapi)
# - pango, cairo, gdk-pixbuf2, fontconfig: for WeasyPrint PDF generation
USER root
RUN microdnf install -y \
        krb5-devel gcc python3-devel \
        pango cairo gdk-pixbuf2 fontconfig \
    && microdnf clean all
USER 1001

# Install pipx for isolated application install
RUN pip install pipx && \
    pipx ensurepath

ENV PATH="/opt/app-root/src/.local/bin:$PATH"

# Install iptax from PyPI
RUN pipx install iptax

# Verify installation
RUN iptax --help

# Install browser (Playwright Firefox)
RUN iptax init

# Default command shows version and help
CMD ["iptax", "--help"]
