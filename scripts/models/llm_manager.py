import os
import sys
import json
import logging
import re
from pathlib import Path

# Configuration
MODEL_DIRECTORY = os.path.expanduser("~/.cache/lm-studio/models")
LLM_MODEL_PATH = os.path.join(
    MODEL_DIRECTORY,
    "lmstudio-community/Phi-3.1-mini-128k-instruct-GGUF/Phi-3.1-mini-128k-instruct-Q4_K_M.gguf",
)

class GeminiLLM:
    def __init__(self, model_name: str = "gemini-2.5-pro-preview"):
        import google.generativeai as genai
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def create_chat_completion(self, messages, temperature: float, max_tokens: int):
        prompt = "\n".join(m["content"] for m in messages)
        resp = self.model.generate_content(
            prompt,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        return {"choices": [{"message": {"content": resp.text}}]}

class LLMManager:
    def __init__(self):
        self.llm = None
        self.backend = None

    def load_llm(self, backend: str = None):
        """Initialize and return the LLM text generator."""
        backend = backend or os.getenv("LLM_BACKEND", "phi")
        
        if self.llm is None or backend != self.backend:
            self.backend = backend
            if backend == "gemini":
                logging.info("Loading Gemini model")
                print("Loading Gemini model...", file=sys.stderr)
                self.llm = GeminiLLM()
            else:
                from llama_cpp import Llama
                logging.info("Loading LLaMA model from %s", LLM_MODEL_PATH)
                print("Loading local Phi model...", file=sys.stderr)
                self.llm = Llama(
                    model_path=LLM_MODEL_PATH,
                    n_gpu_layers=-1,
                    n_ctx=8192,
                    verbose=True,
                    chat_format="chatml",
                )
            logging.info("LLM model loaded: %s", backend)
            print("Model loaded successfully", file=sys.stderr)
        
        return self.llm

    def extract_json(self, text: str):
        """Extract the most relevant JSON object or array found in text."""
        logging.debug("extract_json input: %s", text[:200])
        decoder = json.JSONDecoder()
        text = text.strip()
        
        # Remove paired <think>...</think> blocks that some LLMs prepend
        think_tag_re = re.compile(r"<think>.*?</think>", re.DOTALL)
        text = think_tag_re.sub("", text)
        text = text.replace("<think>", "")   # handle stray opening tag
        text = text.replace("</think>", "")  # handle stray closing tag
        
        # Remove Markdown-style code fences if present
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n", "", text)
            if text.endswith("```"):
                text = text[:-3]

        best_obj = None
        best_len = -1
        for idx, ch in enumerate(text):
            if ch in "[{":
                try:
                    obj, end = decoder.raw_decode(text[idx:])
                except json.JSONDecodeError:
                    continue
                length = end
                if length > best_len:
                    best_obj = obj
                    best_len = length
        
        if best_obj is not None:
            return best_obj
        
        logging.error("extract_json: failed to find JSON")
        raise ValueError("No JSON object found in LLM output.")

    def deduplicate_posts(self, posts: list[dict]) -> list[dict]:
        """Remove posts that share the same source_quote."""
        logging.info("deduplicate_posts: starting with %d posts", len(posts))
        seen = set()
        unique = []
        for post in posts:
            quote = post.get("source_quote")
            if quote and quote in seen:
                continue
            if quote:
                seen.add(quote)
            unique.append(post)
        logging.info("deduplicate_posts: returning %d posts", len(unique))
        return unique

    def generate_posts_from_text(self, context, source_type):
        """Generate high-quality social media posts with enhanced prompting."""
        
        # Enhanced system prompt that's much more specific about what makes content viral
        system_prompt = """You are creating authentic, engaging social media posts from source material. 

Your posts should:
- Sound natural and conversational (avoid "mind-blowing" or "game-changing" clichés)
- Vary in style - some can be questions, observations, quick tips, or thought starters
- Stay under 280 characters total
- Use minimal emojis (0-2 max, only when they add value)
- Feel like something a real person would share, not marketing copy

Extract meaningful insights and present them in diverse ways:
- "Ever notice how..." 
- "Quick thought on..."
- "This changed my perspective:"
- "Worth remembering:"
- Or just state the insight directly

You MUST provide your output as a valid JSON array of objects with ONLY the JSON text.
Each object must have:
- "post_text": The complete social media post (under 280 chars)
- "source_quote": The exact phrase from source that inspired this post
- Each source_quote must be unique

For PDFs with page markers, also include:
- "page_number": The page number as an integer

Examples of good variety:
[
  {
    "post_text": "The most successful people aren't just working harder - they're working smarter. Focus on leverage, not just effort. #productivity",
    "source_quote": "The key to success is not just hard work, but smart work"
  },
  {
    "post_text": "Quick reminder: your attention is your most valuable resource. Where you focus determines your reality. #mindfulness #focus", 
    "source_quote": "What you pay attention to becomes your experience"
  },
  {
    "post_text": "Ever wonder why some habits stick and others don't? It's about environment design, not willpower. #habits",
    "source_quote": "Environment is the invisible hand that shapes human behavior"
  }
]
"""

        # Estimate tokens and chunk if needed
        chars_per_token = 4
        output_token_buffer = 1024
        max_context_tokens = 8192 - (len(system_prompt) + output_token_buffer)
        max_context_chars = max_context_tokens * chars_per_token

        logging.info("generate_posts_from_text: %d chars from %s", len(context), source_type)
        print("Generating viral social media posts...", file=sys.stderr)
        
        llm = self.load_llm()
        all_posts = []
        
        # Process content in chunks
        for i in range(0, len(context), max_context_chars):
            chunk = context[i:i + max_context_chars]
            logging.debug("generate_posts_from_text: processing chunk %d-%d", i, i + len(chunk))

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user", 
                    "content": f"Extract the most VIRAL quotes from this {source_type}. Focus on controversial, surprising, or valuable insights that people will want to share:\n\n{chunk}"
                }
            ]

            logging.debug("LLM INPUT: %s", json.dumps(messages, ensure_ascii=False))

            chat_completion = llm.create_chat_completion(
                messages=messages,
                temperature=0.4,  # Higher creativity for viral content
                max_tokens=output_token_buffer,
            )

            response_content = chat_completion['choices'][0]['message']['content']
            logging.debug("LLM OUTPUT: %s", response_content)
            print("--- RAW LLM OUTPUT ---", file=sys.stderr)
            print(response_content, file=sys.stderr)
            print("--- END RAW LLM OUTPUT ---", file=sys.stderr)

            try:
                data = self.extract_json(response_content)
                if isinstance(data, dict):
                    if len(data) == 1 and isinstance(list(data.values())[0], list):
                        posts = list(data.values())[0]
                    elif "post_text" in data and "source_quote" in data:
                        posts = [data]
                    else:
                        raise ValueError("JSON object does not contain expected structure")
                elif isinstance(data, list):
                    posts = data
                else:
                    raise ValueError("JSON output must be a list of objects")

                if any(not isinstance(p, dict) for p in posts):
                    raise ValueError("JSON array must contain objects")

                # Basic validation - ensure posts have required fields
                valid_posts = []
                for post in posts:
                    if isinstance(post, dict) and "post_text" in post and "source_quote" in post:
                        valid_posts.append(post)
                    else:
                        logging.warning("Skipping invalid post: %s", post)
                
                all_posts.extend(valid_posts)
                print(f"Extracted {len(valid_posts)} posts from chunk", file=sys.stderr)

            except Exception as e:
                error_msg = f"Failed to parse LLM output: {e}. Raw output: {response_content}"
                print(f"Error parsing JSON output: {e}", file=sys.stderr)
                logging.warning("Chunk processing failed: %s", error_msg)
                # Continue processing other chunks instead of failing completely
                continue

        final_posts = self.deduplicate_posts(all_posts)
        logging.info("generate_posts_from_text: produced %d final posts", len(final_posts))
        print(f"Generated {len(final_posts)} viral posts", file=sys.stderr)
        
        return final_posts