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

CSRC_MCP_PORT = os.getenv("CSRC_MCP_PORT", "8002")

# Create CSRC MCP server
mcp = FastMCP("csrc-regulatory-docs", port=int(CSRC_MCP_PORT))

class CSRCDocumentAgent:
    def __init__(self):
        self.base_folder = 'regulatory_docs/csrc'

        
        # CSRC main and regional URLs
        self.csrc_urls = {
            'main': 'http://www.csrc.gov.cn/',
            'shandong': 'http://www.csrc.gov.cn/shandong/',
            'dalian': 'http://www.csrc.gov.cn/dalian/',
            'liaoning': 'http://www.csrc.gov.cn/liaoning/',
            'ningxia': 'http://www.csrc.gov.cn/ningxia/',
            'hubei': 'http://www.csrc.gov.cn/hubei/',
            'zhejiang': 'http://www.csrc.gov.cn/zhejiang/',
            'shenzhen': 'http://www.csrc.gov.cn/shenzhen/',
            'heilongjiang': 'http://www.csrc.gov.cn/heilongjiang/',
            'guangdong': 'http://www.csrc.gov.cn/guangdong/',
            'wza': 'http://www.csrc.gov.cn/wza/',
            'shanghai': 'http://www.csrc.gov.cn/shanghai/',
            'henan': 'http://www.csrc.gov.cn/henan/',
            'anhui': 'http://www.csrc.gov.cn/anhui/',
            'xiamen': 'http://www.csrc.gov.cn/xiamen/',
            'hebei': 'http://www.csrc.gov.cn/hebei/',
            'shanxi': 'http://www.csrc.gov.cn/shanxi/',
            'yunnan': 'http://www.csrc.gov.cn/yunnan/',
            'beijing': 'http://www.csrc.gov.cn/beijing/',
            'qinghai': 'http://www.csrc.gov.cn/qinghai/'
        }
        
        # CSRC document categories and their common URL patterns
        self.document_categories = {
            'Securities Law': {
                'keywords': ['证券法', '证券', 'securities', 'law', '法律', '法规'],
                'paths': ['/pub/newsite/flb/flfg/', '/flfg/', '/law/', '/securities/'],
                'priority_regions': ['main', 'shanghai', 'shenzhen']
            },
            'Market Regulation': {
                'keywords': ['市场监管', '监管', 'regulation', 'market', '规定', '办法'],
                'paths': ['/pub/newsite/zjhjs/', '/regulation/', '/market/', '/supervision/'],
                'priority_regions': ['main', 'shanghai', 'shenzhen', 'beijing']
            },
            'Disclosure Rules': {
                'keywords': ['信息披露', '披露', 'disclosure', 'information', '公告', '报告'],
                'paths': ['/pub/newsite/xxpl/', '/disclosure/', '/info/', '/announcement/'],
                'priority_regions': ['main', 'shanghai', 'shenzhen']
            },
            'Listed Company Rules': {
                'keywords': ['上市公司', 'listed company', '公司治理', 'corporate governance'],
                'paths': ['/pub/newsite/ssgsjg/', '/listed/', '/company/', '/corporate/'],
                'priority_regions': ['main', 'shanghai', 'shenzhen']
            },
            'Fund Management': {
                'keywords': ['基金', 'fund', '资产管理', 'asset management', '私募'],
                'paths': ['/pub/newsite/jjjg/', '/fund/', '/asset/', '/investment/'],
                'priority_regions': ['main', 'shanghai', 'shenzhen', 'beijing']
            },
            'Futures Regulation': {
                'keywords': ['期货', 'futures', '衍生品', 'derivatives'],
                'paths': ['/pub/newsite/qhjg/', '/futures/', '/derivatives/'],
                'priority_regions': ['main', 'dalian', 'shanghai', 'shenzhen']
            },
            'Bond Market': {
                'keywords': ['债券', 'bond', '公司债', 'corporate bond'],
                'paths': ['/pub/newsite/zqsc/', '/bond/', '/debt/'],
                'priority_regions': ['main', 'shanghai', 'shenzhen']
            },
            'IPO Rules': {
                'keywords': ['首次公开发行', 'IPO', '发行', 'issuance', '上市'],
                'paths': ['/pub/newsite/fxb/', '/ipo/', '/issuance/', '/listing/'],
                'priority_regions': ['main', 'shanghai', 'shenzhen']
            }
        }
        self.create_directories()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        # Common CSRC page patterns for document discovery
        self.common_paths = [
            '/pub/newsite/',
            '/xxgk/',  # Information disclosure
            '/flfg/',  # Laws and regulations
            '/gzdt/',  # Work updates
            '/zcfb/',  # Policy releases
            '/tjsj/',  # Statistical data
            '/English/' # English content
        ]
    
    def create_directories(self):
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)
        # Create subdirectories matching ESMA structure
        for subfolder in ['raw', 'processed', 'summaries', 'comparisons', 'guidelines', 'technical_standards', 'regional']:
            Path(f"{self.base_folder}/{subfolder}").mkdir(parents=True, exist_ok=True)
        
        # Create regional subdirectories
        for region in self.csrc_urls.keys():
            Path(f"{self.base_folder}/regional/{region}").mkdir(parents=True, exist_ok=True)
    
    def get_file_hash(self, content):
        return hashlib.md5(content.encode() if isinstance(content, str) else content).hexdigest()
    
    def sanitize_filename(self, filename):
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Handle Chinese characters properly
        filename = re.sub(r'[^\w\s\-_\u4e00-\u9fff.]', '_', filename)
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        return filename
    
    def fetch_csrc_documents(self, document_types: List[str] = None, regions: List[str] = None, 
                           download_files: bool = True, include_regional: bool = True) -> Dict:
        if document_types is None:
            document_types = ['Securities Law', 'Market Regulation', 'Disclosure Rules', 'Listed Company Rules']
        
        if regions is None:
            regions = ['main', 'shanghai', 'shenzhen', 'beijing']
        
        try:
            results = {}
            downloaded_files = []
            
            for doc_type in document_types:
                logger.info(f"Fetching CSRC documents for: {doc_type}")
                doc_result = self._fetch_documents_by_category(doc_type, regions, download_files)
                results[doc_type] = doc_result
                if download_files and 'documents' in doc_result:
                    downloaded_files.extend(doc_result['documents'])
            
            # Fetch recent announcements if requested
            if include_regional:
                regional_result = self._fetch_regional_content(regions, download_files)
                results['regional_content'] = regional_result
                if download_files and 'documents' in regional_result:
                    downloaded_files.extend(regional_result['documents'])
            
            return {
                "finalResponse": "SUCCESS",
                "source": "CSRC",
                "documents_fetched": results,
                "storage_location": self.base_folder,
                "downloaded_files": downloaded_files,
                "regions_searched": regions,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error fetching CSRC documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"CSRC document fetch failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _fetch_documents_by_category(self, doc_type: str, regions: List[str], download_files: bool = True) -> Dict:
        try:
            documents = []
            category_info = self.document_categories.get(doc_type, {})
            
            # Use priority regions if available, otherwise use provided regions
            priority_regions = category_info.get('priority_regions', regions)
            search_regions = [r for r in priority_regions if r in regions] or regions
            
            for region in search_regions:
                if region not in self.csrc_urls:
                    continue
                
                base_url = self.csrc_urls[region]
                logger.info(f"Searching {region} for {doc_type} documents")
                
                # Search in category-specific paths
                for path in category_info.get('paths', []):
                    search_url = urljoin(base_url, path)
                    region_docs = self._scrape_csrc_page(search_url, doc_type, region, download_files)
                    documents.extend(region_docs)
                
                # Also search main pages and common paths
                for common_path in self.common_paths[:3]:  # Limit to avoid too many requests
                    search_url = urljoin(base_url, common_path)
                    region_docs = self._scrape_csrc_page_filtered(search_url, doc_type, region, download_files)
                    documents.extend(region_docs)
            
            return {
                "documents": documents,
                "count": len(documents),
                "regions_searched": search_regions,
                "category": doc_type
            }
        
        except Exception as e:
            logger.error(f"Error fetching {doc_type} documents: {str(e)}")
            return {
                "documents": [],
                "count": 0,
                "error": str(e)
            }
    
    def _scrape_csrc_page(self, url: str, doc_type: str, region: str, download_files: bool = True) -> List[Dict]:
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code == 404:
                return []
            
            response.raise_for_status()
            response.encoding = 'utf-8'  # Handle Chinese encoding
            
            soup = BeautifulSoup(response.content, 'html.parser')
            documents = []
            
            # Look for document links with various extensions
            document_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.html', '.htm']
            
            # Find all links
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                # Check if it's a document link or relevant page
                is_document = any(ext in href.lower() for ext in document_extensions)
                
                if is_document or self._is_relevant_link(link, doc_type):
                    full_url = urljoin(url, href)
                    title = self._extract_link_title(link, doc_type)
                    
                    if title and len(title.strip()) > 2:  # Valid title
                        doc_info = {
                            "title": title,
                            "url": full_url,
                            "doc_type": doc_type,
                            "region": region,
                            "source": "csrc",
                            "page_url": url,
                            "is_document_file": is_document
                        }
                        
                        # Download document if requested
                        if download_files:
                            downloaded_info = self._download_document(full_url, title, doc_type, region, is_document)
                            if downloaded_info:
                                doc_info.update(downloaded_info)
                                documents.append(doc_info)
                        else:
                            documents.append(doc_info)
            
            logger.info(f"Found {len(documents)} documents on {url}")
            return documents
        
        except Exception as e:
            logger.error(f"Error scraping CSRC page {url}: {str(e)}")
            return []
    
    def _scrape_csrc_page_filtered(self, url: str, doc_type: str, region: str, download_files: bool = True) -> List[Dict]:
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code == 404:
                return []
            
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.content, 'html.parser')
            documents = []
            
            # Get keywords for this document type
            keywords = self.document_categories.get(doc_type, {}).get('keywords', [])
            
            # Look for content that matches our keywords
            for link in soup.find_all('a', href=True):
                link_text = link.get_text(strip=True).lower()
                href = link['href']
                
                # Check if link text contains relevant keywords
                if any(keyword.lower() in link_text for keyword in keywords):
                    full_url = urljoin(url, href)
                    title = self._extract_link_title(link, doc_type)
                    
                    if title and len(title.strip()) > 2:
                        is_document = any(ext in href.lower() for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx'])
                        
                        doc_info = {
                            "title": title,
                            "url": full_url,
                            "doc_type": doc_type,
                            "region": region,
                            "source": "csrc",
                            "page_url": url,
                            "is_document_file": is_document,
                            "matched_keywords": [kw for kw in keywords if kw.lower() in link_text]
                        }
                        
                        if download_files:
                            downloaded_info = self._download_document(full_url, title, doc_type, region, is_document)
                            if downloaded_info:
                                doc_info.update(downloaded_info)
                                documents.append(doc_info)
                        else:
                            documents.append(doc_info)
            
            return documents[:10]  # Limit results to avoid too many matches
        
        except Exception as e:
            logger.error(f"Error scraping filtered CSRC page {url}: {str(e)}")
            return []
    
    def _is_relevant_link(self, link, doc_type: str) -> bool:
        link_text = link.get_text(strip=True).lower()
        href = link.get('href', '').lower()
        
        keywords = self.document_categories.get(doc_type, {}).get('keywords', [])
        
        # Check if link text or href contains relevant keywords
        for keyword in keywords:
            if keyword.lower() in link_text or keyword.lower() in href:
                return True
        
        return False
    
    def _extract_link_title(self, link, doc_type: str) -> str:
        # Try text content first
        title = link.get_text(strip=True)
        if title and len(title) > 3:
            # Clean up common prefixes/suffixes
            title = re.sub(r'^(更多|详细|查看|点击)', '', title)
            title = re.sub(r'(更多|>>|»)$', '', title)
            return title.strip()
        
        # Try title attribute
        if link.get('title'):
            return link['title'].strip()
        
        # Try href filename
        href = link.get('href', '')
        if href:
            filename = os.path.basename(href)
            if filename and '.' in filename:
                return os.path.splitext(filename)[0]
        
        return f"CSRC_{doc_type}_document"
    
    def _fetch_regional_content(self, regions: List[str], download_files: bool = True) -> Dict:
        try:
            documents = []
            
            for region in regions[:5]:  # Limit to avoid too many requests
                if region not in self.csrc_urls:
                    continue
                
                base_url = self.csrc_urls[region]
                
                # Look for recent announcements/news
                news_paths = ['/gzdt/', '/zcfb/', '/xxgk/']
                
                for path in news_paths:
                    news_url = urljoin(base_url, path)
                    try:
                        response = self.session.get(news_url, timeout=20)
                        if response.status_code == 200:
                            response.encoding = 'utf-8'
                            soup = BeautifulSoup(response.content, 'html.parser')
                            
                            # Look for recent items (usually in lists or with dates)
                            recent_items = soup.find_all(['li', 'div', 'tr'], limit=10)
                            
                            for item in recent_items:
                                item_link = item.find('a', href=True)
                                if item_link:
                                    title = self._extract_link_title(item_link, 'regional_content')
                                    if title and len(title.strip()) > 5:
                                        full_url = urljoin(news_url, item_link['href'])
                                        
                                        doc_info = {
                                            "title": title,
                                            "url": full_url,
                                            "doc_type": "regional_content",
                                            "region": region,
                                            "source": "csrc",
                                            "page_url": news_url,
                                            "content_type": path.strip('/')
                                        }
                                        
                                        if download_files:
                                            downloaded_info = self._download_document(full_url, title, 'regional', region, False)
                                            if downloaded_info:
                                                doc_info.update(downloaded_info)
                                                documents.append(doc_info)
                                        else:
                                            documents.append(doc_info)
                    except Exception as e:
                        logger.warning(f"Could not fetch {news_url}: {str(e)}")
                        continue
            
            return {
                "documents": documents,
                "count": len(documents),
                "regions_searched": regions
            }
        
        except Exception as e:
            logger.error(f"Error fetching regional content: {str(e)}")
            return {
                "documents": [],
                "count": 0,
                "error": str(e)
            }
    
    def _download_document(self, url: str, title: str, doc_type: str, region: str, is_file: bool = True) -> Optional[Dict]:
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Create filename
            sanitized_title = self.sanitize_filename(title)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if is_file:
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
                
                filename = f"csrc_{region}_{doc_type}_{sanitized_title}_{timestamp}{ext}"
                content = response.content
            else:
                # HTML content
                filename = f"csrc_{region}_{doc_type}_{sanitized_title}_{timestamp}.html"
                response.encoding = 'utf-8'
                content = response.text
            
            # Determine subfolder
            subfolder = 'raw'
            if doc_type == 'regional':
                subfolder = f'regional/{region}'
            elif 'guideline' in doc_type.lower() or 'guide' in doc_type.lower():
                subfolder = 'guidelines'
            
            # Save file
            file_path = os.path.join(self.base_folder, subfolder, filename)
            
            # Check for duplicates
            file_hash = self.get_file_hash(content if isinstance(content, str) else content)
            
            # Save appropriately based on content type
            if is_file and isinstance(content, bytes):
                with open(file_path, 'wb') as f:
                    f.write(content)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content if isinstance(content, str) else content.decode('utf-8'))
            
            logger.info(f"Downloaded CSRC document: {filename}")
            
            return {
                "filename": filename,
                "file_path": file_path,
                "file_hash": file_hash,
                "size_bytes": len(content) if isinstance(content, bytes) else len(content.encode('utf-8')),
                "download_timestamp": datetime.now().isoformat(),
                "subfolder": subfolder,
                "region": region
            }
        
        except Exception as e:
            logger.error(f"Error downloading CSRC document from {url}: {str(e)}")
            return None
    
    def search_csrc_documents(self, query: str, regions: List[str] = None, download_files: bool = False) -> Dict:
        if regions is None:
            regions = ['main', 'shanghai', 'shenzhen']
        
        try:
            documents = []
            
            for region in regions:
                if region not in self.csrc_urls:
                    continue
                
                base_url = self.csrc_urls[region]
                
                # Try different search approaches since CSRC might not have unified search
                search_approaches = [
                    f"{base_url}?q={query}",  # Query parameter
                    f"{base_url}search/?keyword={query}",  # Common search pattern
                    f"{base_url}s?wd={query}"  # Another common pattern
                ]
                
                for search_url in search_approaches:
                    try:
                        response = self.session.get(search_url, timeout=20)
                        if response.status_code == 200:
                            response.encoding = 'utf-8'
                            soup = BeautifulSoup(response.content, 'html.parser')
                            
                            # Look for search results or content with query terms
                            search_results = self._extract_search_results(soup, query, search_url, region, download_files)
                            documents.extend(search_results)
                            break  # If one search method works, don't try others
                    except Exception as e:
                        continue  # Try next search approach
            
            return {
                "finalResponse": "SUCCESS",
                "query": query,
                "documents": documents,
                "count": len(documents),
                "regions_searched": regions,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error searching CSRC documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"Search failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _extract_search_results(self, soup, query: str, search_url: str, region: str, download_files: bool) -> List[Dict]:
        documents = []
        query_lower = query.lower()
        
        # Look for content that contains the search query
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            link_text = link.get_text(strip=True)
            if query_lower in link_text.lower() and len(link_text) > 5:
                full_url = urljoin(search_url, link['href'])
                
                doc_info = {
                    "title": link_text,
                    "url": full_url,
                    "doc_type": f"search_{query}",
                    "region": region,
                    "source": "csrc",
                    "page_url": search_url,
                    "relevance_score": self._calculate_relevance(link_text, query)
                }
                
                if download_files:
                    is_file = any(ext in link['href'].lower() for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx'])
                    downloaded_info = self._download_document(full_url, link_text, f"search_{query}", region, is_file)
                    if downloaded_info:
                        doc_info.update(downloaded_info)
                        documents.append(doc_info)
                else:
                    documents.append(doc_info)
        
        # Sort by relevance and return top results
        documents.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return documents[:20]  # Limit results
    
    def _calculate_relevance(self, text: str, query: str) -> float:
        text_lower = text.lower()
        query_lower = query.lower()
        
        # Count occurrences and position bonus for early matches
        score = text_lower.count(query_lower)
        if text_lower.startswith(query_lower):
            score += 2
        if query_lower in text_lower[:len(text_lower)//3]:
            score += 1
        
        return score
    
    def list_csrc_documents(self) -> Dict:
        try:
            documents = {}
            total_files = 0
            
            # Main folders
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
            
            # Regional folders
            regional_path = os.path.join(self.base_folder, 'regional')
            if os.path.exists(regional_path):
                regional_docs = {}
                for region in os.listdir(regional_path):
                    region_path = os.path.join(regional_path, region)
                    if os.path.isdir(region_path):
                        files = [f for f in os.listdir(region_path) if os.path.isfile(os.path.join(region_path, f))]
                        regional_docs[region] = {
                            "files": files,
                            "count": len(files)
                        }
                        total_files += len(files)
                documents['regional'] = regional_docs
            
            return {
                "finalResponse": "SUCCESS",
                "source": "CSRC",
                "documents": documents,
                "total_files": total_files,
                "storage_location": self.base_folder,
                "available_regions": list(self.csrc_urls.keys()),
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error listing CSRC documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"Failed to list CSRC documents: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

# Initialize the CSRC agent
csrc_agent = CSRCDocumentAgent()

@mcp.tool()
def fetch_csrc_documents(document_types: List[str] = None, regions: List[str] = None, 
                        download_files: bool = True, include_regional: bool = True):
    
    return json.dumps(csrc_agent.fetch_csrc_documents(document_types, regions, download_files, include_regional))

@mcp.tool()
def search_csrc_documents(query: str, regions: List[str] = None, download_files: bool = False):
   
    return json.dumps(csrc_agent.search_csrc_documents(query, regions, download_files))

@mcp.tool()
def list_csrc_documents():
    return json.dumps(csrc_agent.list_csrc_documents())

@mcp.tool()
def get_csrc_document_categories():
    return json.dumps({
        "finalResponse": "SUCCESS",
        "document_categories": list(csrc_agent.document_categories.keys()),
        "available_regions": list(csrc_agent.csrc_urls.keys()),
        "category_details": {
            category: {
                "keywords": info["keywords"],
                "priority_regions": info["priority_regions"],
                "description": f"Documents related to {category}"
            }
            for category, info in csrc_agent.document_categories.items()
        },
        "region_urls": csrc_agent.csrc_urls,
        "timestamp": datetime.now().isoformat()
    })

@mcp.tool()
def analyze_csrc_document(file_path: str):
    
    try:
        if not os.path.exists(file_path):
            return json.dumps({
                "finalResponse": "FAILED",
                "error": "File not found",
                "timestamp": datetime.now().isoformat()
            })
        
        # Basic file info
        file_size = os.path.getsize(file_path)
        file_ext = os.path.splitext(file_path)[1].lower()
        
        analysis = {
            "file_path": file_path,
            "file_size": file_size,
            "file_extension": file_ext,
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        # Text extraction based on file type
        if file_ext == '.pdf':
            try:
                with open(file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    text = ""
                    for page in pdf_reader.pages[:5]:  # First 5 pages
                        text += page.extract_text()
                    analysis["text_preview"] = text[:2000]  # First 2000 chars
                    analysis["total_pages"] = len(pdf_reader.pages)
            except Exception as e:
                analysis["pdf_error"] = str(e)
        
        elif file_ext in ['.doc', '.docx']:
            try:
                doc = Document(file_path)
                text = "\n".join([paragraph.text for paragraph in doc.paragraphs[:10]])  # First 10 paragraphs
                analysis["text_preview"] = text[:2000]
                analysis["total_paragraphs"] = len(doc.paragraphs)
            except Exception as e:
                analysis["docx_error"] = str(e)
        
        elif file_ext in ['.html', '.htm']:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    soup = BeautifulSoup(content, 'html.parser')
                    text = soup.get_text()
                    analysis["text_preview"] = text[:2000]
                    analysis["html_title"] = soup.title.string if soup.title else "No title"
            except Exception as e:
                analysis["html_error"] = str(e)
        
        # Basic text analysis if we have text
        if "text_preview" in analysis:
            text = analysis["text_preview"]
            analysis["word_count"] = len(text.split())
            analysis["character_count"] = len(text)
            
            # Look for key regulatory terms
            regulatory_terms = [
                "证券法", "Securities Law", "regulation", "监管", "规定", "办法",
                "披露", "disclosure", "上市公司", "listed company", "基金", "fund",
                "期货", "futures", "债券", "bond", "发行", "issuance"
            ]
            
            found_terms = [term for term in regulatory_terms if term.lower() in text.lower()]
            analysis["regulatory_terms_found"] = found_terms
            analysis["regulatory_score"] = len(found_terms)
        
        return json.dumps({
            "finalResponse": "SUCCESS",
            "analysis": analysis,
            "timestamp": datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error analyzing CSRC document: {str(e)}")
        return json.dumps({
            "finalResponse": "FAILED",
            "error": f"Analysis failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })

@mcp.tool()
def get_csrc_document_stats():
    try:
        stats = {
            "total_documents": 0,
            "documents_by_type": {},
            "documents_by_region": {},
            "documents_by_extension": {},
            "storage_usage": 0,
            "latest_downloads": []
        }
        
        # Scan all directories
        for root, dirs, files in os.walk(csrc_agent.base_folder):
            for file in files:
                if file.startswith('.'):  # Skip hidden files
                    continue
                
                file_path = os.path.join(root, file)
                file_size = os.path.getsize(file_path)
                file_ext = os.path.splitext(file)[1].lower()
                
                stats["total_documents"] += 1
                stats["storage_usage"] += file_size
                
                # Count by extension
                stats["documents_by_extension"][file_ext] = stats["documents_by_extension"].get(file_ext, 0) + 1
                
                # Extract type and region from filename if possible
                if "csrc_" in file:
                    parts = file.split('_')
                    if len(parts) >= 3:
                        region = parts[1]
                        doc_type = parts[2]
                        
                        stats["documents_by_region"][region] = stats["documents_by_region"].get(region, 0) + 1
                        stats["documents_by_type"][doc_type] = stats["documents_by_type"].get(doc_type, 0) + 1
                
                # Track recent files
                file_mtime = os.path.getmtime(file_path)
                stats["latest_downloads"].append({
                    "filename": file,
                    "path": file_path,
                    "size": file_size,
                    "modified": datetime.fromtimestamp(file_mtime).isoformat()
                })
        
        # Sort latest downloads by modification time
        stats["latest_downloads"].sort(key=lambda x: x["modified"], reverse=True)
        stats["latest_downloads"] = stats["latest_downloads"][:10]  # Keep only latest 10
        
        # Convert storage usage to human readable
        stats["storage_usage_mb"] = round(stats["storage_usage"] / (1024 * 1024), 2)
        
        return json.dumps({
            "finalResponse": "SUCCESS",
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error getting CSRC document stats: {str(e)}")
        return json.dumps({
            "finalResponse": "FAILED",
            "error": f"Stats retrieval failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })

@mcp.tool()
def clean_csrc_documents(older_than_days: int = 30, dry_run: bool = True):
    
    
    try:
        import time
        
        cutoff_time = time.time() - (older_than_days * 24 * 60 * 60)
        files_to_delete = []
        total_size_to_free = 0
        
        # Scan for old files
        for root, dirs, files in os.walk(csrc_agent.base_folder):
            for file in files:
                if file.startswith('.'):  # Skip hidden files
                    continue
                
                file_path = os.path.join(root, file)
                file_mtime = os.path.getmtime(file_path)
                
                if file_mtime < cutoff_time:
                    file_size = os.path.getsize(file_path)
                    files_to_delete.append({
                        "path": file_path,
                        "size": file_size,
                        "age_days": int((time.time() - file_mtime) / (24 * 60 * 60))
                    })
                    total_size_to_free += file_size
        
        result = {
            "files_to_delete": len(files_to_delete),
            "total_size_mb": round(total_size_to_free / (1024 * 1024), 2),
            "dry_run": dry_run,
            "files": files_to_delete[:20]  # Show first 20 files
        }
        
        # Actually delete if not dry run
        if not dry_run and files_to_delete:
            deleted_count = 0
            for file_info in files_to_delete:
                try:
                    os.remove(file_info["path"])
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Could not delete {file_info['path']}: {str(e)}")
            
            result["deleted_count"] = deleted_count
        
        return json.dumps({
            "finalResponse": "SUCCESS",
            "cleanup_result": result,
            "timestamp": datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error cleaning CSRC documents: {str(e)}")
        return json.dumps({
            "finalResponse": "FAILED",
            "error": f"Cleanup failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })

# Health check endpoint
@mcp.tool()
def csrc_health_check():
    try:
        health_info = {
            "server_status": "running",
            "storage_accessible": os.path.exists(csrc_agent.base_folder),
            "available_regions": list(csrc_agent.csrc_urls.keys()),
            "document_categories": list(csrc_agent.document_categories.keys()),
            "timestamp": datetime.now().isoformat()
        }
        
        # Test connectivity to main CSRC site
        try:
            response = csrc_agent.session.get(csrc_agent.csrc_urls['main'], timeout=10)
            health_info["csrc_main_accessible"] = response.status_code == 200
            health_info["csrc_response_time"] = response.elapsed.total_seconds()
        except Exception as e:
            health_info["csrc_main_accessible"] = False
            health_info["csrc_error"] = str(e)
        
        # Check storage space
        try:
            import shutil
            total, used, free = shutil.disk_usage(csrc_agent.base_folder)
            health_info["storage_space"] = {
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "free_gb": round(free / (1024**3), 2)
            }
        except Exception as e:
            health_info["storage_error"] = str(e)
        
        return json.dumps({
            "finalResponse": "SUCCESS",
            "health": health_info,
            "timestamp": datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return json.dumps({
            "finalResponse": "FAILED",
            "error": f"Health check failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })

# Server startup
if __name__ == "__main__":
    print(f"Starting CSRC MCP Server on port {CSRC_MCP_PORT}")
    print(f"Storage location: {csrc_agent.base_folder}")
    print(f"Available regions: {', '.join(csrc_agent.csrc_urls.keys())}")
    print(f"Document categories: {', '.join(csrc_agent.document_categories.keys())}")
    
    try:
        mcp.run(transport='sse')
    except KeyboardInterrupt:
        print("\nShutting down CSRC MCP Server...")
    except Exception as e:
        print(f"Server error: {str(e)}")
        sys.exit(1)