FROM python:3.11-slim

ARG INSTALL_LATEX=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OVERLEAF_CE_MCP_TEMPLATE_ROOT=/opt/overleaf-ce-mcp/overleaf_ce_mcp/templates

WORKDIR /opt/overleaf-ce-mcp

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        zip \
        unzip \
    && if [ "$INSTALL_LATEX" = "1" ]; then \
        apt-get install -y --no-install-recommends texlive-latex-base texlive-latex-extra latexmk; \
    fi \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY overleaf_ce_mcp ./overleaf_ce_mcp
COPY templates ./templates
COPY vendor_patches ./vendor_patches
COPY docs ./docs

RUN pip install --upgrade pip \
    && pip install .

ENTRYPOINT ["overleaf-ce-mcp"]
