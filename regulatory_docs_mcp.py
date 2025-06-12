#!/usr/bin/env python3

import sys
import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import hashlib
import re
from typing import Dict, List, Optional
import PyPDF2
from docx import Document
import logging

from mcp.server.fastmcp import FastMCP

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REGULATORY_DOCS_MCP_PORT = os.getenv("REGULATORY_DOCS_MCP_PORT", "8001")

# Create an MCP server
mcp = FastMCP("regulatory-docs", port=int(REGULATORY_DOCS_MCP_PORT))

class RegulatoryDocumentAgent:
    def __init__(self):
        self.base_folders = {
            'esma': 'regulatory_docs/esma',
            'csrc': 'regulatory_docs/csrc'
        }
        self.create_directories()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def create_directories(self):
        """Create necessary directories for document storage"""
        for folder_path in self.base_folders.values():
            Path(folder_path).mkdir(parents=True, exist_ok=True)
            # Create subdirectories
            for subfolder in ['raw', 'processed', 'summaries', 'comparisons']:
                Path(f"{folder_path}/{subfolder}").mkdir(parents=True, exist_ok=True)
    
    def get_file_hash(self, content):
        """Generate hash for file content to avoid duplicates"""
        return hashlib.md5(content.encode() if isinstance(content, str) else content).hexdigest()
    
    def sanitize_filename(self, filename):
        """Sanitize filename for safe storage"""
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        return filename
    
    def fetch_esma_documents(self, document_types: List[str] = None) -> Dict:
        """Fetch ESMA regulatory documents"""
        if document_types is None:
            document_types = ['MiFID II', 'MiFIR', 'Prospectus Regulation', 'Market Abuse Regulation', 'MiCA']
        
        try:
            base_url = "https://www.esma.europa.eu"
            results = {}
            
            for doc_type in document_types:
                logger.info(f"Fetching ESMA documents for: {doc_type}")
                results[doc_type] = self._fetch_esma_specific_docs(base_url, doc_type)
            
            return {
                "finalResponse": "SUCCESS",
                "source": "ESMA",
                "documents_fetched": results,
                "storage_location": self.base_folders['esma'],
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error fetching ESMA documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"ESMA document fetch failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _fetch_esma_specific_docs(self, base_url: str, doc_type: str) -> Dict:
        """Fetch specific ESMA document type"""
        try:
            # Search for documents related to the specific type
            search_urls = {
                'MiFID II': f"{base_url}/policy-rules/mifid-ii-and-mifir",
                'MiFIR': f"{base_url}/policy-rules/mifid-ii-and-mifir",
                'Prospectus Regulation': f"{base_url}/policy-rules/investment-management/prospectus-regulation",
                'Market Abuse Regulation': f"{base_url}/policy-rules/market-abuse",
                'MiCA': f"{base_url}/policy-rules/crypto-assets"
            }
            
            search_url = search_urls.get(doc_type, f"{base_url}/search?query={doc_type}")
            response = self.session.get(search_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            documents = []
            
            # Look for PDF and document links
            for link in soup.find_all('a', href=True):
                href = link['href']
                if any(ext in href.lower() for ext in ['.pdf', '.doc', '.docx']):
                    full_url = urljoin(base_url, href)
                    title = link.get_text(strip=True) or f"{doc_type}_document"
                    
                    # Download document
                    doc_info = self._download_document(full_url, title, 'esma', doc_type)
                    if doc_info:
                        documents.append(doc_info)
            
            return {
                "documents": documents,
                "count": len(documents),
                "search_url": search_url
            }
        
        except Exception as e:
            logger.error(f"Error fetching {doc_type} from ESMA: {str(e)}")
            return {
                "documents": [],
                "count": 0,
                "error": str(e)
            }
    
    def fetch_csrc_documents(self, document_types: List[str] = None) -> Dict:
        """Fetch CSRC regulatory documents"""
        if document_types is None:
            document_types = ['Securities Law']
        
        try:
            base_url = "http://www.csrc.gov.cn"
            results = {}
            
            for doc_type in document_types:
                logger.info(f"Fetching CSRC documents for: {doc_type}")
                results[doc_type] = self._fetch_csrc_specific_docs(base_url, doc_type)
            
            return {
                "finalResponse": "SUCCESS",
                "source": "CSRC",
                "documents_fetched": results,
                "storage_location": self.base_folders['csrc'],
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error fetching CSRC documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"CSRC document fetch failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _fetch_csrc_specific_docs(self, base_url: str, doc_type: str) -> Dict:
        """Fetch specific CSRC document type"""
        try:
            # CSRC website structure - adjust based on actual site
            search_urls = {
                'Securities Law': f"{base_url}/pub/newsite/flb/flfg/",
            }
            
            search_url = search_urls.get(doc_type, f"{base_url}")
            response = self.session.get(search_url, timeout=30)
            response.raise_for_status()
            
            # Handle Chinese encoding
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.content, 'html.parser')
            documents = []
            
            # Look for document links
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True)
                
                # Look for securities law related documents
                if any(keyword in text.lower() for keyword in ['securities', '证券', 'law', '法']):
                    full_url = urljoin(base_url, href)
                    title = text or f"{doc_type}_document"
                    
                    # For CSRC, we might need to handle HTML pages that contain the law text
                    doc_info = self._download_document(full_url, title, 'csrc', doc_type, is_html=True)
                    if doc_info:
                        documents.append(doc_info)
            
            return {
                "documents": documents,
                "count": len(documents),
                "search_url": search_url
            }
        
        except Exception as e:
            logger.error(f"Error fetching {doc_type} from CSRC: {str(e)}")
            return {
                "documents": [],
                "count": 0,
                "error": str(e)
            }
    
    def _download_document(self, url: str, title: str, source: str, doc_type: str, is_html: bool = False) -> Optional[Dict]:
        """Download and save document"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Create filename
            sanitized_title = self.sanitize_filename(title)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if is_html:
                filename = f"{sanitized_title}_{timestamp}.html"
                content = response.text
            else:
                # Get file extension from URL
                parsed_url = urlparse(url)
                ext = os.path.splitext(parsed_url.path)[1] or '.pdf'
                filename = f"{sanitized_title}_{timestamp}{ext}"
                content = response.content
            
            # Save to raw folder
            file_path = os.path.join(self.base_folders[source], 'raw', filename)
            
            # Check for duplicates
            file_hash = self.get_file_hash(content)
            
            if is_html:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                with open(file_path, 'wb') as f:
                    f.write(content)
            
            logger.info(f"Downloaded: {filename}")
            
            return {
                "title": title,
                "filename": filename,
                "file_path": file_path,
                "url": url,
                "doc_type": doc_type,
                "source": source,
                "file_hash": file_hash,
                "size_bytes": len(content),
                "download_timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error downloading document from {url}: {str(e)}")
            return None
    
    def summarize_documents(self, source: str, doc_type: str = None) -> Dict:
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
    
    def _generate_summary(self, text: str, filename: str, source: str) -> Dict:
        """Generate summary using LLM - placeholder for your LLM integration"""
        try:
            # This is where you'd integrate with your existing LLM setup
            # For now, returning a structured placeholder
            
            # Truncate text for summary
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
        
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return {
                "error": f"Summary generation failed: {str(e)}",
                "document_name": filename,
                "source": source
            }
    
    def compare_documents(self, source1: str, source2: str = None, doc_types: List[str] = None) -> Dict:
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
    
    def _get_summaries_from_source(self, source: str, doc_types: List[str] = None) -> List[Dict]:
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
    
    def _compare_two_documents(self, doc1: Dict, doc2: Dict) -> Dict:
        """Compare two document summaries"""
        try:
            # Placeholder comparison logic - replace with your LLM-based comparison
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
regulatory_agent = RegulatoryDocumentAgent()

@mcp.tool()
def fetch_esma_documents(document_types: List[str] = None):
    """Fetch ESMA regulatory documents"""
    return json.dumps(regulatory_agent.fetch_esma_documents(document_types))

@mcp.tool()
def fetch_csrc_documents(document_types: List[str] = None):
    """Fetch CSRC regulatory documents"""
    return json.dumps(regulatory_agent.fetch_csrc_documents(document_types))

@mcp.tool()
def summarize_regulatory_documents(source: str, doc_type: str = None):
    """Summarize regulatory documents from specified source"""
    return json.dumps(regulatory_agent.summarize_documents(source, doc_type))

@mcp.tool()
def compare_regulatory_documents(source1: str, source2: str = None, doc_types: List[str] = None):
    """Compare regulatory documents between sources"""
    return json.dumps(regulatory_agent.compare_documents(source1, source2, doc_types))

@mcp.tool()
def list_local_documents(source: str = None):
    """List all locally stored documents"""
    try:
        if source:
            sources = [source]
        else:
            sources = list(regulatory_agent.base_folders.keys())
        
        all_documents = {}
        
        for src in sources:
            src_docs = {}
            base_path = regulatory_agent.base_folders[src]
            
            for folder in ['raw', 'processed', 'summaries', 'comparisons']:
                folder_path = os.path.join(base_path, folder)
                if os.path.exists(folder_path):
                    src_docs[folder] = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
                else:
                    src_docs[folder] = []
            
            all_documents[src] = src_docs
        
        result = {
            "finalResponse": "SUCCESS",
            "documents": all_documents,
            "timestamp": datetime.now().isoformat()
        }
        
        return json.dumps(result)
    
    except Exception as e:
        result = {
            "finalResponse": "FAILED",
            "error": f"Failed to list documents: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
        return json.dumps(result)

if __name__ == "__main__":
    # Initialize and run the server
    print(f"Starting Regulatory Documents MCP Server on port {REGULATORY_DOCS_MCP_PORT}")
    mcp.run(transport='sse')