import os
import sys
import json
import subprocess
import logging
from pathlib import Path
import re
from difflib import SequenceMatcher
from typing import List, Dict, Tuple, Optional

class DebuggingQuoteMatcher:
    """
    Quote matcher with extensive debugging to show what's happening
    """
    
    def __init__(self):
        # Try to import advanced fuzzy matching library
        self.use_rapidfuzz = False
        try:
            import rapidfuzz
            from rapidfuzz import fuzz, process
            self.rapidfuzz = rapidfuzz
            self.fuzz = fuzz
            self.process = process
            self.use_rapidfuzz = True
            print("🚀 Using rapidfuzz for advanced quote matching", file=sys.stderr)
        except ImportError:
            print("📝 Using standard fuzzy matching (install rapidfuzz for better results)", file=sys.stderr)
    
    def normalize_text(self, text: str) -> str:
        """Clean and normalize text for matching."""
        if not text:
            return ""
        
        # Convert to lowercase and remove extra whitespace
        text = text.lower().strip()
        
        # Remove punctuation but keep apostrophes in contractions
        text = re.sub(r"[^\w\s']", " ", text)
        
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        
        return text.strip()
    
    def extract_keywords(self, text: str, min_length: int = 3) -> List[str]:
        """Extract meaningful keywords from text."""
        words = self.normalize_text(text).split()
        
        # Filter out common stop words and short words
        stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
            'after', 'above', 'below', 'between', 'among', 'is', 'are', 'was',
            'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
            'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might',
            'must', 'shall', 'this', 'that', 'these', 'those', 'i', 'you', 'he',
            'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my',
            'your', 'his', 'her', 'its', 'our', 'their', 'a', 'an'
        }
        
        keywords = [word for word in words 
                   if len(word) >= min_length and word not in stop_words]
        
        return keywords
    
    def word_overlap_score(self, text1: str, text2: str) -> float:
        """Calculate word overlap score between two texts."""
        words1 = set(self.normalize_text(text1).split())
        words2 = set(self.normalize_text(text2).split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        # Jaccard similarity
        jaccard = len(intersection) / len(union) if union else 0.0
        
        # Also calculate coverage of the quote in the text
        quote_coverage = len(intersection) / len(words1) if words1 else 0.0
        
        # Combined score favoring good coverage
        return 0.4 * jaccard + 0.6 * quote_coverage
    
    def keyword_match_score(self, quote: str, text: str) -> float:
        """Score based on keyword matching."""
        quote_keywords = self.extract_keywords(quote)
        text_keywords = self.extract_keywords(text)
        
        if not quote_keywords:
            return 0.0
        
        # Count how many quote keywords appear in the text
        matches = sum(1 for kw in quote_keywords if kw in text_keywords)
        return matches / len(quote_keywords)
    
    def sequence_similarity(self, text1: str, text2: str) -> float:
        """Get sequence similarity using the best available method."""
        if self.use_rapidfuzz:
            # rapidfuzz has better algorithms than difflib
            return self.fuzz.ratio(text1, text2) / 100.0
        else:
            # Fallback to standard library
            return SequenceMatcher(None, text1, text2).ratio()
    
    def find_best_match(self, segments: List[Dict], quote: str, 
                       max_window: int = 25, context_padding: float = 2.0) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        Find the best matching segment(s) for a quote using multiple strategies.
        
        Returns: (start_time, end_time, matched_text) or (None, None, None)
        """
        if not quote or not segments:
            print("❌ No quote or no segments provided", file=sys.stderr)
            return None, None, None
        
        print(f"🔍 DEBUGGING QUOTE SEARCH:", file=sys.stderr)
        print(f"   Quote: '{quote}'", file=sys.stderr)
        print(f"   Segments: {len(segments)} total", file=sys.stderr)
        print(f"   First few segments:", file=sys.stderr)
        for i, seg in enumerate(segments[:3]):
            print(f"     [{i}] {seg.get('start', 0):.1f}s-{seg.get('end', 0):.1f}s: '{seg.get('text', '')[:50]}...'", file=sys.stderr)
        
        normalized_quote = self.normalize_text(quote)
        quote_words = normalized_quote.split()
        
        print(f"   Normalized quote: '{normalized_quote}'", file=sys.stderr)
        print(f"   Quote words: {len(quote_words)}", file=sys.stderr)
        
        if len(quote_words) < 2:
            print("   Using exact substring search for short quote", file=sys.stderr)
            # Very short quotes - use exact substring matching
            result = self._find_exact_substring(segments, quote, context_padding)
            if result[0] is not None:
                print(f"   ✅ Exact match found: {result[0]:.1f}s-{result[1]:.1f}s", file=sys.stderr)
            else:
                print(f"   ❌ No exact match found", file=sys.stderr)
            return result
        
        best_score = 0.0
        best_match = None
        best_window_info = None
        candidates_tested = 0
        
        # With merged segments, we can use smaller windows
        window_sizes = [1, 2, 3, 5, 8]  # Reduced since segments are now longer
        window_sizes = [w for w in window_sizes if w <= len(segments)]
        
        print(f"   Testing window sizes: {window_sizes}", file=sys.stderr)
        
        for window_size in window_sizes:
            for start_idx in range(len(segments) - window_size + 1):
                candidates_tested += 1
                
                # Combine segments in this window
                window_segments = segments[start_idx:start_idx + window_size]
                combined_text = " ".join(seg.get("text", "") for seg in window_segments)
                
                if not combined_text.strip():
                    continue
                
                # Calculate multiple similarity scores
                scores = self._calculate_all_scores(quote, combined_text)
                
                # Weighted combination of scores
                final_score = (
                    0.3 * scores['sequence'] +
                    0.4 * scores['word_overlap'] +
                    0.3 * scores['keyword_match']
                )
                
                # Bonus for appropriate length matches
                text_word_count = len(self.normalize_text(combined_text).split())
                if len(quote_words) > 0:
                    length_ratio = min(text_word_count / len(quote_words), len(quote_words) / text_word_count)
                    length_bonus = 1.0 + 0.2 * max(0, length_ratio - 0.5)
                else:
                    length_bonus = 1.0
                
                adjusted_score = final_score * length_bonus
                
                # Debug output for promising candidates (reduced noise)
                if adjusted_score > 0.6 or candidates_tested <= 3:  # Show fewer candidates
                    start_time = window_segments[0].get("start", 0)
                    end_time = window_segments[-1].get("end", 0)
                    print(f"     Candidate [{start_idx}:{start_idx+window_size}] {start_time:.1f}s-{end_time:.1f}s", file=sys.stderr)
                    print(f"       Score: {adjusted_score:.3f}", file=sys.stderr)
                    print(f"       Text: '{combined_text[:60]}...'", file=sys.stderr)
                
                if adjusted_score > best_score:
                    best_score = adjusted_score
                    start_time = window_segments[0].get("start")
                    end_time = window_segments[-1].get("end")
                    
                    best_match = (start_time, end_time, combined_text.strip())
                    best_window_info = {
                        'start_idx': start_idx,
                        'window_size': window_size,
                        'scores': scores,
                        'final_score': final_score,
                        'length_bonus': length_bonus
                    }
                    
                    print(f"       ⭐ NEW BEST MATCH!", file=sys.stderr)
        
        print(f"   Tested {candidates_tested} candidates", file=sys.stderr)
        
        # Use more conservative thresholds to avoid false positives
        min_threshold = 0.5 if len(quote_words) <= 5 else 0.4 if len(quote_words) <= 10 else 0.35
        
        print(f"   Best score: {best_score:.3f}, threshold: {min_threshold}", file=sys.stderr)
        
        if best_score >= min_threshold and best_match:
            raw_start, raw_end = best_match[0], best_match[1]
            
            # Apply context padding more carefully
            if raw_start is not None and raw_end is not None:
                # Only apply padding if we're not already at the very beginning
                padded_start = max(0, raw_start - context_padding) if raw_start > context_padding else raw_start
                padded_end = raw_end + context_padding
                
                duration = padded_end - padded_start
                raw_duration = raw_end - raw_start
                
                print(f"   ✅ MATCH ACCEPTED:", file=sys.stderr)
                print(f"     Raw times: {raw_start:.1f}s - {raw_end:.1f}s ({raw_duration:.1f}s)", file=sys.stderr)
                print(f"     Padded times: {padded_start:.1f}s - {padded_end:.1f}s ({duration:.1f}s)", file=sys.stderr)
                
                return padded_start, padded_end, best_match[2]
        
        print(f"   ❌ NO ACCEPTABLE MATCH FOUND", file=sys.stderr)
        print(f"     Best score {best_score:.3f} < threshold {min_threshold}", file=sys.stderr)
        
        return None, None, None
    
    def _calculate_all_scores(self, quote: str, text: str) -> Dict[str, float]:
        """Calculate all similarity scores."""
        normalized_quote = self.normalize_text(quote)
        normalized_text = self.normalize_text(text)
        
        return {
            'sequence': self.sequence_similarity(normalized_quote, normalized_text),
            'word_overlap': self.word_overlap_score(quote, text),
            'keyword_match': self.keyword_match_score(quote, text)
        }
    
    def _find_exact_substring(self, segments: List[Dict], quote: str, 
                            context_padding: float) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Find exact substring matches for very short quotes."""
        normalized_quote = self.normalize_text(quote).lower()
        
        print(f"   Looking for exact substring: '{normalized_quote}'", file=sys.stderr)
        
        for i, segment in enumerate(segments):
            text = self.normalize_text(segment.get("text", "")).lower()
            if normalized_quote in text:
                start_time = segment.get("start")
                end_time = segment.get("end")
                
                print(f"   Found in segment {i}: '{segment.get('text', '')}'", file=sys.stderr)
                print(f"   Times: {start_time}s - {end_time}s", file=sys.stderr)
                
                if start_time is not None:
                    padded_start = max(0, start_time - context_padding)
                else:
                    padded_start = 0
                    
                if end_time is not None:
                    padded_end = end_time + context_padding
                else:
                    padded_end = 10  # fallback
                
                return padded_start, padded_end, segment.get("text", "")
        
        return None, None, None


class YouTubeProcessor:
    def __init__(self, public_folder, watermark_path):
        self.public_folder = public_folder
        self.watermark_path = watermark_path
        self.quote_matcher = DebuggingQuoteMatcher()

    def merge_short_segments(self, segments, min_duration=8.0, max_duration=20.0):
        """
        Merge short segments into longer, more meaningful chunks.
        
        Args:
            segments: List of transcript segments
            min_duration: Minimum duration for a merged segment (seconds)
            max_duration: Maximum duration for a merged segment (seconds)
        
        Returns:
            List of merged segments with longer, more coherent text
        """
        if not segments:
            return segments
        
        print(f"🔧 MERGING SEGMENTS:", file=sys.stderr)
        print(f"   Input: {len(segments)} segments", file=sys.stderr)
        print(f"   Target duration: {min_duration}s - {max_duration}s", file=sys.stderr)
        
        merged_segments = []
        current_chunk = None
        
        for i, segment in enumerate(segments):
            start_time = segment.get("start", 0)
            end_time = segment.get("end", 0)
            text = segment.get("text", "").strip()
            
            if not text:
                continue
            
            # Start a new chunk if needed
            if current_chunk is None:
                current_chunk = {
                    "start": start_time,
                    "end": end_time,
                    "text": text,
                    "segment_count": 1
                }
                continue
            
            # Calculate what the duration would be if we add this segment
            potential_duration = end_time - current_chunk["start"]
            
            # Decide whether to extend current chunk or start new one
            should_extend = True
            
            # Don't extend if it would make chunk too long
            if potential_duration > max_duration:
                should_extend = False
            
            # Don't extend if current chunk is already long enough and we hit a natural break
            elif (current_chunk["end"] - current_chunk["start"]) >= min_duration:
                # Look for natural breaking points
                if any(punct in current_chunk["text"][-10:] for punct in ['.', '!', '?']):
                    # Previous chunk ended with sentence punctuation
                    should_extend = False
                elif text.startswith(('-', '•', '—')):
                    # New segment starts with dash (new speaker/thought)
                    should_extend = False
                elif any(phrase in text.lower()[:20] for phrase in ['so ', 'now ', 'but ', 'and so', 'okay', 'alright']):
                    # New segment starts with transition words
                    should_extend = False
            
            if should_extend:
                # Extend current chunk
                current_chunk["end"] = end_time
                # Add space between segments unless previous text ends with punctuation
                if current_chunk["text"] and not current_chunk["text"][-1] in '.,!?;:':
                    current_chunk["text"] += " " + text
                else:
                    current_chunk["text"] += " " + text
                current_chunk["segment_count"] += 1
            else:
                # Finalize current chunk and start new one
                chunk_duration = current_chunk["end"] - current_chunk["start"]
                if chunk_duration >= 1.0:  # Only keep chunks that are at least 1 second
                    merged_segments.append({
                        "start": current_chunk["start"],
                        "end": current_chunk["end"],
                        "text": current_chunk["text"].strip()
                    })
                
                # Start new chunk
                current_chunk = {
                    "start": start_time,
                    "end": end_time,
                    "text": text,
                    "segment_count": 1
                }
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_duration = current_chunk["end"] - current_chunk["start"]
            if chunk_duration >= 1.0:
                merged_segments.append({
                    "start": current_chunk["start"],
                    "end": current_chunk["end"],
                    "text": current_chunk["text"].strip()
                })
        
        print(f"   Output: {len(merged_segments)} merged segments", file=sys.stderr)
        if merged_segments:
            avg_duration = sum(s['end'] - s['start'] for s in merged_segments) / len(merged_segments)
            print(f"   Average duration: {avg_duration:.1f}s", file=sys.stderr)
        
        return merged_segments

    def extract_clip_with_verification(self, video_path, start, end, output_path, quote, segments, padding=1.0):
        """
        Extract a clip and verify it contains the quote, with fallback mechanisms for timing drift.
        """
        original_start, original_end = start, end
        
        print(f"🎬 VERIFIED CLIP EXTRACTION:", file=sys.stderr)
        print(f"   Quote: '{quote}'", file=sys.stderr)
        print(f"   Target times: {start:.1f}s - {end:.1f}s", file=sys.stderr)
        
        # Try multiple strategies if the first one fails
        strategies = [
            {"name": "Exact timing", "start_offset": 0, "end_offset": 0, "extra_padding": 0},
            {"name": "Small buffer", "start_offset": -2, "end_offset": 2, "extra_padding": 1},
            {"name": "Medium buffer", "start_offset": -5, "end_offset": 5, "extra_padding": 2},
            {"name": "Large buffer", "start_offset": -10, "end_offset": 10, "extra_padding": 3},
            {"name": "Extended search", "start_offset": -30, "end_offset": 30, "extra_padding": 5},
        ]
        
        for i, strategy in enumerate(strategies):
            print(f"   Strategy {i+1}: {strategy['name']}", file=sys.stderr)
            
            # Adjust timing based on strategy
            adjusted_start = max(0, start + strategy["start_offset"])
            adjusted_end = end + strategy["end_offset"]
            total_padding = padding + strategy["extra_padding"]
            
            # Create temporary clip path for testing
            temp_clip_path = str(output_path).replace('.mp4', f'_test_{i}.mp4')
            
            try:
                success = self._extract_single_clip(
                    video_path, adjusted_start, adjusted_end, temp_clip_path, total_padding
                )
                
                if not success:
                    print(f"     ❌ Extraction failed", file=sys.stderr)
                    continue
                
                # Verify the clip contains the quote
                verification_result = self._verify_clip_contains_quote(temp_clip_path, quote, strategy['name'])
                
                if verification_result['likely_contains_quote']:
                    print(f"     ✅ Verification passed: {verification_result['confidence']}", file=sys.stderr)
                    
                    # Move successful clip to final location
                    import shutil
                    shutil.move(temp_clip_path, output_path)
                    
                    return {
                        'success': True,
                        'strategy': strategy['name'],
                        'adjusted_start': adjusted_start,
                        'adjusted_end': adjusted_end,
                        'confidence': verification_result['confidence'],
                        'original_start': original_start,
                        'original_end': original_end
                    }
                else:
                    print(f"     ❌ Verification failed: {verification_result['reason']}", file=sys.stderr)
                    # Clean up failed attempt
                    try:
                        os.remove(temp_clip_path)
                    except:
                        pass
                    
            except Exception as e:
                print(f"     ❌ Strategy failed: {e}", file=sys.stderr)
                try:
                    os.remove(temp_clip_path)
                except:
                    pass
        
        # If all strategies failed, create a longer "debug" clip
        print(f"   🔍 All strategies failed, creating extended debug clip", file=sys.stderr)
        debug_start = max(0, start - 30)
        debug_end = end + 30
        debug_path = str(output_path).replace('.mp4', '_debug_extended.mp4')
        
        success = self._extract_single_clip(video_path, debug_start, debug_end, debug_path, 0)
        
        if success:
            print(f"   📹 Debug clip created: {debug_path}", file=sys.stderr)
            print(f"      Covers {debug_start:.1f}s - {debug_end:.1f}s (60s total)", file=sys.stderr)
            print(f"      Look for quote around {start-debug_start:.1f}s mark in this clip", file=sys.stderr)
            
            # Also copy to main output path so user gets something
            import shutil
            shutil.copy(debug_path, output_path)
        
        return {
            'success': False,
            'debug_clip': debug_path if success else None,
            'message': 'Quote not found at expected timestamp. Check debug clip.'
        }

    def _extract_single_clip(self, video_path, start, end, output_path, padding):
        """Extract a single clip without verification."""
        padded_start = max(0, start - padding)
        padded_end = end + padding
        
        # Check video duration
        try:
            probe_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)]
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            video_duration = float(result.stdout.strip()) if result.stdout.strip() else 0
            
            if padded_end > video_duration:
                padded_end = video_duration - 0.1
        except Exception:
            pass
        
        duration = padded_end - padded_start
        if duration <= 0:
            return False
        
        # FFmpeg command
        command = [
            "ffmpeg",
            "-ss", f"{padded_start:.2f}",
            "-i", str(video_path),
            "-t", f"{duration:.2f}",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            "-y", str(output_path),
        ]
        
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            return result.returncode == 0 and os.path.exists(output_path)
        except Exception:
            return False

    def _verify_clip_contains_quote(self, clip_path, quote, strategy_name):
        """
        Verify that the extracted clip likely contains the quote.
        Uses multiple verification methods.
        """
        print(f"     🔍 Verifying clip contains quote...", file=sys.stderr)
        
        verification_methods = []
        
        # Method 1: Check clip duration is reasonable
        try:
            probe_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(clip_path)]
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            duration = float(result.stdout.strip()) if result.stdout.strip() else 0
            
            if duration > 0:
                verification_methods.append({
                    'method': 'duration_check',
                    'passed': duration >= 2.0,  # At least 2 seconds
                    'details': f"Duration: {duration:.1f}s"
                })
            else:
                return {'likely_contains_quote': False, 'reason': 'Zero duration clip', 'confidence': 'low'}
        except Exception as e:
            return {'likely_contains_quote': False, 'reason': f'Could not probe clip: {e}', 'confidence': 'low'}
        
        # Method 2: Quick audio presence check
        try:
            # Check if clip has audio content (not silent)
            audio_check_cmd = [
                "ffprobe", "-v", "quiet", "-show_entries", "stream=codec_type", 
                "-of", "csv=p=0", str(clip_path)
            ]
            result = subprocess.run(audio_check_cmd, capture_output=True, text=True)
            has_audio = 'audio' in result.stdout.lower()
            
            verification_methods.append({
                'method': 'audio_check',
                'passed': has_audio,
                'details': f"Has audio: {has_audio}"
            })
        except Exception:
            pass
        
        # Method 3: File size sanity check
        try:
            file_size = os.path.getsize(clip_path)
            # Expect at least 100KB for a few seconds of video
            size_reasonable = file_size > 100000
            
            verification_methods.append({
                'method': 'size_check', 
                'passed': size_reasonable,
                'details': f"Size: {file_size//1000}KB"
            })
        except Exception:
            pass
        
        # Method 4: Strategy-based confidence
        strategy_confidence = {
            "Exact timing": 0.9,
            "Small buffer": 0.8,
            "Medium buffer": 0.6,
            "Large buffer": 0.4,
            "Extended search": 0.2
        }
        
        base_confidence = strategy_confidence.get(strategy_name, 0.1)
        
        # Calculate overall confidence
        passed_checks = sum(1 for method in verification_methods if method['passed'])
        total_checks = len(verification_methods)
        
        if total_checks > 0:
            check_score = passed_checks / total_checks
            final_confidence = base_confidence * check_score
        else:
            final_confidence = base_confidence
        
        # Log verification details
        for method in verification_methods:
            status = "✅" if method['passed'] else "❌"
            print(f"       {status} {method['method']}: {method['details']}", file=sys.stderr)
        
        # Decision logic
        likely_contains_quote = final_confidence >= 0.5
        
        if likely_contains_quote:
            confidence_level = "high" if final_confidence >= 0.8 else "medium" if final_confidence >= 0.6 else "low"
        else:
            confidence_level = "low"
            
        reason = f"Confidence: {final_confidence:.2f}, Strategy: {strategy_name}"
        
        return {
            'likely_contains_quote': likely_contains_quote,
            'confidence': confidence_level,
            'confidence_score': final_confidence,
            'reason': reason,
            'verification_methods': verification_methods
        }

    def fetch_youtube_transcript(self, url, languages=("en",)):
        """Return transcript text and segment timings if YouTube provides them."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except Exception:
            logging.info("youtube_transcript_api not installed")
            return None, None

        video_id = None
        m = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})(?:[?&]|$)", url)
        if m:
            video_id = m.group(1)
        if not video_id:
            logging.info("Could not extract video id from %s", url)
            return None, None

        try:
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = None
            for lang in languages:
                try:
                    transcript = transcripts.find_manually_created_transcript([lang])
                    break
                except Exception:
                    pass
            if transcript is None:
                for lang in languages:
                    try:
                        transcript = transcripts.find_generated_transcript([lang])
                        break
                    except Exception:
                        pass
            if transcript is None:
                return None, None
            items = transcript.fetch()
            segments = [
                {"start": it["start"], "end": it["start"] + it["duration"], "text": it["text"]}
                for it in items
            ]
            text = " ".join(it["text"] for it in items)
            return text, segments
        except Exception as e:
            logging.info("fetch_youtube_transcript failed: %s", e)
            return None, None

    def convert_to_wav(self, video_path, job_id):
        audio_output_path = self.public_folder / f"{job_id}_audio.wav"
        command = [
            'ffmpeg', '-i', str(video_path),
            '-ar', '16000',      # 16kHz
            '-ac', '1',          # mono
            '-y', str(audio_output_path)
        ]
        try:
            logging.info("convert_to_wav: running ffmpeg %s", ' '.join(command))
            print("Converting video to WAV for Whisper...", file=sys.stderr)
            subprocess.run(command, check=True, capture_output=True, text=True)
            print("Conversion successful.", file=sys.stderr)
            logging.info("convert_to_wav: wrote %s", audio_output_path)
            return str(audio_output_path)
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error: {e.stderr}", file=sys.stderr)
            logging.error("convert_to_wav failed: %s", e.stderr)
            raise RuntimeError(f"FFmpeg failed: {e.stderr}")

    def process(self, url, job_id, whisper_manager):
        """Process a YouTube URL and return transcript text, video path, and segments."""
        import yt_dlp
        from yt_dlp.utils import DownloadError

        class _Logger:
            def debug(self, msg): pass
            def warning(self, msg): pass
            def error(self, msg): print(msg, file=sys.stderr)

        logging.info("YouTubeProcessor: checking transcripts for %s", url)
        print("Checking for existing transcripts...", file=sys.stderr)
        transcript_text, segments = self.fetch_youtube_transcript(url)

        logging.info("YouTubeProcessor: downloading %s", url)
        print("Downloading YouTube video...", file=sys.stderr)
        video_path = self.public_folder / f"{job_id}_full.mp4"
        video_format = os.getenv(
            "YTDLP_VIDEO_FORMAT",
            "bestvideo[height<=720]+bestaudio/best[height<=720]",
        )
        logging.info("YouTubeProcessor: using format %s", video_format)
        ydl_opts = {
            'format': video_format,
            'outtmpl': str(video_path),
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
            'logger': _Logger(),
        }
        cookie_file = os.getenv("YTDLP_COOKIE_FILE")
        if cookie_file and os.path.exists(cookie_file):
            print(f"Using cookies from {cookie_file}", file=sys.stderr)
            ydl_opts['cookiefile'] = cookie_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([url])
            except DownloadError as e:
                message = str(e)
                if "Sign in to confirm" in message:
                    message += (
                        "\nSet the YTDLP_COOKIE_FILE environment variable to the "
                        "path of a browser-exported cookies file so yt_dlp can "
                        "authenticate."
                    )
                raise RuntimeError(f"Failed to download video: {message}")
        
        logging.info("YouTubeProcessor: downloaded to %s", video_path)
        print(f"Downloaded to: {video_path}", file=sys.stderr)

        if not transcript_text:
            wav_path = self.convert_to_wav(video_path, job_id)

            logging.info("YouTubeProcessor: transcribing")
            print("Transcribing audio...", file=sys.stderr)
            transcript_result = whisper_manager.transcribe_audio(wav_path)
            transcript_text = transcript_result.get("text", "")
            segments = transcript_result.get("segments", [])
            logging.info(
                "YouTubeProcessor: transcription complete (%d chars, %d segments)",
                len(transcript_text),
                len(segments),
            )
            print("Transcription complete.", file=sys.stderr)
        else:
            logging.info(
                "YouTubeProcessor: using existing transcript (%d chars, %d segments)",
                len(transcript_text),
                len(segments),
            )

        # DEBUG AND FIX SEGMENTS BEFORE MERGING
        print(f"🔍 SEGMENTS DEBUG BEFORE PROCESSING:", file=sys.stderr)
        print(f"   Total segments: {len(segments)}", file=sys.stderr)
        
        if segments and len(segments) > 0:
            print(f"   First segment: {segments[0]}", file=sys.stderr)
            print(f"   Last segment: {segments[-1]}", file=sys.stderr)
            
            # Calculate average duration of original segments
            avg_duration = sum(s.get('end', 0) - s.get('start', 0) for s in segments) / len(segments)
            print(f"   Average duration: {avg_duration:.1f}s", file=sys.stderr)
            
            # Check for and fix missing timestamps
            valid_segments = []
            for i, segment in enumerate(segments):
                # Ensure segment has proper structure
                if isinstance(segment, dict):
                    start = segment.get("start", 0)
                    end = segment.get("end", 0)
                    text = segment.get("text", "")
                    
                    # Skip empty segments
                    if not text.strip():
                        continue
                    
                    # Fix segments with missing or zero timestamps
                    if start == 0 and end == 0 and i > 0:
                        # Try to estimate timing based on previous segment
                        prev_end = valid_segments[-1].get("end", 0) if valid_segments else 0
                        estimated_duration = max(2.0, len(text) * 0.1)  # Rough estimate: 0.1s per character
                        start = prev_end
                        end = start + estimated_duration
                        print(f"   Fixed segment {i}: estimated {start:.1f}s - {end:.1f}s", file=sys.stderr)
                    
                    valid_segments.append({
                        "start": float(start),
                        "end": float(end),
                        "text": text.strip()
                    })
                else:
                    print(f"   Warning: segment {i} is not a dict: {segment}", file=sys.stderr)
            
            segments = valid_segments
            print(f"   Valid segments after cleanup: {len(segments)}", file=sys.stderr)
            
            # Merge short segments into longer, more coherent chunks
            if avg_duration < 6.0:  # Only merge if segments are short on average
                merged_segments = self.merge_short_segments(segments)
                
                # Use merged segments if they're better
                if len(merged_segments) > 0 and len(merged_segments) < len(segments) * 0.8:
                    print(f"✅ Using merged segments: {len(merged_segments)} instead of {len(segments)}", file=sys.stderr)
                    segments = merged_segments
                else:
                    print(f"⚠️  Keeping original segments (merging didn't improve much)", file=sys.stderr)
            else:
                print(f"⚠️  Segments already long enough, skipping merge", file=sys.stderr)
        
        # Save segments for later clip extraction
        segments_file = self.public_folder / f"{job_id}_segments.json"
        try:
            with open(segments_file, "w") as f:
                json.dump(segments, f, indent=2)
            print(f"✅ Saved {len(segments)} segments to {segments_file}", file=sys.stderr)
            
            # Verify the saved file
            with open(segments_file, "r") as f:
                saved_segments = json.load(f)
            print(f"✅ Verified: loaded {len(saved_segments)} segments from saved file", file=sys.stderr)
            
        except Exception as e:
            print(f"❌ Error saving segments: {e}", file=sys.stderr)
            raise RuntimeError(f"Failed to save segments: {e}")

        return transcript_text, str(video_path), segments

    # Keep the old method for backward compatibility but use verification when possible
    def extract_clip(self, video_path, start, end, output_path, padding=1.0):
        """Extract a clip with verification if quote information is available."""
        
        # Check if we have quote information for verification
        quote = getattr(self, '_current_quote', '')
        segments = getattr(self, '_current_segments', [])
        
        if quote and segments:
            print(f"🎬 Using verified extraction for quote: '{quote[:30]}...'", file=sys.stderr)
            result = self.extract_clip_with_verification(video_path, start, end, output_path, quote, segments, padding)
            
            if result['success']:
                print(f"✅ Verified extraction successful using {result['strategy']}", file=sys.stderr)
                return True
            else:
                print(f"⚠️  Verified extraction failed: {result.get('message', 'Unknown error')}", file=sys.stderr)
                return result.get('debug_clip') is not None
        else:
            print(f"🎬 Using standard extraction (no quote verification available)", file=sys.stderr)
            return self._extract_single_clip(video_path, start, end, output_path, padding)

    def find_quote_timestamps(self, segments, quote, window=20, threshold=0.65, context_padding=2.0):
        """
        Find the best matching segment(s) for a quote using the debugging matcher.
        """
        print(f"🎯 QUOTE MATCHING REQUEST:", file=sys.stderr)
        print(f"   Quote: '{quote}'", file=sys.stderr)
        print(f"   Segments available: {len(segments)}", file=sys.stderr)
        print(f"   Context padding: {context_padding}s", file=sys.stderr)
        
        result = self.quote_matcher.find_best_match(segments, quote, window, context_padding)
        
        if result[0] is not None:
            print(f"🎯 FINAL RESULT: {result[0]:.1f}s - {result[1]:.1f}s", file=sys.stderr)
        else:
            print(f"🎯 FINAL RESULT: No match found", file=sys.stderr)
            
        return result