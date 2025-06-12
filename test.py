#!/usr/bin/env python3

import asyncio
import json
import os
import aiohttp
from mcp import ClientSession
from mcp.client.sse import sse_client

async def test_esma_server():
    """Test ESMA MCP server"""
    try:
        esma_url = os.getenv("ESMA_MCP_URL", "http://localhost:8001/sse")
        print(f"\nTesting ESMA server at: {esma_url}")
        
        async with sse_client(url=esma_url) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                
                # Test ESMA document fetching
                print("\nTesting ESMA document fetch...")
                esma_result = await session.call_tool(
                    "fetch_esma_documents",
                    arguments={"document_types": ["MiFID II"]}
                )
                esma_data = json.loads(esma_result.content[0].text)
                print(f"ESMA fetch result: {esma_data.get('finalResponse', 'No response')}")
                
                # List local documents
                print("\nListing ESMA local documents...")
                list_result = await session.call_tool("list_local_documents")
                list_data = json.loads(list_result.content[0].text)
                print(f"List documents result: {list_data.get('finalResponse', 'No response')}")
                
                return "SUCCESS" if all(r.get('finalResponse') == "SUCCESS" for r in [esma_data, list_data]) else "FAILED"
    
    except Exception as e:
        print(f"Error testing ESMA server: {str(e)}")
        return "FAILED"

async def test_csrc_server():
    """Test CSRC MCP server"""
    try:
        csrc_url = os.getenv("CSRC_MCP_URL", "http://localhost:8002/sse")
        print(f"\nTesting CSRC server at: {csrc_url}")
        
        async with sse_client(url=csrc_url) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                
                # Test CSRC document fetching
                print("\nTesting CSRC document fetch...")
                csrc_result = await session.call_tool(
                    "fetch_csrc_documents",
                    arguments={"document_types": ["Securities Law"]}
                )
                csrc_data = json.loads(csrc_result.content[0].text)
                print(f"CSRC fetch result: {csrc_data.get('finalResponse', 'No response')}")
                
                # List local documents
                print("\nListing CSRC local documents...")
                list_result = await session.call_tool("list_local_documents")
                list_data = json.loads(list_result.content[0].text)
                print(f"List documents result: {list_data.get('finalResponse', 'No response')}")
                
                return "SUCCESS" if all(r.get('finalResponse') == "SUCCESS" for r in [csrc_data, list_data]) else "FAILED"
    
    except Exception as e:
        print(f"Error testing CSRC server: {str(e)}")
        return "FAILED"

async def test_common_tools_server():
    """Test Common Tools MCP server"""
    try:
        tools_url = os.getenv("COMMON_TOOLS_MCP_URL", "http://localhost:8003/sse")
        print(f"\nTesting Common Tools server at: {tools_url}")
        
        async with sse_client(url=tools_url) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                
                # Test document summarization
                print("\nTesting document summarization...")
                summary_result = await session.call_tool(
                    "summarize_documents",
                    arguments={"source": "esma", "doc_type": "MiFID II"}
                )
                summary_data = json.loads(summary_result.content[0].text)
                print(f"Summarization result: {summary_data.get('finalResponse', 'No response')}")
                
                # Test document comparison
                print("\nTesting document comparison...")
                compare_result = await session.call_tool(
                    "compare_documents",
                    arguments={"source1": "esma", "source2": "csrc"}
                )
                compare_data = json.loads(compare_result.content[0].text)
                print(f"Comparison result: {compare_data.get('finalResponse', 'No response')}")
                
                return "SUCCESS" if all(r.get('finalResponse') == "SUCCESS" for r in [summary_data, compare_data]) else "FAILED"
    
    except Exception as e:
        print(f"Error testing Common Tools server: {str(e)}")
        return "FAILED"

async def test_all_servers():
    """Test all MCP servers"""
    print("Testing Enhanced Regulatory Documents System...")
    print("============================================")
    
    try:
        # Test all servers in sequence
        esma_result = await test_esma_server()
        csrc_result = await test_csrc_server()
        tools_result = await test_common_tools_server()
        
        # Print summary
        print("\nTest Results Summary:")
        print("=====================")
        print(f"ESMA Server: {esma_result}")
        print(f"CSRC Server: {csrc_result}")
        print(f"Common Tools Server: {tools_result}")
        
        all_success = all(result == "SUCCESS" for result in [esma_result, csrc_result, tools_result])
        print("\nOverall Test Result:", "SUCCESS" if all_success else "FAILED")
    
    except Exception as e:
        print(f"\nTest suite failed: {str(e)}")
        print("\nOverall Test Result: FAILED")

if __name__ == "__main__":
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("python-dotenv not installed, skipping .env file loading")
    
    # Run the test suite
    asyncio.run(test_all_servers())