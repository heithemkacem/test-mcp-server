#!/usr/bin/env python3

import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from pathlib import Path
import logging
from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CSRC_MCP_PORT = os.getenv("CSRC_MCP_PORT", "8002")

# Create an MCP server
mcp = FastMCP("csrc-mcp", port=int(CSRC_MCP_PORT))

class CSRCDocumentAgent:
    def __init__(self):
        self.base_folder = 'regulatory_docs/csrc'
        self.create_directories()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def create_directories(self):
        """Create necessary directories for document storage"""
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)
        for subfolder in ['raw', 'processed']:
            Path(f"{self.base_folder}/{subfolder}").mkdir(parents=True, exist_ok=True)
    
    def fetch_csrc_documents(self, document_types=None):
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
                "storage_location": self.base_folder,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error fetching CSRC documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"CSRC document fetch failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _fetch_csrc_specific_docs(self, base_url: str, doc_type: str):
        """Fetch specific CSRC document type"""
        try:
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
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True)
                
                if any(keyword in text.lower() for keyword in ['securities', '证券', 'law', '法']):
                    full_url = urljoin(base_url, href)
                    title = text or f"{doc_type}_document"
                    
                    doc_info = self._download_document(full_url, title, doc_type)
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
    
    def _download_document(self, url: str, title: str, doc_type: str):
        """Download and save document"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Create filename
            sanitized_title = self._sanitize_filename(title)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Determine content type
            is_html = 'text/html' in response.headers.get('content-type', '').lower()
            
            if is_html:
                filename = f"{sanitized_title}_{timestamp}.html"
                content = response.text
                write_mode = 'w'
                encode_args = {'encoding': 'utf-8'}
            else:
                # Get file extension from URL or default to .pdf
                parsed_url = urlparse(url)
                ext = os.path.splitext(parsed_url.path)[1] or '.pdf'
                filename = f"{sanitized_title}_{timestamp}{ext}"
                content = response.content
                write_mode = 'wb'
                encode_args = {}
            
            # Save to raw folder
            file_path = os.path.join(self.base_folder, 'raw', filename)
            
            with open(file_path, write_mode, **encode_args) as f:
                f.write(content)
            
            logger.info(f"Downloaded: {filename}")
            
            return {
                "title": title,
                "filename": filename,
                "file_path": file_path,
                "url": url,
                "doc_type": doc_type,
                "source": "CSRC",
                "size_bytes": len(content.encode() if is_html else content),
                "download_timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error downloading document from {url}: {str(e)}")
            return None
    
    def _sanitize_filename(self, filename):
        """Sanitize filename for safe storage"""
        # Remove invalid characters
        filename = ''.join(c for c in filename if c.isalnum() or c in ' -_.')
        # Limit length
        return filename[:200] if len(filename) > 200 else filename

    def list_local_documents(self):
        """List all locally stored documents"""
        try:
            docs = {}
            
            for folder in ['raw', 'processed']:
                folder_path = os.path.join(self.base_folder, folder)
                if os.path.exists(folder_path):
                    docs[folder] = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
                else:
                    docs[folder] = []
            
            return {
                "finalResponse": "SUCCESS",
                "documents": docs,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            return {
                "finalResponse": "FAILED",
                "error": f"Failed to list documents: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

# Initialize the agent
csrc_agent = CSRCDocumentAgent()

@mcp.tool()
def fetch_csrc_documents(document_types=None):
    """Fetch CSRC regulatory documents"""
    return json.dumps(csrc_agent.fetch_csrc_documents(document_types))

@mcp.tool()
def list_local_documents():
    """List all locally stored documents"""
    return json.dumps(csrc_agent.list_local_documents())

if __name__ == "__main__":
    # Initialize and run the server
    print(f"Starting CSRC MCP Server on port {CSRC_MCP_PORT}")
    mcp.run(transport='sse')
