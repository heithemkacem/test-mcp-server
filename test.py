#!/usr/bin/env python3

import asyncio
import json
import os
import aiohttp
import aiofiles
from pathlib import Path
from urllib.parse import urljoin, urlparse
import re
from bs4 import BeautifulSoup
from mcp import ClientSession
from mcp.client.sse import sse_client

class DocumentDownloader:
    """Enhanced document downloader for regulatory websites"""
    
    def __init__(self, download_dir="downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.session = None
    
    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_page(self, url):
        """Fetch a web page with error handling"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    print(f"HTTP {response.status} for {url}")
                    return None
        except Exception as e:
            print(f"Error fetching {url}: {str(e)}")
            return None
    
    async def download_file(self, url, filename=None):
        """Download a file and save it locally"""
        try:
            if not filename:
                parsed = urlparse(url)
                filename = os.path.basename(parsed.path) or "document"
            
            # Ensure we have a file extension
            if not os.path.splitext(filename)[1]:
                # Try to determine from URL or default to .pdf
                if '.pdf' in url.lower():
                    filename += '.pdf'
                elif '.doc' in url.lower():
                    filename += '.docx' if 'docx' in url.lower() else '.doc'
                else:
                    filename += '.pdf'
            
            file_path = self.download_dir / filename
            
            # Check if file already exists
            if file_path.exists():
                print(f"File already exists: {file_path}")
                return str(file_path)
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                    print(f"Downloaded: {file_path}")
                    return str(file_path)
                else:
                    print(f"Failed to download {url}: HTTP {response.status}")
                    return None
        except Exception as e:
            print(f"Error downloading {url}: {str(e)}")
            return None
    
    def extract_document_links(self, html, base_url):
        """Extract PDF and Word document links from HTML"""
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(base_url, href)
            
            # Check if it's a document link
            if self.is_document_link(full_url):
                title = link.get_text(strip=True) or link.get('title', '')
                links.append({
                    'url': full_url,
                    'title': title,
                    'type': self.get_document_type(full_url)
                })
        
        return links
    
    def is_document_link(self, url):
        """Check if URL points to a document"""
        doc_extensions = ['.pdf', '.doc', '.docx', '.rtf']
        url_lower = url.lower()
        return any(ext in url_lower for ext in doc_extensions)
    
    def get_document_type(self, url):
        """Determine document type from URL"""
        url_lower = url.lower()
        if '.pdf' in url_lower:
            return 'pdf'
        elif '.docx' in url_lower:
            return 'docx'
        elif '.doc' in url_lower:
            return 'doc'
        elif '.rtf' in url_lower:
            return 'rtf'
        return 'unknown'

class ESMADocumentFetcher:
    """Enhanced ESMA document fetcher"""
    
    BASE_URLS = {
        'mifid': 'https://www.esma.europa.eu/policy-activities/mifid-ii-and-mifir',
        'emir': 'https://www.esma.europa.eu/policy-activities/post-trading/ccps-emir',
        'sftr': 'https://www.esma.europa.eu/policy-activities/post-trading/sftr',
        'general': 'https://www.esma.europa.eu/publications'
    }
    
    async def fetch_documents(self, document_types, downloader):
        """Fetch ESMA documents with enhanced scraping"""
        results = []
        
        for doc_type in document_types:
            print(f"Fetching ESMA {doc_type} documents...")
            
            # Get the appropriate URL
            url_key = doc_type.lower().replace(' ', '').replace('ii', '')
            if 'mifid' in url_key:
                url_key = 'mifid'
            
            base_url = self.BASE_URLS.get(url_key, self.BASE_URLS['general'])
            
            # Fetch the page
            html = await downloader.fetch_page(base_url)
            if not html:
                continue
            
            # Extract document links
            links = downloader.extract_document_links(html, base_url)
            
            # Filter relevant documents
            relevant_links = self.filter_relevant_documents(links, doc_type)
            
            # Download documents
            downloaded_files = []
            for link in relevant_links[:5]:  # Limit to 5 documents per type
                file_path = await downloader.download_file(
                    link['url'], 
                    f"esma_{doc_type}_{link['title'][:50]}.{link['type']}"
                )
                if file_path:
                    downloaded_files.append({
                        'title': link['title'],
                        'url': link['url'],
                        'file_path': file_path,
                        'type': link['type']
                    })
            
            results.append({
                'document_type': doc_type,
                'source': 'esma',
                'documents_found': len(links),
                'documents_downloaded': len(downloaded_files),
                'downloaded_files': downloaded_files
            })
        
        return results
    
    def filter_relevant_documents(self, links, doc_type):
        """Filter documents based on document type"""
        keywords = {
            'MiFID II': ['mifid', 'markets in financial instruments'],
            'EMIR': ['emir', 'european market infrastructure'],
            'SFTR': ['sftr', 'securities financing']
        }
        
        relevant_keywords = keywords.get(doc_type, [doc_type.lower()])
        filtered_links = []
        
        for link in links:
            title_lower = link['title'].lower()
            if any(keyword in title_lower for keyword in relevant_keywords):
                filtered_links.append(link)
        
        return filtered_links

class CSRCDocumentFetcher:
    """Enhanced CSRC document fetcher"""
    
    BASE_URLS = {
        'securities_law': 'http://www.csrc.gov.cn/csrc_en/c101864/common_list.shtml',
        'regulations': 'http://www.csrc.gov.cn/csrc_en/c101861/common_list.shtml',
        'general': 'http://www.csrc.gov.cn/csrc_en/'
    }
    
    async def fetch_documents(self, document_types, downloader):
        """Fetch CSRC documents with enhanced scraping"""
        results = []
        
        for doc_type in document_types:
            print(f"Fetching CSRC {doc_type} documents...")
            
            # Get the appropriate URL
            url_key = doc_type.lower().replace(' ', '_')
            base_url = self.BASE_URLS.get(url_key, self.BASE_URLS['general'])
            
            # Fetch the page
            html = await downloader.fetch_page(base_url)
            if not html:
                continue
            
            # Extract document links
            links = downloader.extract_document_links(html, base_url)
            
            # Filter relevant documents
            relevant_links = self.filter_relevant_documents(links, doc_type)
            
            # Download documents
            downloaded_files = []
            for link in relevant_links[:5]:  # Limit to 5 documents per type
                file_path = await downloader.download_file(
                    link['url'],
                    f"csrc_{doc_type}_{link['title'][:50]}.{link['type']}"
                )
                if file_path:
                    downloaded_files.append({
                        'title': link['title'],
                        'url': link['url'],
                        'file_path': file_path,
                        'type': link['type']
                    })
            
            results.append({
                'document_type': doc_type,
                'source': 'csrc',
                'documents_found': len(links),
                'documents_downloaded': len(downloaded_files),
                'downloaded_files': downloaded_files
            })
        
        return results
    
    def filter_relevant_documents(self, links, doc_type):
        """Filter documents based on document type"""
        keywords = {
            'Securities Law': ['securities', 'law', 'regulation'],
            'Market Regulation': ['market', 'regulation', 'rule'],
            'Disclosure Rules': ['disclosure', 'information', 'reporting']
        }
        
        relevant_keywords = keywords.get(doc_type, [doc_type.lower()])
        filtered_links = []
        
        for link in links:
            title_lower = link['title'].lower()
            if any(keyword in title_lower for keyword in relevant_keywords):
                filtered_links.append(link)
        
        return filtered_links

async def test_enhanced_regulatory_docs_server():
    """Test the enhanced regulatory documents system"""
    print("Testing Enhanced Regulatory Documents System...")
    
    try:
        # Test standalone document fetching first
        async with DocumentDownloader("regulatory_docs") as downloader:
            # Test ESMA fetching
            print("\n=== Testing ESMA Document Fetching ===")
            esma_fetcher = ESMADocumentFetcher()
            esma_results = await esma_fetcher.fetch_documents(["MiFID II"], downloader)
            
            for result in esma_results:
                print(f"\nESMA {result['document_type']} Results:")
                print(f"  Documents found: {result['documents_found']}")
                print(f"  Documents downloaded: {result['documents_downloaded']}")
                for doc in result['downloaded_files']:
                    print(f"    - {doc['title'][:60]}... ({doc['type']})")
                    print(f"      File: {doc['file_path']}")
            
            # Test CSRC fetching
            print("\n=== Testing CSRC Document Fetching ===")
            csrc_fetcher = CSRCDocumentFetcher()
            csrc_results = await csrc_fetcher.fetch_documents(["Securities Law"], downloader)
            
            for result in csrc_results:
                print(f"\nCSRC {result['document_type']} Results:")
                print(f"  Documents found: {result['documents_found']}")
                print(f"  Documents downloaded: {result['documents_downloaded']}")
                for doc in result['downloaded_files']:
                    print(f"    - {doc['title'][:60]}... ({doc['type']})")
                    print(f"      File: {doc['file_path']}")
        
        # Now test with MCP server if available
        print("\n\n=== Testing MCP Server Integration ===")
        try:
            mcp_url = os.getenv("REGULATORY_DOCS_MCP_URL", "http://localhost:8001/sse")
            print(f"Connecting to MCP server: {mcp_url}")
            
            async with sse_client(url=mcp_url) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    
                    # Test enhanced ESMA fetching
                    print("\nTesting enhanced ESMA document fetch...")
                    esma_result = await session.call_tool(
                        "fetch_esma_documents",
                        arguments={"document_types": ["MiFID II"], "download_files": True}
                    )
                    esma_data = json.loads(esma_result.content[0].text)
                    print(f"   ESMA result: {esma_data.get('finalResponse', 'No response')}")
                    
                    if 'downloaded_files' in esma_data:
                        print(f"   Files downloaded: {len(esma_data['downloaded_files'])}")
                        for file_info in esma_data['downloaded_files']:
                            print(f"     - {file_info.get('title', 'Unknown')}")
                    
                    # Test enhanced CSRC fetching
                    print("\nTesting enhanced CSRC document fetch...")
                    csrc_result = await session.call_tool(
                        "fetch_csrc_documents", 
                        arguments={"document_types": ["Securities Law"], "download_files": True}
                    )
                    csrc_data = json.loads(csrc_result.content[0].text)
                    print(f"   CSRC result: {csrc_data.get('finalResponse', 'No response')}")
                    
                    if 'downloaded_files' in csrc_data:
                        print(f"   Files downloaded: {len(csrc_data['downloaded_files'])}")
                        for file_info in csrc_data['downloaded_files']:
                            print(f"     - {file_info.get('title', 'Unknown')}")
        
        except Exception as mcp_error:
            print(f"MCP server not available or error: {str(mcp_error)}")
            print("Continuing with standalone testing...")
        
        print("\n=== All tests completed ===")
        
    except Exception as e:
        print(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

async def interactive_enhanced_test():
    """Interactive test mode with file downloading"""
    print("\nEnhanced Interactive Test Mode")
    print("Available commands:")
    print("1. fetch_esma [doc_types] - Fetch and download ESMA documents")
    print("2. fetch_csrc [doc_types] - Fetch and download CSRC documents") 
    print("3. list_files - List downloaded files")
    print("4. test_url <url> - Test scraping a specific URL")
    print("5. exit")
    
    async with DocumentDownloader("interactive_downloads") as downloader:
        esma_fetcher = ESMADocumentFetcher()
        csrc_fetcher = CSRCDocumentFetcher()
        
        while True:
            command = input("\nEnter command: ").strip().split()
            
            if not command or command[0] == "exit":
                break
            
            try:
                if command[0] == "fetch_esma":
                    doc_types = command[1:] if len(command) > 1 else ["MiFID II"]
                    results = await esma_fetcher.fetch_documents(doc_types, downloader)
                    print(f"Results: {json.dumps(results, indent=2)}")
                
                elif command[0] == "fetch_csrc":
                    doc_types = command[1:] if len(command) > 1 else ["Securities Law"]
                    results = await csrc_fetcher.fetch_documents(doc_types, downloader)
                    print(f"Results: {json.dumps(results, indent=2)}")
                
                elif command[0] == "list_files":
                    files = list(downloader.download_dir.glob("*"))
                    print("Downloaded files:")
                    for file_path in files:
                        print(f"  - {file_path.name} ({file_path.stat().st_size} bytes)")
                
                elif command[0] == "test_url":
                    if len(command) < 2:
                        print("Usage: test_url <url>")
                        continue
                    
                    url = command[1]
                    html = await downloader.fetch_page(url)
                    if html:
                        links = downloader.extract_document_links(html, url)
                        print(f"Found {len(links)} document links:")
                        for link in links[:10]:  # Show first 10
                            print(f"  - {link['title'][:80]}... ({link['type']})")
                            print(f"    URL: {link['url']}")
                    else:
                        print("Failed to fetch URL")
                
                else:
                    print(f"Unknown command: {command[0]}")
            
            except Exception as e:
                print(f"Command failed: {str(e)}")
                import traceback
                traceback.print_exc()

# Run enhanced test
if __name__ == "__main__":
    # Install required packages reminder
    required_packages = ['aiohttp', 'aiofiles', 'beautifulsoup4', 'python-dotenv']
    print("Required packages:", ', '.join(required_packages))
    print("Install with: pip install " + ' '.join(required_packages))
    print()
    
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("python-dotenv not installed, skipping .env file loading")
    
    print("Enhanced Regulatory Documents Test Suite")
    print("=====================================")
    print("Choose test mode:")
    print("1. Enhanced full test suite")
    print("2. Interactive enhanced mode")
    print("3. Original MCP server test")
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == "1":
        asyncio.run(test_enhanced_regulatory_docs_server())
    
    elif choice == "2":
        asyncio.run(interactive_enhanced_test())
    
    elif choice == "3":
        # Run original test from your code
        from test_regulatory_docs_server import test_regulatory_docs_server
        asyncio.run(test_regulatory_docs_server())
    
    else:
        print("Invalid choice")