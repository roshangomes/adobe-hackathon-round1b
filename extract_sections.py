from datetime import datetime
import fitz  # PyMuPDF
import json
import os
import re
from typing import List, Dict

def detect_heading_level(font_size: float, max_font: float) -> str:
    if font_size >= max_font * 0.95:
        return "H1"
    elif font_size >= max_font * 0.75:
        return "H2"
    elif font_size >= max_font * 0.55:
        return "H3"
    else:
        return None

def extract_outline(pdf_path: str) -> Dict:
    doc = fitz.open(pdf_path)
    outline, all_font_sizes = [], []
    title = "Unknown Title"

    # Collect all font sizes from the document
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span["text"].strip():
                        all_font_sizes.append(span["size"])

    max_font = max(all_font_sizes) if all_font_sizes else 12

    # Improved title extraction - look for largest font on first page
    try:
        first_page_blocks = doc[0].get_text("dict")["blocks"]
        title_candidates = []
        for block in first_page_blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span["size"] >= max_font * 0.95 and span["text"].strip():
                        title_candidates.append(span["text"].strip())
        if title_candidates:
            title = " ".join(title_candidates)
    except (IndexError, KeyError):
        pass

    # Extract headings from all pages
    for i, page in enumerate(doc, start=1):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                full_line_text = " ".join(
                    span["text"].strip() for span in line.get("spans", []) if span["text"].strip()
                )
                if not full_line_text or len(full_line_text.split()) > 15:
                    continue
                
                font_sizes = [span["size"] for span in line.get("spans", []) if span["text"].strip()]
                if not font_sizes:
                    continue
                
                font_size = max(font_sizes)
                level = detect_heading_level(font_size, max_font)
                if level:
                    outline.append({
                        "level": level,
                        "text": full_line_text,
                        "page": i
                    })

    doc.close()
    return {"title": title.strip(), "outline": outline}

def score_relevance(text: str, job_keywords: List[str]) -> float:
    """Calculate relevance score based on keyword matches"""
    if not job_keywords:
        return 0
    
    text_lower = text.lower()
    matches = sum(1 for keyword in job_keywords if keyword.lower() in text_lower)
    return matches / len(job_keywords)

def extract_sections(pdf_dir: str, persona: str, job: str) -> Dict:
    job_keywords = re.split(r'\s+', job.lower().strip())
    sections, sub_sections, seen_subsections = [], [], set()
    
    # Get all PDF files in directory
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]

    for pdf_file in pdf_files:
        pdf_path = os.path.join(pdf_dir, pdf_file)
        try:
            outline_data = extract_outline(pdf_path)
            
            for item in outline_data['outline']:
                relevance = score_relevance(item['text'], job_keywords)
                
                # Higher threshold for relevance (0.3 instead of 0)
                if relevance > 0.3:
                    sections.append({
                        "document": pdf_file,
                        "page_number": item['page'],
                        "section_title": item['text'],
                        "importance_rank": relevance
                    })

                    # Extract sub-section content
                    doc = fitz.open(pdf_path)
                    page_key = (pdf_file, item['page'])
                    
                    if page_key not in seen_subsections and item['page'] - 1 < len(doc):
                        try:
                            page = doc[item['page'] - 1]
                            page_text = page.get_text().strip()
                            
                            # Better text extraction - take first line up to 300 chars
                            refined_text = page_text.split('\n')[0][:300] if page_text else ""
                            
                            if refined_text:
                                sub_sections.append({
                                    "document": pdf_file,
                                    "refined_text": refined_text,
                                    "page_number": item['page']
                                })
                                seen_subsections.add(page_key)
                        except Exception as e:
                            print(f"Error extracting text from page {item['page']} in {pdf_file}: {e}")
                    
                    doc.close()
                    
        except Exception as e:
            print(f"Error processing {pdf_file}: {e}")
            continue

    # Sort all found sections by importance score (higher is better)
    sections.sort(key=lambda x: x['importance_rank'], reverse=True)

    # Keep only the top 25 most relevant sections
    sections = sections[:25]

    # Now, re-rank the final list from 1 to 25
    for i, section in enumerate(sections, 1):
        section['importance_rank'] = i

    return {
        "metadata": {
            "input_documents": pdf_files,
            "persona": persona,
            "job_to_be_done": job,
            "processing_timestamp": datetime.now().isoformat()
        },
        "extracted_sections": sections,
        "sub_section_analysis": sub_sections
    }

def save_output(output_data: Dict, output_path: str):
    """Save the output data to a JSON file"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Output saved to {output_path}")
    except Exception as e:
        print(f"Error saving output: {e}")

def run_from_json(json_path: str, output_path: str):
    """Run extraction from JSON input file"""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pdf_dir = "pdfs"  # Fixed directory inside container
        persona = data["persona"]["role"]
        job = data["job_to_be_done"]["task"]

        result = extract_sections(pdf_dir, persona, job)
        save_output(result, output_path)
        
    except Exception as e:
        print(f"Error running from JSON: {e}")

def main():
    """Main function to handle command line arguments"""
    import sys
    
    if len(sys.argv) == 3:
        # Usage: python extract_sections.py input.json output.json
        run_from_json(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 5:
        # Usage: python extract_sections.py pdf_folder "Persona" "Task" output.json
        pdf_dir = sys.argv[1]
        persona = sys.argv[2]
        job = sys.argv[3]
        output_path = sys.argv[4]
        
        result = extract_sections(pdf_dir, persona, job)
        save_output(result, output_path)
    else:
        print("Usage:")
        print("  python extract_sections.py <pdf_dir> <persona> <task> <output_json>")
        print("  OR")
        print("  python extract_sections.py <input_json> <output_json>")

if __name__ == "__main__":
    main()