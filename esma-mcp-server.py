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
import logging

from mcp.server.fastmcp import FastMCP

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ESMA_MCP_PORT = os.getenv("ESMA_MCP_PORT", "8001")

# Create ESMA MCP server
mcp = FastMCP("esma-regulatory-docs", port=int(ESMA_MCP_PORT))

class ESMADocumentAgent:
    def __init__(self):
        self.base_folder = 'regulatory_docs/esma'
        self.create_directories()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # ESMA specific URLs based on the provided links
        self.esma_sections = {
            'investors_and_issuers': 'https://www.esma.europa.eu/esmas-activities/investors-and-issuers',
            'markets_and_infrastructure': 'https://www.esma.europa.eu/esmas-activities/markets-and-infrastructure',
            'sustainable_finance': 'https://www.esma.europa.eu/esmas-activities/sustainable-finance',
            'digital_finance': 'https://www.esma.europa.eu/esmas-activities/digital-finance-and-innovation',
            'supervision_convergence': 'https://www.esma.europa.eu/esmas-activities/supervision-and-convergence',
            'publications': 'https://www.esma.europa.eu/publications-and-data',
            'guidelines_recommendations': 'https://www.esma.europa.eu/publications-and-data/guidelines-recommendations-and-technical-standards'
        }
        
        # Document type mappings
        self.document_categories = {
            'MiFID II': ['investment-services-and-crowdfunding', 'trading'],
            'MiFIR': ['trading', 'consolidated-tape-providers'],
            'Prospectus Regulation': ['issuer-disclosure'],
            'Market Abuse Regulation': ['market-integrity'],
            'MiCA': ['markets-crypto-assets-regulation-mica'],
            'DORA': ['digital-operational-resilience-act-dora'],
            'Benchmark Regulation': ['benchmark-administrators'],
            'Fund Management': ['fund-management'],
            'Credit Rating Agencies': ['credit-rating-agencies'],
            'Central Counterparties': ['central-counterparties'],
            'Short Selling': ['short-selling'],
            'Securitisation': ['securitisation']
        }
    
    def create_directories(self):
        """Create necessary directories for ESMA document storage"""
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)
        # Create subdirectories
        for subfolder in ['raw', 'processed', 'summaries', 'comparisons', 'guidelines', 'technical_standards']:
            Path(f"{self.base_folder}/{subfolder}").mkdir(parents=True, exist_ok=True)
    
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
    
    def fetch_esma_documents(self, document_types: List[str] = None, download_files: bool = True, include_news: bool = False) -> Dict:
        """Fetch ESMA regulatory documents from specific sections"""
        if document_types is None:
            document_types = ['MiFID II', 'MiFIR', 'MiCA', 'DORA', 'Fund Management']
        
        try:
            results = {}
            downloaded_files = []
            
            for doc_type in document_types:
                logger.info(f"Fetching ESMA documents for: {doc_type}")
                doc_result = self._fetch_documents_by_category(doc_type, download_files)
                results[doc_type] = doc_result
                if download_files and 'documents' in doc_result:
                    downloaded_files.extend(doc_result['documents'])
            
            # Optionally fetch recent news/publications
            if include_news:
                news_result = self._fetch_recent_publications(download_files)
                results['recent_publications'] = news_result
                if download_files and 'documents' in news_result:
                    downloaded_files.extend(news_result['documents'])
            
            return {
                "finalResponse": "SUCCESS",
                "source": "ESMA",
                "documents_fetched": results,
                "storage_location": self.base_folder,
                "downloaded_files": downloaded_files,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error fetching ESMA documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"ESMA document fetch failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _fetch_documents_by_category(self, doc_type: str, download_files: bool = True) -> Dict:
        """Fetch documents for a specific category using ESMA's structure"""
        try:
            documents = []
            
            # Get category URLs for this document type
            categories = self.document_categories.get(doc_type, [])
            
            for category in categories:
                # Build URL based on ESMA structure
                category_url = f"https://www.esma.europa.eu/esmas-activities/markets-and-infrastructure/{category}"
                if doc_type in ['Fund Management', 'Credit Rating Agencies', 'Benchmark Regulation']:
                    category_url = f"https://www.esma.europa.eu/esmas-activities/investors-and-issuers/{category}"
                elif doc_type in ['MiCA', 'DORA']:
                    category_url = f"https://www.esma.europa.eu/esmas-activities/digital-finance-and-innovation/{category}"
                
                logger.info(f"Fetching from: {category_url}")
                category_docs = self._scrape_esma_page(category_url, doc_type, download_files)
                documents.extend(category_docs)
            
            # Also check guidelines and technical standards
            guidelines_docs = self._fetch_guidelines_and_standards(doc_type, download_files)
            documents.extend(guidelines_docs)
            
            return {
                "documents": documents,
                "count": len(documents),
                "categories_searched": categories
            }
        
        except Exception as e:
            logger.error(f"Error fetching {doc_type} documents: {str(e)}")
            return {
                "documents": [],
                "count": 0,
                "error": str(e)
            }
    
    def _scrape_esma_page(self, url: str, doc_type: str, download_files: bool = True) -> List[Dict]:
        """Scrape an ESMA page for documents"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            documents = []
            
            # Look for document links
            document_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx']
            
            # Find all links
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                # Check if it's a document link
                if any(ext in href.lower() for ext in document_extensions):
                    full_url = urljoin(url, href)
                    title = self._extract_link_title(link)
                    
                    doc_info = {
                        "title": title,
                        "url": full_url,
                        "doc_type": doc_type,
                        "source": "esma",
                        "page_url": url
                    }
                    
                    # Download document if requested
                    if download_files:
                        downloaded_info = self._download_document(full_url, title, doc_type)
                        if downloaded_info:
                            doc_info.update(downloaded_info)
                            documents.append(doc_info)
                    else:
                        documents.append(doc_info)
            
            # Also look for embedded document viewers or special document sections
            document_sections = soup.find_all(['div', 'section'], class_=re.compile(r'document|publication|download', re.I))
            for section in document_sections:
                section_docs = self._extract_documents_from_section(section, url, doc_type, download_files)
                documents.extend(section_docs)
            
            logger.info(f"Found {len(documents)} documents on {url}")
            return documents
        
        except Exception as e:
            logger.error(f"Error scraping ESMA page {url}: {str(e)}")
            return []
    
    def _extract_link_title(self, link) -> str:
        """Extract a meaningful title from a link"""
        # Try text content first
        title = link.get_text(strip=True)
        if title and len(title) > 3:
            return title
        
        # Try title attribute
        if link.get('title'):
            return link['title']
        
        # Try href filename
        href = link.get('href', '')
        if href:
            filename = os.path.basename(href)
            if filename:
                return os.path.splitext(filename)[0]
        
        return "ESMA_document"
    
    def _extract_documents_from_section(self, section, base_url: str, doc_type: str, download_files: bool) -> List[Dict]:
        """Extract documents from a specific section of the page"""
        documents = []
        document_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx']
        
        # Look for links within this section
        for link in section.find_all('a', href=True):
            href = link['href']
            if any(ext in href.lower() for ext in document_extensions):
                full_url = urljoin(base_url, href)
                title = self._extract_link_title(link)
                
                doc_info = {
                    "title": title,
                    "url": full_url,
                    "doc_type": doc_type,
                    "source": "esma",
                    "page_url": base_url,
                    "section": "embedded"
                }
                
                if download_files:
                    downloaded_info = self._download_document(full_url, title, doc_type)
                    if downloaded_info:
                        doc_info.update(downloaded_info)
                        documents.append(doc_info)
                else:
                    documents.append(doc_info)
        
        return documents
    
    def _fetch_guidelines_and_standards(self, doc_type: str, download_files: bool = True) -> List[Dict]:
        """Fetch guidelines and technical standards for a document type"""
        try:
            documents = []
            
            # Guidelines and recommendations page
            guidelines_url = "https://www.esma.europa.eu/publications-and-data/guidelines-recommendations-and-technical-standards"
            
            response = self.session.get(guidelines_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for content related to our document type
            for element in soup.find_all(text=re.compile(doc_type, re.I)):
                parent = element.parent
                while parent and parent.name not in ['div', 'section', 'article']:
                    parent = parent.parent
                
                if parent:
                    # Look for document links in this parent section
                    section_docs = self._extract_documents_from_section(parent, guidelines_url, f"{doc_type}_guidelines", download_files)
                    documents.extend(section_docs)
            
            return documents
        
        except Exception as e:
            logger.error(f"Error fetching guidelines for {doc_type}: {str(e)}")
            return []
    
    def _fetch_recent_publications(self, download_files: bool = True) -> Dict:
        """Fetch recent ESMA publications and news"""
        try:
            documents = []
            
            # Recent news and publications
            news_url = "https://www.esma.europa.eu/press-news/esma-news"
            
            response = self.session.get(news_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for recent news items with document links
            news_items = soup.find_all(['article', 'div'], class_=re.compile(r'news|publication|press', re.I))
            
            for item in news_items[:10]:  # Limit to recent 10 items
                item_docs = self._extract_documents_from_section(item, news_url, "recent_publication", download_files)
                documents.extend(item_docs)
            
            return {
                "documents": documents,
                "count": len(documents),
                "source_url": news_url
            }
        
        except Exception as e:
            logger.error(f"Error fetching recent publications: {str(e)}")
            return {
                "documents": [],
                "count": 0,
                "error": str(e)
            }
    
    def _download_document(self, url: str, title: str, doc_type: str) -> Optional[Dict]:
        """Download and save ESMA document"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Create filename
            sanitized_title = self.sanitize_filename(title)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Get file extension from URL or content type
            parsed_url = urlparse(url)
            ext = os.path.splitext(parsed_url.path)[1]
            
            if not ext:
                content_type = response.headers.get('content-type', '').lower()
                if 'pdf' in content_type:
                    ext = '.pdf'
                elif 'word' in content_type or 'msword' in content_type:
                    ext = '.doc'
                elif 'excel' in content_type or 'spreadsheet' in content_type:
                    ext = '.xls'
                else:
                    ext = '.pdf'  # Default
            
            filename = f"esma_{doc_type}_{sanitized_title}_{timestamp}{ext}"
            
            content = response.content
            
            # Determine subfolder based on document type
            subfolder = 'raw'
            if 'guideline' in doc_type.lower():
                subfolder = 'guidelines'
            elif 'technical' in doc_type.lower() or 'standard' in doc_type.lower():
                subfolder = 'technical_standards'
            
            # Save file
            file_path = os.path.join(self.base_folder, subfolder, filename)
            
            # Check for duplicates
            file_hash = self.get_file_hash(content)
            
            with open(file_path, 'wb') as f:
                f.write(content)
            
            logger.info(f"Downloaded ESMA document: {filename}")
            
            return {
                "filename": filename,
                "file_path": file_path,
                "file_hash": file_hash,
                "size_bytes": len(content),
                "download_timestamp": datetime.now().isoformat(),
                "subfolder": subfolder
            }
        
        except Exception as e:
            logger.error(f"Error downloading ESMA document from {url}: {str(e)}")
            return None
    
    def search_esma_documents(self, query: str, download_files: bool = False) -> Dict:
        """Search ESMA website for specific documents"""
        try:
            # Use ESMA's search functionality
            search_url = f"https://www.esma.europa.eu/search/site/{query}"
            
            response = self.session.get(search_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            documents = []
            
            # Parse search results
            search_results = soup.find_all(['div', 'article'], class_=re.compile(r'search-result|result', re.I))
            
            for result in search_results[:20]:  # Limit results
                result_docs = self._extract_documents_from_section(result, search_url, f"search_{query}", download_files)
                documents.extend(result_docs)
            
            return {
                "finalResponse": "SUCCESS",
                "query": query,
                "documents": documents,
                "count": len(documents),
                "search_url": search_url,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error searching ESMA documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"Search failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def list_esma_documents(self) -> Dict:
        """List all locally stored ESMA documents"""
        try:
            documents = {}
            total_files = 0
            
            for folder in ['raw', 'processed', 'summaries', 'comparisons', 'guidelines', 'technical_standards']:
                folder_path = os.path.join(self.base_folder, folder)
                if os.path.exists(folder_path):
                    files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
                    documents[folder] = {
                        "files": files,
                        "count": len(files)
                    }
                    total_files += len(files)
                else:
                    documents[folder] = {
                        "files": [],
                        "count": 0
                    }
            
            return {
                "finalResponse": "SUCCESS",
                "source": "ESMA",
                "documents": documents,
                "total_files": total_files,
                "storage_location": self.base_folder,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error listing ESMA documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"Failed to list ESMA documents: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

# Initialize the ESMA agent
esma_agent = ESMADocumentAgent()

@mcp.tool()
def fetch_esma_documents(document_types: List[str] = None, download_files: bool = True, include_news: bool = False):
    """Fetch ESMA regulatory documents from specific categories
    
    Args:
        document_types: List of document types to fetch (e.g., ['MiFID II', 'MiFIR', 'MiCA', 'DORA'])
        download_files: Whether to download files locally or just return metadata
        include_news: Whether to include recent news and publications
    """
    return json.dumps(esma_agent.fetch_esma_documents(document_types, download_files, include_news))

@mcp.tool()
def search_esma_documents(query: str, download_files: bool = False):
    """Search ESMA website for specific documents
    
    Args:
        query: Search query (e.g., "MiFID transparency", "crypto assets")
        download_files: Whether to download found documents
    """
    return json.dumps(esma_agent.search_esma_documents(query, download_files))

@mcp.tool()
def list_esma_documents():
    """List all locally stored ESMA documents with counts by category"""
    return json.dumps(esma_agent.list_esma_documents())

@mcp.tool()
def get_esma_sections():
    """Get available ESMA website sections and document categories"""
    return json.dumps({
        "esma_sections": esma_agent.esma_sections,
        "document_categories": esma_agent.document_categories,
        "available_document_types": list(esma_agent.document_categories.keys())
    })

if __name__ == "__main__":
    print(f"Starting ESMA MCP Server on port {ESMA_MCP_PORT}")
    mcp.run(transport='sse')