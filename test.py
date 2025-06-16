#!/usr/bin/env python3

import asyncio
import json
import os
from mcp.client.sse import sse_client
from mcp import ClientSession
import aiohttp
import aiofiles
from dotenv import load_dotenv

# Define MCP server URLs (from environment variables or defaults)
CSRC_MCP_URL = os.getenv("CSRC_MCP_URL", "http://localhost:8002/sse")
ESMA_MCP_URL = os.getenv("ESMA_MCP_URL", "http://localhost:8001/sse")
ANALYSIS_MCP_URL = os.getenv("ANALYSIS_MCP_URL", "http://localhost:8003/sse")

# List of tools for each server
MCP_SERVERS = {
    "CSRC Server": {
        "url": CSRC_MCP_URL,
        "tools": {
            "fetch_csrc_documents": {
                "description": "Fetch CSRC regulatory documents.",
                "arguments": {"document_types": ["Securities Law"], "download_files": True},
            },
            "list_csrc_documents": {
                "description": "List all stored CSRC documents.",
                "arguments": {},
            },
        },
    },
    "ESMA Server": {
        "url": ESMA_MCP_URL,
        "tools": {
            "fetch_esma_documents": {
                "description": "Fetch ESMA regulatory documents.",
                "arguments": {"document_types": ["MiFID II"], "download_files": True},
            },
            "list_esma_documents": {
                "description": "List all stored ESMA documents.",
                "arguments": {},
            },
        },
    },
    "Analysis Server": {
        "url": ANALYSIS_MCP_URL,
        "tools": {
            "summarize_regulatory_documents": {
                "description": "Summarize regulatory documents for a source.",
                "arguments": {"source": "csrc", "doc_type": "Securities Law"},
            },
            "compare_regulatory_documents": {
                "description": "Compare regulatory documents between sources.",
                "arguments": {"source1": "csrc", "source2": "esma", "doc_types": ["Securities Law", "MiFID II"]},
            },
            "generate_comparative_report": {
                "description": "Generate a detailed comparative report.",
                "arguments": {"source1": "csrc", "source2": "esma", "doc_types": ["Securities Law", "MiFID II"]},
            },
            "get_analysis_summary": {
                "description": "Get analysis summary for a source.",
                "arguments": {"source": "csrc"},
            },
        },
    },
}


async def test_tool(server_name: str, tool_name: str, custom_args: dict = None):
    """Test a single tool from any MCP server."""
    server_info = MCP_SERVERS.get(server_name)
    if not server_info:
        print(f"Error: Server '{server_name}' not configured.")
        return

    url = server_info["url"]
    tool_info = server_info["tools"].get(tool_name)
    if not tool_info:
        print(f"Error: Tool '{tool_name}' not found for server '{server_name}'.")
        return

    arguments = custom_args if custom_args else tool_info["arguments"]
    print(f"\n=== Testing '{tool_name}' on '{server_name}' ===")

    try:
        async with sse_client(url=url) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                response = await session.call_tool(tool_name, arguments=arguments)
                response_data = json.loads(response.content[0].text)
                print(f"Tool '{tool_name}' Response:\n{json.dumps(response_data, indent=2)}")
    except Exception as e:
        print(f"Error testing tool: {tool_name}. Exception: {str(e)}")


async def test_all_tools():
    """Run all tools on all configured MCP servers."""
    print("\n=== Running Complete Test Suite ===")
    results = []

    for server_name, server_info in MCP_SERVERS.items():
        url = server_info["url"]

        async with sse_client(url=url) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                print(f"\n--- Testing tools on server: {server_name} ---")
                for tool_name, tool_info in server_info["tools"].items():
                    try:
                        print(f"\n--- Testing tool: {tool_name} ---")
                        response = await session.call_tool(tool_name, arguments=tool_info["arguments"])
                        response_data = json.loads(response.content[0].text)
                        print(f"Response for '{tool_name}':\n{json.dumps(response_data, indent=2)}")
                        results.append({tool_name: response_data})
                    except Exception as e:
                        print(f"Error testing tool '{tool_name}' on server '{server_name}': {str(e)}")
                        results.append({tool_name: {"error": str(e)}})

    print("\n=== Test Suite Summary ===")
    print(json.dumps(results, indent=2))


def display_servers_and_tools():
    """Display all configured servers and their tools."""
    print("\nConfigured Servers and Tools:")
    for server_name, server_info in MCP_SERVERS.items():
        print(f"\nServer: {server_name} (URL: {server_info['url']})")
        for tool_name, tool_info in server_info["tools"].items():
            print(f"  - Tool: {tool_name} - {tool_info['description']}")


def main():
    """Command-line interface for testing multiple MCP servers."""
    # Load environment variables
    print("\n=== MCP Multi-Server CLI Test ===")
    print("Ensure all MCP servers are running and accessible at their URLs.\n")

    print("Options:")
    print("  1. View all servers and tools")
    print("  2. Test a specific tool")
    print("  3. Run full test suite for all servers")
    print("  4. Exit\n")

    while True:
        choice = input("Enter your choice (1-4): ").strip()

        if choice == "1":
            display_servers_and_tools()

        elif choice == "2":
            server_name = input("\nEnter server name: ").strip()
            tool_name = input("Enter tool name: ").strip()
            custom_args_input = input("Enter custom arguments as JSON (or press Enter to use defaults): ").strip()

            try:
                custom_args = json.loads(custom_args_input) if custom_args_input else None
                asyncio.run(test_tool(server_name, tool_name, custom_args))
            except Exception as e:
                print(f"Invalid arguments: {str(e)}")

        elif choice == "3":
            asyncio.run(test_all_tools())

        elif choice == "4":
            print("\nExiting MCP Multi-Server CLI Test.")
            break

        else:
            print("Invalid choice. Please enter a number between 1 and 4.")


if __name__ == "__main__":
    main()
