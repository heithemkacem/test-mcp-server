#!/usr/bin/env python3

import asyncio
import json
import os
import re
from typing import Dict, List, Any, Optional
from mcp.client.sse import sse_client
from mcp import ClientSession
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MCP server URLs
CSRC_MCP_URL = os.getenv("CSRC_MCP_URL", "http://localhost:8002/sse")
ESMA_MCP_URL = os.getenv("ESMA_MCP_URL", "http://localhost:8001/sse")
ANALYSIS_MCP_URL = os.getenv("ANALYSIS_MCP_URL", "http://localhost:8003/sse")

# Azure OpenAI configuration
azure_client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

# Azure OpenAI deployment name
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")

# Complete tool definitions with all available tools
MCP_TOOLS = {
    "CSRC": {
        "url": CSRC_MCP_URL,
        "tools": {
            "fetch_csrc_documents": {
                "description": "Fetch CSRC regulatory documents from specified categories and regions",
                "parameters": {
                    "document_types": "List of document types (e.g., ['Securities Law', 'Market Regulation', 'Disclosure Rules', 'Listed Company Rules'])",
                    "regions": "List of CSRC regions (['main', 'shanghai', 'shenzhen', 'beijing'])",
                    "download_files": "Whether to download files locally (boolean)",
                    "include_regional": "Whether to include regional office content (boolean)"
                }
            },
            "search_csrc_documents": {
                "description": "Search CSRC websites for specific documents",
                "parameters": {
                    "query": "Search query string",
                    "regions": "List of CSRC regions to search",
                    "download_files": "Whether to download found documents"
                }
            },
            "list_csrc_documents": {
                "description": "List all locally stored CSRC documents",
                "parameters": {}
            },
            "get_csrc_document_categories": {
                "description": "Get available CSRC document categories and regions",
                "parameters": {}
            },
            "analyze_csrc_document": {
                "description": "Analyze a locally stored CSRC document",
                "parameters": {
                    "file_path": "Path to the document file to analyze"
                }
            },
            "get_csrc_document_stats": {
                "description": "Get statistics about locally stored CSRC documents",
                "parameters": {}
            },
            "clean_csrc_documents": {
                "description": "Clean up old CSRC documents",
                "parameters": {
                    "older_than_days": "Remove documents older than this many days",
                    "dry_run": "If True, only report what would be deleted"
                }
            },
            "csrc_health_check": {
                "description": "Check CSRC MCP server health and connectivity",
                "parameters": {}
            }
        }
    },
    "ESMA": {
        "url": ESMA_MCP_URL,
        "tools": {
            "fetch_esma_documents": {
                "description": "Fetch ESMA regulatory documents from specific categories",
                "parameters": {
                    "document_types": "List of document types (['MiFID II', 'MiFIR', 'MiCA', 'DORA'])",
                    "download_files": "Whether to download files locally",
                    "include_news": "Whether to include recent news and publications"
                }
            },
            "search_esma_documents": {
                "description": "Search ESMA website for specific documents",
                "parameters": {
                    "query": "Search query (e.g., 'MiFID transparency', 'crypto assets')",
                    "download_files": "Whether to download found documents"
                }
            },
            "list_esma_documents": {
                "description": "List all locally stored ESMA documents with counts by category",
                "parameters": {}
            },
            "get_esma_sections": {
                "description": "Get available ESMA website sections and document categories",
                "parameters": {}
            }
        }
    },
    "ANALYSIS": {
        "url": ANALYSIS_MCP_URL,
        "tools": {
            "summarize_regulatory_documents": {
                "description": "Summarize regulatory documents from specified source",
                "parameters": {
                    "source": "Source of documents ('esma' or 'csrc')",
                    "doc_type": "Optional filter by document type"
                }
            },
            "compare_regulatory_documents": {
                "description": "Compare regulatory documents between sources or within same source",
                "parameters": {
                    "source1": "First source ('esma' or 'csrc')",
                    "source2": "Second source (optional)",
                    "doc_types": "Optional filter by document types"
                }
            },
            "generate_comparative_report": {
                "description": "Generate comprehensive comparative analysis report",
                "parameters": {
                    "source1": "First source ('esma' or 'csrc')",
                    "source2": "Second source (optional)",
                    "doc_types": "Optional filter by document types"
                }
            },
            "get_analysis_summary": {
                "description": "Get summary of all analysis activities for a source",
                "parameters": {
                    "source": "Source to analyze ('esma' or 'csrc')"
                }
            },
            "get_document_details": {
                "description": "Get detailed information about a specific document",
                "parameters": {
                    "source": "Source of document ('esma' or 'csrc')",
                    "document_name": "Name of the document to analyze"
                }
            },
            "cleanup_analysis_files": {
                "description": "Clean up old analysis files",
                "parameters": {
                    "source": "Source to clean ('esma' or 'csrc')",
                    "category": "Optional category to clean",
                    "older_than_days": "Remove files older than this many days"
                }
            }
        }
    }
}


