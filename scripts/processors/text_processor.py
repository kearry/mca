import logging
import sys

class TextProcessor:
    def __init__(self):
        pass

    def process(self, file_path, job_id):
        """Process a text file and return its contents."""
        logging.info("TextProcessor: reading %s", file_path)
        print("Processing text...", file=sys.stderr)
        
        with open(file_path, "r", encoding="utf-8") as f:
            text_content = f.read()
        
        logging.info("TextProcessor: read %d characters", len(text_content))
        print(f"Read {len(text_content)} characters", file=sys.stderr)
        
        return text_content