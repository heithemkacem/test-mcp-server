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

ANALYSIS_MCP_PORT = os.getenv("ANALYSIS_MCP_PORT", "8003")

# Create Analysis MCP server
mcp = FastMCP("regulatory-analysis", port=int(ANALYSIS_MCP_PORT))

class RegulatoryAnalysisAgent:
    def __init__(self):
        self.base_folders = {
            'esma': 'regulatory_docs/esma',
            'csrc': 'regulatory_docs/csrc'
        }
        self.ensure_directories()
    
    def ensure_directories(self):
        for folder_path in self.base_folders.values():
            Path(folder_path).mkdir(parents=True, exist_ok=True)
            # Create subdirectories
            for subfolder in ['raw', 'processed', 'summaries', 'comparisons']:
                Path(f"{folder_path}/{subfolder}").mkdir(parents=True, exist_ok=True)
    
    def summarize_documents(self, source: str, doc_type: str = None) -> Dict:
        try:
            if source not in self.base_folders:
                return {
                    "finalResponse": "FAILED",
                    "error": f"Unknown source: {source}. Available sources: {list(self.base_folders.keys())}",
                    "timestamp": datetime.now().isoformat()
                }
            
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
            
            files_to_process = []
            for filename in os.listdir(raw_folder):
                if doc_type and doc_type.lower().replace(' ', '_') not in filename.lower():
                    continue
                file_path = os.path.join(raw_folder, filename)
                if os.path.isfile(file_path):
                    files_to_process.append((filename, file_path))
            
            for filename, file_path in files_to_process:
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
                "storage_location": summaries_folder,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error summarizing documents: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"Document summarization failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def compare_documents(self, source1: str, source2: str = None, doc_types: List[str] = None) -> Dict:
        try:
            if source1 not in self.base_folders:
                return {
                    "finalResponse": "FAILED",
                    "error": f"Unknown source1: {source1}. Available sources: {list(self.base_folders.keys())}",
                    "timestamp": datetime.now().isoformat()
                }
            
            if source2 is None:
                source2 = source1
            elif source2 not in self.base_folders:
                return {
                    "finalResponse": "FAILED",
                    "error": f"Unknown source2: {source2}. Available sources: {list(self.base_folders.keys())}",
                    "timestamp": datetime.now().isoformat()
                }
            
            comparison_results = []
            
            # Get summaries from both sources
            summaries1 = self._get_summaries_from_source(source1, doc_types)
            summaries2 = self._get_summaries_from_source(source2, doc_types)
            
            if not summaries1 and not summaries2:
                return {
                    "finalResponse": "FAILED",
                    "error": "No summaries found for comparison. Please generate summaries first.",
                    "timestamp": datetime.now().isoformat()
                }
            
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
                "comparison_path": comparison_path,
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
    
    def _extract_text_from_file(self, file_path: str) -> str:
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.pdf':
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
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
        try:
            # Truncate text for summary if too long
            text_sample = text[:5000] if len(text) > 5000 else text
            
            # Extract key information
            key_points = self._extract_key_points(text, source)
            compliance_requirements = self._extract_compliance_requirements(text, source)
            effective_dates = self._extract_effective_dates(text)
            penalties = self._extract_penalties(text)
            definitions = self._extract_definitions(text)
            
            # Generate executive summary
            executive_summary = self._generate_executive_summary(text, source)
            
            # Identify document type
            doc_type = self._identify_document_type(filename, text)
            
            # Extract regulatory scope
            regulatory_scope = self._extract_regulatory_scope(text, source)
            
            return {
                "document_name": filename,
                "source": source.upper(),
                "document_type": doc_type,
                "executive_summary": executive_summary,
                "regulatory_scope": regulatory_scope,
                "key_points": key_points,
                "compliance_requirements": compliance_requirements,
                "effective_dates": effective_dates,
                "penalties": penalties,
                "definitions": definitions,
                "text_length": len(text),
                "analysis_quality_score": self._calculate_analysis_quality(text),
                "generated_timestamp": datetime.now().isoformat(),
                "metadata": {
                    "processing_time": "N/A",  # Could be calculated
                    "confidence_score": self._calculate_confidence_score(text),
                    "language_detected": self._detect_language(text)
                }
            }
        
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return {
                "error": f"Summary generation failed: {str(e)}",
                "document_name": filename,
                "source": source
            }
    
    def _extract_key_points(self, text: str, source: str) -> List[str]:
        key_points = []
        
        # Common regulatory keywords
        keywords = {
            'esma': ['investment', 'market', 'transparency', 'disclosure', 'reporting', 'compliance', 'authorization', 'supervision'],
            'csrc': ['securities', 'public offering', 'listing', 'trading', 'disclosure', 'investor protection', 'market manipulation']
        }
        
        source_keywords = keywords.get(source.lower(), keywords['esma'])
        
        # Split text into sentences
        sentences = re.split(r'[.!?]+', text)
        
        for sentence in sentences[:50]:  # Limit to first 50 sentences
            sentence = sentence.strip()
            if len(sentence) > 30:  # Ignore very short sentences
                for keyword in source_keywords:
                    if keyword.lower() in sentence.lower():
                        key_points.append(sentence[:200] + "..." if len(sentence) > 200 else sentence)
                        break
        
        return list(set(key_points))[:10]  # Return unique points, max 10
    
    def _extract_compliance_requirements(self, text: str, source: str) -> List[str]:
        requirements = []
        
        # Patterns for compliance requirements
        patterns = [
            r'shall\s+([^.]{20,100})',
            r'must\s+([^.]{20,100})',
            r'required\s+to\s+([^.]{20,100})',
            r'obligation\s+to\s+([^.]{20,100})',
            r'duty\s+to\s+([^.]{20,100})'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches[:5]:  # Limit matches per pattern
                requirements.append(f"Must {match.strip()}")
        
        return requirements[:15]  # Max 15 requirements
    
    def _extract_effective_dates(self, text: str) -> List[str]:
        dates = []
        
        # Date patterns
        date_patterns = [
            r'effective\s+(?:from\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'comes?\s+into\s+force\s+(?:on\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'applicable\s+(?:from\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(\d{1,2}\s+\w+\s+\d{4})'  # e.g., "1 January 2024"
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)
        
        return list(set(dates))[:5]  # Return unique dates, max 5
    
    def _extract_penalties(self, text: str) -> List[str]:
        penalties = []
        
        # Penalty patterns
        penalty_patterns = [
            r'penalty\s+of\s+([^.]{10,100})',
            r'fine\s+(?:of\s+)?([^.]{10,100})',
            r'punishment\s+(?:of\s+)?([^.]{10,100})',
            r'sanction\s+(?:of\s+)?([^.]{10,100})'
        ]
        
        for pattern in penalty_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            penalties.extend(matches)
        
        return penalties[:10]  # Max 10 penalties
    
    def _extract_definitions(self, text: str) -> Dict[str, str]:
        definitions = {}
        
        # Definition patterns
        definition_patterns = [
            r'"([^"]+)"\s+means\s+([^.]{20,200})',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+means\s+([^.]{20,200})',
            r'For\s+the\s+purposes?\s+of\s+this\s+[^,]+,\s+"([^"]+)"\s+means\s+([^.]{20,200})'
        ]
        
        for pattern in definition_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for term, definition in matches[:10]:  # Max 10 definitions
                definitions[term.strip()] = definition.strip()
        
        return definitions
    
    def _generate_executive_summary(self, text: str, source: str) -> str:
        # This is a placeholder - in a real implementation, you'd use an LLM
        summary_parts = []
        
        # Extract first meaningful paragraph
        paragraphs = text.split('\n\n')
        for para in paragraphs:
            if len(para) > 100 and any(word in para.lower() for word in ['regulation', 'law', 'rule', 'requirement']):
                summary_parts.append(para[:300] + "...")
                break
        
        if not summary_parts:
            summary_parts.append(f"This document from {source.upper()} contains regulatory content with {len(text)} characters of text.")
        
        return " ".join(summary_parts)
    
    def _identify_document_type(self, filename: str, text: str) -> str:
        filename_lower = filename.lower()
        text_lower = text.lower()
        
        # Document type patterns
        if any(term in filename_lower for term in ['mifid', 'mifir']):
            return 'MiFID II/MiFIR'
        elif any(term in filename_lower for term in ['prospectus']):
            return 'Prospectus Regulation'
        elif any(term in filename_lower for term in ['market', 'abuse']):
            return 'Market Abuse Regulation'
        elif any(term in filename_lower for term in ['mica', 'crypto']):
            return 'MiCA'
        elif any(term in filename_lower for term in ['securities', 'law']):
            return 'Securities Law'
        elif any(term in text_lower for term in ['investment', 'fund']):
            return 'Investment Regulation'
        else:
            return 'Regulatory Document'
    
    def _extract_regulatory_scope(self, text: str, source: str) -> List[str]:
        scope = []
        
        scope_keywords = {
            'esma': ['investment firms', 'market operators', 'trading venues', 'fund managers', 'issuers'],
            'csrc': ['listed companies', 'securities companies', 'fund management companies', 'investors']
        }
        
        keywords = scope_keywords.get(source.lower(), scope_keywords['esma'])
        
        for keyword in keywords:
            if keyword.lower() in text.lower():
                scope.append(keyword)
        
        return scope
    
    def _calculate_analysis_quality(self, text: str) -> float:
        score = 0.0
        
        # Check text length
        if len(text) > 1000:
            score += 0.3
        elif len(text) > 500:
            score += 0.2
        
        # Check for regulatory keywords
        regulatory_keywords = ['shall', 'must', 'requirement', 'compliance', 'regulation', 'law']
        keyword_count = sum(1 for keyword in regulatory_keywords if keyword in text.lower())
        score += min(keyword_count * 0.1, 0.4)
        
        # Check for structure indicators
        if any(indicator in text for indicator in ['Article', 'Section', 'Chapter']):
            score += 0.2
        
        # Check for dates
        if re.search(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', text):
            score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_confidence_score(self, text: str) -> float:
        # Simple confidence calculation based on text characteristics
        if len(text) < 100:
            return 0.3
        elif len(text) < 500:
            return 0.6
        elif len(text) < 2000:
            return 0.8
        else:
            return 0.9
    
    def _detect_language(self, text: str) -> str:
        # Simple language detection
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        total_chars = len(text)
        
        if total_chars > 0 and chinese_chars / total_chars > 0.1:
            return 'Chinese'
        else:
            return 'English'
    
    def _get_summaries_from_source(self, source: str, doc_types: List[str] = None) -> List[Dict]:
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
        try:
            comparison = {
                "document1": doc1.get("document_name", "Unknown"),
                "document2": doc2.get("document_name", "Unknown"),
                "source1": doc1.get("source", "Unknown"),
                "source2": doc2.get("source", "Unknown"),
                "document_type1": doc1.get("document_type", "Unknown"),
                "document_type2": doc2.get("document_type", "Unknown"),
                "similarities": {},
                "differences": {},
                "compliance_gaps": [],
                "recommendations": [],
                "comparison_score": 0.0,
                "comparison_timestamp": datetime.now().isoformat()
            }
            
            # Compare key points
            doc1_points = set(doc1.get("key_points", []))
            doc2_points = set(doc2.get("key_points", []))
            
            comparison["similarities"]["key_points"] = list(doc1_points.intersection(doc2_points))
            comparison["differences"]["key_points"] = {
                "doc1_unique": list(doc1_points - doc2_points),
                "doc2_unique": list(doc2_points - doc1_points)
            }
            
            # Compare compliance requirements
            doc1_compliance = set(doc1.get("compliance_requirements", []))
            doc2_compliance = set(doc2.get("compliance_requirements", []))
            
            comparison["similarities"]["compliance"] = list(doc1_compliance.intersection(doc2_compliance))
            comparison["differences"]["compliance"] = {
                "doc1_unique": list(doc1_compliance - doc2_compliance),
                "doc2_unique": list(doc2_compliance - doc1_compliance)
            }
            
            # Compare regulatory scope
            doc1_scope = set(doc1.get("regulatory_scope", []))
            doc2_scope = set(doc2.get("regulatory_scope", []))
            
            comparison["similarities"]["scope"] = list(doc1_scope.intersection(doc2_scope))
            comparison["differences"]["scope"] = {
                "doc1_unique": list(doc1_scope - doc2_scope),
                "doc2_unique": list(doc2_scope - doc1_scope)
            }
            
            # Identify compliance gaps
            comparison["compliance_gaps"] = self._identify_compliance_gaps(doc1, doc2)
            
            # Generate recommendations
            comparison["recommendations"] = self._generate_recommendations(doc1, doc2, comparison)
            
            # Calculate comparison score
            comparison["comparison_score"] = self._calculate_comparison_score(comparison)
            
            return comparison
        
        except Exception as e:
            logger.error(f"Error in document comparison: {str(e)}")
            return {
                "error": f"Comparison failed: {str(e)}",
                "document1": doc1.get("document_name", "Unknown"),
                "document2": doc2.get("document_name", "Unknown")
            }
    
    def _identify_compliance_gaps(self, doc1: Dict, doc2: Dict) -> List[str]:
        gaps = []
        
        # Check for missing compliance requirements
        doc1_compliance = set(doc1.get("compliance_requirements", []))
        doc2_compliance = set(doc2.get("compliance_requirements", []))
        
        unique_to_doc1 = doc1_compliance - doc2_compliance
        unique_to_doc2 = doc2_compliance - doc1_compliance
        
        if unique_to_doc1:
            gaps.append(f"Requirements in {doc1.get('source', 'Document 1')} not found in {doc2.get('source', 'Document 2')}")
        
        if unique_to_doc2:
            gaps.append(f"Requirements in {doc2.get('source', 'Document 2')} not found in {doc1.get('source', 'Document 1')}")
        
        # Check for conflicting effective dates
        doc1_dates = doc1.get("effective_dates", [])
        doc2_dates = doc2.get("effective_dates", [])
        
        if doc1_dates and doc2_dates and not set(doc1_dates).intersection(set(doc2_dates)):
            gaps.append("Different effective dates may create compliance timing issues")
        
        return gaps
    
    def _generate_recommendations(self, doc1: Dict, doc2: Dict, comparison: Dict) -> List[str]:
        recommendations = []
        
        # Check for low similarity
        if comparison["comparison_score"] < 0.3:
            recommendations.append("Consider conducting detailed legal review due to significant differences")
        
        # Check for missing compliance requirements
        if comparison["compliance_gaps"]:
            recommendations.append("Review compliance gaps to ensure all requirements are met")
        
        # Check for different sources
        if doc1.get("source") != doc2.get("source"):
            recommendations.append("Cross-jurisdictional compliance review recommended")
        
        # Check for different document types
        if doc1.get("document_type") != doc2.get("document_type"):
            recommendations.append("Consider document type differences in compliance strategy")
        
        return recommendations
    
    def _calculate_comparison_score(self, comparison: Dict) -> float:
        score = 0.0
        
        # Score based on similar key points
        total_key_points = len(comparison["differences"]["key_points"]["doc1_unique"]) + \
                          len(comparison["differences"]["key_points"]["doc2_unique"]) + \
                          len(comparison["similarities"]["key_points"])
        
        if total_key_points > 0:
            score += (len(comparison["similarities"]["key_points"]) / total_key_points) * 0.4
        
        # Score based on similar compliance requirements
        total_compliance = len(comparison["differences"]["compliance"]["doc1_unique"]) + \
                          len(comparison["differences"]["compliance"]["doc2_unique"]) + \
                          len(comparison["similarities"]["compliance"])
        
        if total_compliance > 0:
            score += (len(comparison["similarities"]["compliance"]) / total_compliance) * 0.4
        
        # Score based on similar scope
        total_scope = len(comparison["differences"]["scope"]["doc1_unique"]) + \
                     len(comparison["differences"]["scope"]["doc2_unique"]) + \
                     len(comparison["similarities"]["scope"])
        
        if total_scope > 0:
            score += (len(comparison["similarities"]["scope"]) / total_scope) * 0.2
        
        return min(score, 1.0)
    
    def generate_comparative_report(self, source1: str, source2: str = None, doc_types: List[str] = None) -> Dict:
        try:
            # First run comparison
            comparison_result = self.compare_documents(source1, source2, doc_types)
            
            if comparison_result["finalResponse"] != "SUCCESS":
                return comparison_result
            
            # Generate enhanced report
            report = {
                "finalResponse": "SUCCESS",
                "report_type": "Comparative Analysis Report",
                "sources_compared": [source1, source2 or source1],
                "generation_timestamp": datetime.now().isoformat(),
                "executive_summary": self._generate_report_summary(comparison_result["results"]),
                "detailed_analysis": comparison_result["results"],
                "overall_insights": self._generate_overall_insights(comparison_result["results"]),
                "risk_assessment": self._generate_risk_assessment(comparison_result["results"]),
                "action_items": self._generate_action_items(comparison_result["results"])
            }
            
            # Save report
            report_filename = f"comparative_report_{source1}_{source2 or source1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            report_path = os.path.join(self.base_folders[source1], 'comparisons', report_filename)
            
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            report["report_file"] = report_filename
            report["report_path"] = report_path
            
            return report
        
        except Exception as e:
            logger.error(f"Error generating comparative report: {str(e)}")
            return {
                "finalResponse": "FAILED",
                "error": f"Report generation failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _generate_report_summary(self, comparisons: List[Dict]) -> str:
        if not comparisons:
            return "No comparisons available for analysis."
        
        total_comparisons = len(comparisons)
        avg_score = sum(comp.get("comparison_score", 0) for comp in comparisons) / total_comparisons
        high_similarity = sum(1 for comp in comparisons if comp.get("comparison_score", 0) > 0.7)
        
        return f"Analysis of {total_comparisons} document comparisons shows an average similarity score of {avg_score:.2f}. {high_similarity} comparisons indicate high similarity, suggesting potential regulatory alignment."
    
    def _generate_overall_insights(self, comparisons: List[Dict]) -> List[str]:
        insights = []
        
        if not comparisons:
            return ["No comparisons available for insight generation."]
        
        # Common themes
        all_similarities = []
        for comp in comparisons:
            all_similarities.extend(comp.get("similarities", {}).get("key_points", []))
        
        if all_similarities:
            insights.append(f"Found {len(set(all_similarities))} common regulatory themes across documents")
        
        # Gap analysis
        gaps_count = sum(len(comp.get("compliance_gaps", [])) for comp in comparisons)
        if gaps_count > 0:
            insights.append(f"Identified {gaps_count} potential compliance gaps requiring attention")
        
        # Recommendations
        all_recommendations = []
        for comp in comparisons:
            all_recommendations.extend(comp.get("recommendations", []))
        
        unique_recommendations = list(set(all_recommendations))
        if unique_recommendations:
            insights.append(f"Generated {len(unique_recommendations)} unique recommendations for compliance improvement")
        
        # Score distribution
        scores = [comp.get("comparison_score", 0) for comp in comparisons]
        if scores:
            avg_score = sum(scores) / len(scores)
            insights.append(f"Average document similarity score: {avg_score:.2f}")
            
            high_similarity = sum(1 for score in scores if score > 0.7)
            if high_similarity > 0:
                insights.append(f"{high_similarity} document pairs show high similarity (>70%)")
        
        # Cross-jurisdictional analysis
        cross_jurisdictional = sum(1 for comp in comparisons 
                                 if comp.get("source1") != comp.get("source2"))
        if cross_jurisdictional > 0:
            insights.append(f"{cross_jurisdictional} cross-jurisdictional comparisons identified")
        
        return insights
    
    def _generate_risk_assessment(self, comparisons: List[Dict]) -> Dict:
        risk_assessment = {
            "overall_risk_level": "LOW",
            "compliance_risks": [],
            "operational_risks": [],
            "strategic_risks": [],
            "mitigation_priorities": []
        }
        
        if not comparisons:
            return risk_assessment
        
        # Calculate risk metrics
        total_gaps = sum(len(comp.get("compliance_gaps", [])) for comp in comparisons)
        avg_similarity = sum(comp.get("comparison_score", 0) for comp in comparisons) / len(comparisons)
        cross_jurisdictional_count = sum(1 for comp in comparisons 
                                       if comp.get("source1") != comp.get("source2"))
        
        # Determine overall risk level
        if total_gaps > 10 or avg_similarity < 0.3:
            risk_assessment["overall_risk_level"] = "HIGH"
        elif total_gaps > 5 or avg_similarity < 0.6:
            risk_assessment["overall_risk_level"] = "MEDIUM"
        
        # Compliance risks
        if total_gaps > 0:
            risk_assessment["compliance_risks"].append(
                f"Identified {total_gaps} compliance gaps across documents"
            )
        
        # Operational risks
        if avg_similarity < 0.5:
            risk_assessment["operational_risks"].append(
                "Low document similarity may indicate inconsistent regulatory interpretation"
            )
        
        # Strategic risks
        if cross_jurisdictional_count > 0:
            risk_assessment["strategic_risks"].append(
                f"Cross-jurisdictional compliance complexity with {cross_jurisdictional_count} comparisons"
            )
        
        # Mitigation priorities
        if risk_assessment["overall_risk_level"] == "HIGH":
            risk_assessment["mitigation_priorities"].extend([
                "Immediate legal review required",
                "Compliance gap remediation planning",
                "Stakeholder notification and training"
            ])
        elif risk_assessment["overall_risk_level"] == "MEDIUM":
            risk_assessment["mitigation_priorities"].extend([
                "Schedule detailed compliance review",
                "Monitor regulatory updates",
                "Update internal procedures"
            ])
        
        return risk_assessment
    
    def _generate_action_items(self, comparisons: List[Dict]) -> List[Dict]:
        action_items = []
        
        if not comparisons:
            return action_items
        
        # Compliance gap actions
        all_gaps = []
        for comp in comparisons:
            all_gaps.extend(comp.get("compliance_gaps", []))
        
        if all_gaps:
            action_items.append({
                "priority": "HIGH",
                "category": "Compliance",
                "action": "Review and address identified compliance gaps",
                "description": f"Address {len(all_gaps)} compliance gaps across regulatory documents",
                "timeline": "30 days",
                "owner": "Legal/Compliance Team"
            })
        
        # Documentation actions
        low_similarity_count = sum(1 for comp in comparisons 
                                 if comp.get("comparison_score", 0) < 0.4)
        if low_similarity_count > 0:
            action_items.append({
                "priority": "MEDIUM",
                "category": "Documentation",
                "action": "Harmonize regulatory documentation",
                "description": f"Review {low_similarity_count} document pairs with low similarity",
                "timeline": "60 days",
                "owner": "Regulatory Affairs Team"
            })
        
        # Training actions
        unique_recommendations = set()
        for comp in comparisons:
            unique_recommendations.update(comp.get("recommendations", []))
        
        if unique_recommendations:
            action_items.append({
                "priority": "MEDIUM",
                "category": "Training",
                "action": "Staff training on regulatory differences",
                "description": f"Address {len(unique_recommendations)} identified recommendations",
                "timeline": "45 days",
                "owner": "HR/Training Team"
            })
        
        # Monitoring actions
        action_items.append({
            "priority": "LOW",
            "category": "Monitoring",
            "action": "Establish ongoing regulatory monitoring",
            "description": "Set up alerts for regulatory changes and updates",
            "timeline": "90 days",
            "owner": "Regulatory Affairs Team"
        })
        
        return action_items

# Initialize the analysis agent
analysis_agent = RegulatoryAnalysisAgent()

@mcp.tool()
def summarize_regulatory_documents(source: str, doc_type: str = None):
   
    return json.dumps(analysis_agent.summarize_documents(source, doc_type))

@mcp.tool()
def compare_regulatory_documents(source1: str, source2: str = None, doc_types: List[str] = None):
   
    return json.dumps(analysis_agent.compare_documents(source1, source2, doc_types))

@mcp.tool()
def generate_comparative_report(source1: str, source2: str = None, doc_types: List[str] = None):
    
    return json.dumps(analysis_agent.generate_comparative_report(source1, source2, doc_types))

@mcp.tool()
def get_analysis_summary(source: str):
  
    try:
        if source not in analysis_agent.base_folders:
            return json.dumps({
                "finalResponse": "FAILED",
                "error": f"Unknown source: {source}",
                "timestamp": datetime.now().isoformat()
            })
        
        base_path = analysis_agent.base_folders[source]
        summary = {
            "finalResponse": "SUCCESS",
            "source": source,
            "raw_documents": 0,
            "processed_documents": 0,
            "summaries": 0,
            "comparisons": 0,
            "latest_activity": None,
            "timestamp": datetime.now().isoformat()
        }
        
        # Count files in each category
        for category in ['raw', 'processed', 'summaries', 'comparisons']:
            folder_path = os.path.join(base_path, category)
            if os.path.exists(folder_path):
                files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
                summary[category.replace('summaries', 'summaries')] = len(files)
                
                # Get latest activity
                if files:
                    latest_file = max(files, key=lambda f: os.path.getctime(os.path.join(folder_path, f)))
                    latest_time = os.path.getctime(os.path.join(folder_path, latest_file))
                    if not summary["latest_activity"] or latest_time > summary["latest_activity"]["timestamp"]:
                        summary["latest_activity"] = {
                            "file": latest_file,
                            "category": category,
                            "timestamp": latest_time,
                            "formatted_time": datetime.fromtimestamp(latest_time).isoformat()
                        }
        
        return json.dumps(summary)
    
    except Exception as e:
        logger.error(f"Error getting analysis summary: {str(e)}")
        return json.dumps({
            "finalResponse": "FAILED",
            "error": f"Failed to get analysis summary: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })

@mcp.tool()
def get_document_details(source: str, document_name: str):
   
    try:
        if source not in analysis_agent.base_folders:
            return json.dumps({
                "finalResponse": "FAILED",
                "error": f"Unknown source: {source}",
                "timestamp": datetime.now().isoformat()
            })
        
        base_path = analysis_agent.base_folders[source]
        document_info = {
            "finalResponse": "SUCCESS",
            "source": source,
            "document_name": document_name,
            "found_in": [],
            "details": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # Check each folder for the document
        for category in ['raw', 'processed', 'summaries', 'comparisons']:
            folder_path = os.path.join(base_path, category)
            if os.path.exists(folder_path):
                # Look for files containing the document name
                matching_files = [f for f in os.listdir(folder_path) 
                                if document_name.lower() in f.lower()]
                
                if matching_files:
                    document_info["found_in"].append(category)
                    document_info["details"][category] = []
                    
                    for file in matching_files:
                        file_path = os.path.join(folder_path, file)
                        file_stats = os.stat(file_path)
                        
                        file_info = {
                            "filename": file,
                            "size_bytes": file_stats.st_size,
                            "created": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                            "modified": datetime.fromtimestamp(file_stats.st_mtime).isoformat()
                        }
                        
                        # If it's a summary file, load the content
                        if category == 'summaries' and file.endswith('.json'):
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    summary_content = json.load(f)
                                    file_info["summary_preview"] = {
                                        "document_type": summary_content.get("document_type"),
                                        "key_points_count": len(summary_content.get("key_points", [])),
                                        "compliance_requirements_count": len(summary_content.get("compliance_requirements", [])),
                                        "analysis_quality_score": summary_content.get("analysis_quality_score")
                                    }
                            except Exception as e:
                                file_info["summary_preview"] = f"Error loading summary: {str(e)}"
                        
                        document_info["details"][category].append(file_info)
        
        if not document_info["found_in"]:
            document_info["finalResponse"] = "NOT_FOUND"
            document_info["message"] = f"Document '{document_name}' not found in {source} repository"
        
        return json.dumps(document_info)
    
    except Exception as e:
        logger.error(f"Error getting document details: {str(e)}")
        return json.dumps({
            "finalResponse": "FAILED",
            "error": f"Failed to get document details: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })

@mcp.tool()
def cleanup_analysis_files(source: str, category: str = None, older_than_days: int = 30):
   
    try:
        if source not in analysis_agent.base_folders:
            return json.dumps({
                "finalResponse": "FAILED",
                "error": f"Unknown source: {source}",
                "timestamp": datetime.now().isoformat()
            })
        
        base_path = analysis_agent.base_folders[source]
        categories_to_clean = [category] if category else ['processed', 'summaries', 'comparisons']
        
        cleanup_results = {
            "finalResponse": "SUCCESS",
            "source": source,
            "categories_cleaned": [],
            "files_removed": 0,
            "space_freed_bytes": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        cutoff_time = time.time() - (older_than_days * 24 * 60 * 60)
        
        for cat in categories_to_clean:
            folder_path = os.path.join(base_path, cat)
            if os.path.exists(folder_path):
                files_removed = 0
                space_freed = 0
                
                for filename in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, filename)
                    if os.path.isfile(file_path):
                        file_stats = os.stat(file_path)
                        if file_stats.st_mtime < cutoff_time:
                            space_freed += file_stats.st_size
                            os.remove(file_path)
                            files_removed += 1
                            logger.info(f"Removed old file: {filename}")
                
                if files_removed > 0:
                    cleanup_results["categories_cleaned"].append({
                        "category": cat,
                        "files_removed": files_removed,
                        "space_freed_bytes": space_freed
                    })
                    cleanup_results["files_removed"] += files_removed
                    cleanup_results["space_freed_bytes"] += space_freed
        
        return json.dumps(cleanup_results)
    
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        return json.dumps({
            "finalResponse": "FAILED",
            "error": f"Cleanup failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })

if __name__ == "__main__":
    # Initialize and run the server
    print(f"Starting Regulatory Analysis MCP Server on port {ANALYSIS_MCP_PORT}")
    mcp.run(transport='sse')