class MCPAgent:
    def __init__(self):
        self.tool_descriptions = self._build_tool_descriptions()
    
    def _build_tool_descriptions(self) -> str:
        """Build a comprehensive description of all available tools for the LLM."""
        descriptions = []
        for server_name, server_info in MCP_TOOLS.items():
            descriptions.append(f"\n{server_name} Server Tools:")
            for tool_name, tool_info in server_info["tools"].items():
                descriptions.append(f"- {tool_name}: {tool_info['description']}")
                if tool_info["parameters"]:
                    params = ", ".join([f"{k}: {v}" for k, v in tool_info["parameters"].items()])
                    descriptions.append(f"  Parameters: {params}")
        return "\n".join(descriptions)
    
    def _extract_json_from_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response, handling cases where it's wrapped in text."""
        # First try to parse the entire response as JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON within code blocks
        json_patterns = [
            r'```json\n(.*?)\n```',
            r'```\n(.*?)\n```',
            r'\{.*\}',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, response_text, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _create_fallback_analysis(self, user_query: str) -> Dict[str, Any]:
        """Create a fallback analysis when LLM analysis fails."""
        query_lower = user_query.lower()
        
        # Simple keyword-based fallback
        if any(word in query_lower for word in ['latest', 'new', 'recent', 'law', 'regulation']):
            if 'csrc' in query_lower or 'china' in query_lower:
                return {
                    "intent": "User wants latest CSRC regulations",
                    "tools_to_call": [
                        {
                            "server": "CSRC",
                            "tool": "fetch_csrc_documents",
                            "parameters": {
                                "document_types": ["Securities Law", "Market Regulation"],
                                "regions": ["main"],
                                "download_files": True,
                                "include_regional": False
                            },
                            "reason": "Fetch latest CSRC documents"
                        }
                    ],
                    "response_strategy": "Provide information about latest CSRC regulations"
                }
            elif 'esma' in query_lower or 'eu' in query_lower or 'europe' in query_lower:
                return {
                    "intent": "User wants latest ESMA regulations",
                    "tools_to_call": [
                        {
                            "server": "ESMA",
                            "tool": "fetch_esma_documents",
                            "parameters": {
                                "document_types": ["MiFID II", "MiFIR"],
                                "download_files": True,
                                "include_news": True
                            },
                            "reason": "Fetch latest ESMA documents"
                        }
                    ],
                    "response_strategy": "Provide information about latest ESMA regulations"
                }
        
        # Default fallback - get document categories
        return {
            "intent": "General query about regulatory documents",
            "tools_to_call": [
                {
                    "server": "CSRC",
                    "tool": "get_csrc_document_categories",
                    "parameters": {},
                    "reason": "Get available CSRC document categories"
                }
            ],
            "response_strategy": "Provide overview of available regulatory documents"
        }
    
    async def analyze_query(self, user_query: str) -> Dict[str, Any]:
        """Use LLM to analyze user query and determine which tools to call."""
        system_prompt = f"""You are an expert regulatory document analysis assistant. You have access to the following MCP tools:

{self.tool_descriptions}

Your task is to analyze user queries and determine:
1. Which tools to call to answer the query
2. What parameters to use for each tool
3. The order in which to call the tools

IMPORTANT: You MUST respond with valid JSON only. Do not include any explanatory text before or after the JSON.

Return your analysis as a JSON object with this exact structure:
{{
    "intent": "Brief description of what the user wants",
    "tools_to_call": [
        {{
            "server": "CSRC",
            "tool": "tool_name",
            "parameters": {{"param1": "value1", "param2": "value2"}},
            "reason": "Why this tool is needed"
        }}
    ],
    "response_strategy": "How to combine the tool results into a coherent answer"
}}

Rules:
- Always prefer specific searches over general listings when the user has specific requirements
- For comparison queries, use analysis tools
- For document fetching, use appropriate fetch tools
- For searching, use search tools
- Consider the logical order of operations (e.g., list documents before analyzing specific ones)
- Respond with JSON only, no additional text
"""

        try:
            response = azure_client.chat.completions.create(
                model=AZURE_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            response_text = response.choices[0].message.content.strip()
            print(f"Raw LLM response: {response_text}")  # Debug output
            
            # Try to extract JSON from the response
            analysis = self._extract_json_from_response(response_text)
            
            if analysis is None:
                print("Failed to parse JSON from LLM response, using fallback")
                return self._create_fallback_analysis(user_query)
            
            # Validate the analysis structure
            if not all(key in analysis for key in ["intent", "tools_to_call", "response_strategy"]):
                print("Invalid analysis structure, using fallback")
                return self._create_fallback_analysis(user_query)
            
            return analysis
            
        except Exception as e:
            print(f"Error in query analysis: {e}")
            return self._create_fallback_analysis(user_query)
    
    async def call_tool(self, server: str, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific MCP tool and return the result."""
        server_info = MCP_TOOLS.get(server)
        if not server_info:
            return {"error": f"Server {server} not found"}
        
        url = server_info["url"]
        print(f"Connecting to {server} at {url}")  # Debug output
        
        try:
            async with sse_client(url=url) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    print(f"Calling tool {tool_name} with parameters: {parameters}")  # Debug output
                    response = await session.call_tool(tool_name, arguments=parameters)
                    
                    if hasattr(response, 'content') and response.content:
                        if isinstance(response.content[0], dict):
                            return response.content[0]
                        else:
                            return json.loads(response.content[0].text)
                    else:
                        return {"error": "Empty response from tool"}
                        
        except Exception as e:
            print(f"Detailed error calling {tool_name}: {str(e)}")  # More detailed error
            return {"error": f"Error calling {tool_name}: {str(e)}"}
    
    async def generate_response(self, user_query: str, tool_results: List[Dict[str, Any]], analysis: Dict[str, Any]) -> str:
        """Generate a natural language response based on tool results."""
        system_prompt = """You are a helpful regulatory document assistant. Based on the user's query and the results from various regulatory document tools, provide a comprehensive, natural language response.

Guidelines:
- Synthesize information from multiple tool results
- Provide specific details when available
- Highlight important regulatory information
- If there are errors in tool results, acknowledge them briefly but focus on successful results
- Use professional but accessible language
- Structure your response logically
- Include relevant numbers, dates, and specifics when available
"""

        # Filter out error results for cleaner output
        successful_results = [r for r in tool_results if "error" not in r.get("result", {})]
        
        tool_results_text = json.dumps(successful_results, indent=2)
        
        try:
            response = azure_client.chat.completions.create(
                model=AZURE_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User Query: {user_query}\n\nTool Results: {tool_results_text}\n\nPlease provide a comprehensive response based on this information."}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating response: {str(e)}"
    
    async def process_query(self, user_query: str) -> str:
        """Main method to process a user query end-to-end."""
        print(f"Processing query: {user_query}")
        
        # Step 1: Analyze the query
        print("Analyzing query...")
        analysis = await self.analyze_query(user_query)
        print(f"Analysis: {analysis['intent']}")
        print(f"Tools to call: {len(analysis['tools_to_call'])}")
        
        # Step 2: Call the identified tools
        tool_results = []
        for i, tool_call in enumerate(analysis["tools_to_call"]):
            print(f"Calling tool {i+1}/{len(analysis['tools_to_call'])}: {tool_call['server']}.{tool_call['tool']}...")
            result = await self.call_tool(
                tool_call["server"],
                tool_call["tool"],
                tool_call["parameters"]
            )
            tool_results.append({
                "tool": f"{tool_call['server']}.{tool_call['tool']}",
                "parameters": tool_call["parameters"],
                "result": result,
                "reason": tool_call["reason"]
            })
            print(f"Tool result: {'Success' if 'error' not in result else 'Error'}")
        
        # Step 3: Generate response
        print("Generating response...")
        response = await self.generate_response(user_query, tool_results, analysis)
        
        return response


async def interactive_qa():
    """Interactive Q&A session."""
    agent = MCPAgent()
    
    print("=== MCP Regulatory Document Q&A Agent ===")
    print("Ask questions about regulatory documents from CSRC and ESMA.")
    print("Type 'quit' to exit, 'help' for examples.\n")
    
    while True:
        user_input = input("Your question: ").strip()
        
        if user_input.lower() == 'quit':
            print("Goodbye!")
            break
        
        if user_input.lower() == 'help':
            print("\nExample questions:")
            print("- What are the latest CSRC securities laws?")
            print("- Compare MiFID II regulations with CSRC market regulations")
            print("- Search for documents about crypto assets in ESMA")
            print("- Show me statistics about stored regulatory documents")
            print("- Analyze the differences between EU and Chinese disclosure rules")
            print("- What categories of documents are available from CSRC?")
            print("")
            continue
        
        if not user_input:
            continue
        
        try:
            print("\n" + "="*50)
            response = await agent.process_query(user_input)
            print(f"\nResponse:\n{response}")
            print("="*50 + "\n")
        except Exception as e:
            print(f"Error processing query: {e}")


def main():
    """Main entry point."""
    # Check for required Azure OpenAI environment variables
    required_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT_NAME"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("Error: The following environment variables are required:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set them in your .env file or environment.")
        print("\nExample .env file:")
        print("AZURE_OPENAI_API_KEY=your_api_key_here")
        print("AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/")
        print("AZURE_OPENAI_DEPLOYMENT_NAME=your-gpt4-deployment-name")
        print("AZURE_OPENAI_API_VERSION=2024-02-15-preview")
        return
    
    print("Starting MCP Q&A Agent with Azure OpenAI...")
    asyncio.run(interactive_qa())


if __name__ == "__main__":
    main()