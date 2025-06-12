#!/usr/bin/env python3

import os
import json
from pathlib import Path
import logging
from datetime import datetime
import PyPDF2
from docx import Document
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMMON_TOOLS_MCP_PORT = os.getenv("COMMON_TOOLS_MCP_PORT", "8003")

# Create an MCP server
mcp = FastMCP("common-tools-mcp", port=int(COMMON_TOOLS_MCP_PORT))

class CommonToolsAgent:
    def __init__(self):
        self.base_folders = {
            'esma': 'regulatory_docs/esma',
            'csrc': 'regulatory_docs/csrc'
        }
        self.create_directories()
    
    def create_directories(self):
        """Create necessary directories for document storage"""
        for folder_path in self.base_folders.values():
            Path(folder_path).mkdir(parents=True, exist_ok=True)
            # Create subdirectories for summaries and comparisons
            for subfolder in ['summaries', 'comparisons']:
                Path(f"{folder_path}/{subfolder}").mkdir(parents=True, exist_ok=True)
    
    def summarize_documents(self, source: str, doc_type: str = None) -> dict:
        """Summarize documents using LLM"""
        try:
            raw_folder = os.path.join(self.base_folders[source], 'raw')
            summaries_folder = os.path.join(self.base_folders[source], 'summaries')
            
            summaries = []
            
            # Check if raw folder exists
            if not os.path.exists(raw_folder):
                return {
                    "finalResponse": "FAILED",
                    "error": f"No documents found in {raw_folder}",
                    "timestamp": datetime.now().isoformat()
                }
            
            for filename in os.listdir(raw_folder):
                if doc_type and doc_type.lower().replace(' ', '_') not in filename.lower():
                    continue
                
                file_path = os.path.join(raw_folder, filename)
                
                # Extract text from document
                extracted_text = self._extract_text_from_file(file_path)
                
                if extracted_text:
                    # Generate summary using your existing LLM setup
                    summary = self._generate_summary(extracted_text, filename, source)
                    
                    # Save summary
                    summary_filename = f"summary_{filename}.json"
                    summary_path = os.path.join(summaries_folder, summary_filename)
                    
                    with open(summary_path, 'w', encoding='utf-8') as f:
                        json.dump(summary, f, indent=2, ensure_ascii=False)
                    
                    summaries.append({
                        "original_file": filename,
                        "summary_file": summary_filename,
                        "summary": summary
                    })
            
            return {
                "finalResponse": "SUCCESS",
                "source": source,
                "summaries_generated": len(summaries),
                "summaries": summaries,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error summarizing documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"Document summarization failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _extract_text_from_file(self, file_path: str) -> str:
        """Extract text from various file formats"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.pdf':
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text()
                    return text
            
            elif file_ext in ['.doc', '.docx']:
                doc = Document(file_path)
                return '\n'.join([paragraph.text for paragraph in doc.paragraphs])
            
            elif file_ext == '.html':
                with open(file_path, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f.read(), 'html.parser')
                    return soup.get_text()
            
            elif file_ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            else:
                logger.warning(f"Unsupported file format: {file_ext}")
                return ""
        
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {str(e)}")
            return ""
    
    def _generate_summary(self, text: str, filename: str, source: str) -> dict:
        """Generate summary using LLM - placeholder for your LLM integration"""
        # This is where you'd integrate with your LLM setup
        # For now, returning a structured placeholder
        text_sample = text[:2000] if len(text) > 2000 else text
        
        return {
            "document_name": filename,
            "source": source,
            "summary": f"Summary of {filename} - regulatory document from {source.upper()}. Document contains {len(text)} characters of regulatory content.",
            "key_points": [
                "Key regulatory requirement 1 (from document content)",
                "Key regulatory requirement 2 (from document content)",
                "Key regulatory requirement 3 (from document content)"
            ],
            "compliance_requirements": [
                "Compliance obligation 1 (extracted from text)",
                "Compliance obligation 2 (extracted from text)"
            ],
            "effective_dates": ["Date information if available in document"],
            "penalties": ["Penalty information if available in document"],
            "text_length": len(text),
            "generated_timestamp": datetime.now().isoformat()
        }
    
    def compare_documents(self, source1: str, source2: str = None, doc_types: list = None) -> dict:
        """Compare documents between sources or within same source"""
        try:
            if source2 is None:
                source2 = source1
            
            comparison_results = []
            
            # Get summaries from both sources
            summaries1 = self._get_summaries_from_source(source1, doc_types)
            summaries2 = self._get_summaries_from_source(source2, doc_types)
            
            # Perform comparison
            for summary1 in summaries1:
                for summary2 in summaries2:
                    if source1 == source2 and summary1 == summary2:
                        continue  # Skip comparing document with itself
                    
                    comparison = self._compare_two_documents(summary1, summary2)
                    comparison_results.append(comparison)
            
            # Save comparison results
            comparison_filename = f"comparison_{source1}_{source2}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            comparison_path = os.path.join(self.base_folders[source1], 'comparisons', comparison_filename)
            
            with open(comparison_path, 'w', encoding='utf-8') as f:
                json.dump(comparison_results, f, indent=2, ensure_ascii=False)
            
            return {
                "finalResponse": "SUCCESS",
                "comparison_file": comparison_filename,
                "comparisons_made": len(comparison_results),
                "results": comparison_results,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error comparing documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"Document comparison failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _get_summaries_from_source(self, source: str, doc_types: list = None) -> list:
        """Get all summaries from a source"""
        summaries_folder = os.path.join(self.base_folders[source], 'summaries')
        summaries = []
        
        if not os.path.exists(summaries_folder):
            return summaries
        
        for filename in os.listdir(summaries_folder):
            if filename.endswith('.json'):
                if doc_types:
                    # Filter by document types if specified
                    if not any(doc_type.lower().replace(' ', '_') in filename.lower() for doc_type in doc_types):
                        continue
                
                file_path = os.path.join(summaries_folder, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        summary = json.load(f)
                        summaries.append(summary)
                except Exception as e:
                    logger.error(f"Error reading summary file {filename}: {str(e)}")
        
        return summaries
    
    def _compare_two_documents(self, doc1: dict, doc2: dict) -> dict:
        """Compare two document summaries"""
        try:
            # This is where you'd integrate with your LLM-based comparison
            comparison = {
                "document1": doc1.get("document_name", "Unknown"),
                "document2": doc2.get("document_name", "Unknown"),
                "source1": doc1.get("source", "Unknown"),
                "source2": doc2.get("source", "Unknown"),
                "similarities": [],
                "differences": [],
                "compliance_gaps": [],
                "recommendations": [],
                "comparison_timestamp": datetime.now().isoformat()
            }
            
            # Simple comparison logic (enhance with LLM)
            doc1_points = set(doc1.get("key_points", []))
            doc2_points = set(doc2.get("key_points", []))
            
            comparison["similarities"] = list(doc1_points.intersection(doc2_points))
            comparison["differences"] = {
                "doc1_unique": list(doc1_points - doc2_points),
                "doc2_unique": list(doc2_points - doc1_points)
            }
            
            return comparison
        
        except Exception as e:
            logger.error(f"Error in document comparison: {str(e)}")
            return {
                "error": f"Comparison failed: {str(e)}",
                "document1": doc1.get("document_name", "Unknown"),
                "document2": doc2.get("document_name", "Unknown")
            }

# Initialize the agent
common_tools_agent = CommonToolsAgent()

@mcp.tool()
def summarize_documents(source: str, doc_type: str = None):
    """Summarize regulatory documents from specified source"""
    return json.dumps(common_tools_agent.summarize_documents(source, doc_type))

@mcp.tool()
def compare_documents(source1: str, source2: str = None, doc_types: list = None):
    """Compare regulatory documents between sources"""
    return json.dumps(common_tools_agent.compare_documents(source1, source2, doc_types))

if __name__ == "__main__":
    # Initialize and run the server
    print(f"Starting Common Tools MCP Server on port {COMMON_TOOLS_MCP_PORT}")
    mcp.run(transport='sse')
