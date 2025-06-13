"use client";

import { useState } from 'react';

interface TranscriptViewerProps {
    transcript: string;
    inputType: string;
}

export function TranscriptViewer({ transcript, inputType }: TranscriptViewerProps) {
    const [isExpanded, setIsExpanded] = useState(false);

    if (!transcript || transcript.trim() === '') {
        return null;
    }

    const getTitle = () => {
        switch (inputType) {
            case 'youtube':
                return 'Full Transcript';
            case 'pdf':
                return 'Extracted Text';
            case 'text':
                return 'Source Text';
            default:
                return 'Content';
        }
    };

    const formatTranscript = (text: string) => {
        // For PDFs, preserve page markers formatting
        if (inputType === 'pdf') {
            return text.split('\n').map((line, index) => {
                if (line.match(/^--- Page \d+ ---$/)) {
                    return (
                        <div key={index} className="font-bold text-blue-600 dark:text-blue-400 my-4 py-2 border-b border-gray-300 dark:border-gray-600">
                            {line}
                        </div>
                    );
                }
                return line && <p key={index} className="mb-2">{line}</p>;
            });
        }

        // For other types, split into paragraphs
        return text.split('\n\n').map((paragraph, index) =>
            paragraph.trim() && (
                <p key={index} className="mb-4">
                    {paragraph.trim()}
                </p>
            )
        );
    };

    const preview = transcript.substring(0, 300) + (transcript.length > 300 ? '...' : '');
    const wordCount = transcript.split(/\s+/).length;
    const charCount = transcript.length;

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden my-6">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {getTitle()}
                    </h3>
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                        {wordCount.toLocaleString()} words • {charCount.toLocaleString()} characters
                    </div>
                </div>
            </div>

            <div className="p-4">
                <div className="prose prose-sm max-w-none dark:prose-invert">
                    {isExpanded ? (
                        <div className="text-gray-700 dark:text-gray-300">
                            {formatTranscript(transcript)}
                        </div>
                    ) : (
                        <div className="text-gray-700 dark:text-gray-300">
                            {formatTranscript(preview)}
                        </div>
                    )}
                </div>

                <div className="mt-4 flex gap-2">
                    <button
                        onClick={() => setIsExpanded(!isExpanded)}
                        className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm"
                    >
                        {isExpanded ? 'Show Less' : 'Show Full Transcript'}
                    </button>

                    <button
                        onClick={() => {
                            const blob = new Blob([transcript], { type: 'text/plain' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `transcript-${Date.now()}.txt`;
                            a.click();
                            URL.revokeObjectURL(url);
                        }}
                        className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700 text-sm"
                    >
                        Download Transcript
                    </button>

                    <button
                        onClick={() => {
                            navigator.clipboard.writeText(transcript);
                            // You could add a toast notification here
                        }}
                        className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700 text-sm"
                    >
                        Copy to Clipboard
                    </button>
                </div>
            </div>
        </div>
    );
}