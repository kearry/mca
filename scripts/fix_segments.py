#!/usr/bin/env python3
"""
Quick script to fix existing segments files that have zero timestamps
Run this from your project root: python scripts/fix_segments.py
"""

import json
import os
from pathlib import Path

def fix_segments_file(segments_file):
    """Fix a segments file with zero timestamps"""
    print(f"Fixing {segments_file}...")
    
    try:
        with open(segments_file, 'r') as f:
            segments = json.load(f)
        
        if not segments:
            print("  No segments found, skipping")
            return
        
        # Check if fix is needed
        zero_count = sum(1 for s in segments if s.get("start", 0) == 0 and s.get("end", 0) == 0)
        if zero_count == 0:
            print(f"  Already has valid timestamps, skipping")
            return
        
        print(f"  Found {zero_count}/{len(segments)} segments with zero timestamps")
        
        # Fix timestamps
        current_time = 0.0
        fixed_segments = []
        
        for i, segment in enumerate(segments):
            if isinstance(segment, dict):
                text = segment.get("text", "").strip()
                if not text:
                    continue
                
                start = segment.get("start", 0)
                end = segment.get("end", 0)
                
                # If both are zero, estimate timing
                if start == 0 and end == 0:
                    # Estimate duration based on text length (roughly 150 words per minute)
                    words = len(text.split())
                    estimated_duration = max(1.0, words / 2.5)  # 2.5 words per second
                    
                    start = current_time
                    end = current_time + estimated_duration
                    current_time = end + 0.1  # Small gap between segments
                else:
                    current_time = max(current_time, end)
                
                fixed_segments.append({
                    "start": float(start),
                    "end": float(end),
                    "text": text
                })
        
        # Save the fixed file
        backup_file = str(segments_file) + ".backup"
        os.rename(segments_file, backup_file)
        print(f"  Created backup: {backup_file}")
        
        with open(segments_file, 'w') as f:
            json.dump(fixed_segments, f, indent=2)
        
        print(f"  ✅ Fixed! {len(fixed_segments)} segments with proper timestamps")
        print(f"     Duration: 0s - {fixed_segments[-1]['end']:.1f}s")
        
    except Exception as e:
        print(f"  ❌ Error: {e}")

def main():
    # Find all segments files in public/generated
    public_folder = Path("public/generated")
    if not public_folder.exists():
        print("public/generated folder not found!")
        return
    
    segments_files = list(public_folder.glob("*_segments.json"))
    
    if not segments_files:
        print("No segments files found")
        return
    
    print(f"Found {len(segments_files)} segments files to check:")
    
    for segments_file in segments_files:
        fix_segments_file(segments_file)
    
    print("\nDone! Try extracting clips again.")

if __name__ == "__main__":
    main()