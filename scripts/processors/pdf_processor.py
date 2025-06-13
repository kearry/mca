import logging
import sys
from pathlib import Path

class PDFProcessor:
    def __init__(self, public_folder):
        self.public_folder = public_folder

    def process(self, file_path, job_id):
        """Process a PDF file and return extracted text and image paths."""
        import fitz  # PyMuPDF
        
        logging.info("PDFProcessor: opening %s", file_path)
        print("Processing PDF...", file=sys.stderr)
        
        doc = fitz.open(file_path)
        full_text = ""
        image_paths = []
        
        for page_num, page in enumerate(doc):
            full_text += f"\n\n--- Page {page_num + 1} ---\n\n"
            full_text += page.get_text("text")
            
            # Extract images from this page
            image_list = page.get_images(full=True)
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                img_filename = f"{job_id}_page{page_num + 1}_img{img_index}.{image_ext}"
                img_path = self.public_folder / img_filename
                
                with open(img_path, "wb") as f:
                    f.write(image_bytes)
                
                image_paths.append({
                    "path": f"/generated/{img_filename}", 
                    "page": page_num + 1
                })
        
        doc.close()
        logging.info("PDFProcessor: extracted %d pages, %d images", 
                    len(doc), len(image_paths))
        print(f"Extracted {len(doc)} pages and {len(image_paths)} images", file=sys.stderr)
        
        return full_text, image_paths