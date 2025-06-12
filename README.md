# Regulatory Documents MCP Servers

This project consists of three Model Context Protocol (MCP) servers designed to fetch, summarize, and compare regulatory documents from ESMA and CSRC.

## Components

1. **ESMA MCP Server** (Port 8001)

   - Fetches documents from European Securities and Markets Authority (ESMA)
   - Handles documents like MiFID II, MiFIR, Prospectus Regulation, MAR, and MiCA
   - Located in `esma_mcp/`

2. **CSRC MCP Server** (Port 8002)

   - Fetches documents from China Securities Regulatory Commission (CSRC)
   - Handles Securities Law and other regulatory documents
   - Located in `csrc_mcp/`

3. **Common Tools MCP Server** (Port 8003)
   - Provides document summarization and comparison capabilities
   - Works with documents from both ESMA and CSRC
   - Located in `common_tools_mcp/`

## Installation

Each server has its own requirements file. To install all dependencies:

```bash
# Install ESMA server dependencies
pip install -r esma_mcp/requirements.txt

# Install CSRC server dependencies
pip install -r csrc_mcp/requirements.txt

# Install Common Tools server dependencies
pip install -r common_tools_mcp/requirements.txt
```

## Running the Servers

You can run all servers at once using the provided script:

```bash
./start_servers.sh
```

Or run them individually:

```bash
# Run ESMA server
python esma_mcp/src/esma_server.py

# Run CSRC server
python csrc_mcp/src/csrc_server.py

# Run Common Tools server
python common_tools_mcp/src/common_tools_server.py
```

## Testing

To test all servers:

```bash
python test.py
```

## Environment Variables

The following environment variables can be set:

- `ESMA_MCP_PORT` (default: 8001)
- `CSRC_MCP_PORT` (default: 8002)
- `COMMON_TOOLS_MCP_PORT` (default: 8003)
- `ESMA_MCP_URL` (default: http://localhost:8001/sse)
- `CSRC_MCP_URL` (default: http://localhost:8002/sse)
- `COMMON_TOOLS_MCP_URL` (default: http://localhost:8003/sse)

You can set these in a `.env` file.

## Directory Structure

```
.
├── esma_mcp/
│   ├── requirements.txt
│   └── src/
│       └── esma_server.py
├── csrc_mcp/
│   ├── requirements.txt
│   └── src/
│       └── csrc_server.py
├── common_tools_mcp/
│   ├── requirements.txt
│   └── src/
│       └── common_tools_server.py
├── regulatory_docs/
│   ├── esma/
│   │   ├── raw/
│   │   ├── processed/
│   │   ├── summaries/
│   │   └── comparisons/
│   └── csrc/
│       ├── raw/
│       ├── processed/
│       ├── summaries/
│       └── comparisons/
├── start_servers.sh
└── test.py
```

## Available Tools

### ESMA Server Tools

- `fetch_esma_documents`: Fetch documents from ESMA website
- `list_local_documents`: List locally stored ESMA documents

### CSRC Server Tools

- `fetch_csrc_documents`: Fetch documents from CSRC website
- `list_local_documents`: List locally stored CSRC documents

### Common Tools Server

- `summarize_documents`: Generate summaries for downloaded documents
- `compare_documents`: Compare documents between or within regulatory bodies

## Example Usage

```python
from mcp import ClientSession
from mcp.client.sse import sse_client

async with sse_client(url="http://localhost:8001/sse") as streams:
    async with ClientSession(*streams) as session:
        await session.initialize()

        # Fetch MiFID II documents from ESMA
        result = await session.call_tool(
            "fetch_esma_documents",
            arguments={"document_types": ["MiFID II"]}
        )
```
